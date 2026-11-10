"""Analyse each asset against its factors, train forecasting models, and
write everything the webpage shows to data/data.js.

    python model/train.py

Steps for each asset:
1. Factor analysis: how each factor has moved with the asset over ~20 years,
   whether its moves have led the asset's next month, how that link has
   changed over time, and what happened after big moves up or down.
2. Models: logistic regression (simple, linear), gradient-boosted trees
   (learns non-linear patterns and interactions between factors), and an
   ensemble averaging the two. Each answers "will the price be higher in
   N trading days?"
3. Walk-forward test: for every year since FIRST_TEST_YEAR, train only on
   data before that year and predict that year. Results across all years
   give an honest accuracy figure. The model with the best result is used
   for today's forecast.
"""

import io
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
from config import ASSETS, FACTORS, FIRST_TEST_YEAR, HORIZONS, START  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "data.js"
RNG = np.random.default_rng(0)


# ------------------------------------------------------------------ data

def fetch(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def load_fred(series_id):
    raw = fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={START}")
    df = pd.read_csv(io.BytesIO(raw))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna()


def load_gpr(column):
    raw = fetch("https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls")
    df = pd.read_excel(io.BytesIO(raw))
    return df.set_index(pd.to_datetime(df["date"]))[column].dropna()


def load_data():
    import yfinance as yf

    tickers = sorted({a["ticker"] for a in ASSETS} |
                     {f["source"][1] for f in FACTORS.values() if f["source"][0] == "yahoo"})
    yahoo = yf.download(tickers, start=START, auto_adjust=True, progress=False)["Close"]
    yahoo = yahoo.sort_index()
    days = yahoo.index

    prices = {a["id"]: yahoo[a["ticker"]].where(yahoo[a["ticker"]] > 0) for a in ASSETS}
    factors = {}
    for key, f in FACTORS.items():
        kind, sid = f["source"]
        s = yahoo[sid] if kind == "yahoo" else load_fred(sid) if kind == "fred" else load_gpr(sid)
        # Align to trading days, then delay by the publication lag.
        s = s.reindex(s.index.union(days)).ffill(limit=10).reindex(days)
        factors[key] = s.shift(f["lag"])
        print(f"  {key:<13} {kind}:{sid:<10} {s.first_valid_index():%Y-%m-%d} → {s.last_valid_index():%Y-%m-%d}")
    return prices, factors


def change(s, k, transform):
    return s.diff(k) if transform == "diff" else s.pct_change(k, fill_method=None)


# -------------------------------------------------------------- features

def build_features(price, factors):
    cols, groups = {}, {}
    logp = np.log(price)
    for k in (5, 20, 60, 120):
        cols[f"self_ret{k}"] = price.pct_change(k, fill_method=None)
    vol20 = logp.diff().rolling(20).std()
    cols["self_vol20"] = vol20
    cols["self_volratio"] = vol20 / logp.diff().rolling(120).std()
    cols["self_ma200"] = price / price.rolling(200).mean() - 1
    for c in cols:
        groups[c] = "momentum"
    for key, s in factors.items():
        t = FACTORS[key]["transform"]
        for k in (5, 20, 60):
            cols[f"{key}_chg{k}"] = change(s, k, t)
        cols[f"{key}_level"] = (s - s.rolling(252).mean()) / s.rolling(252).std()
        for c in (f"{key}_chg5", f"{key}_chg20", f"{key}_chg60", f"{key}_level"):
            groups[c] = key
    return pd.DataFrame(cols), groups


def readable(col, asset):
    key, kind = col.split("_", 1) if not col.startswith("real_rates") else ("real_rates", col[11:])
    name = asset["name"] if key == "self" else FACTORS[key]["name"]
    return {
        "ret5": f"{name}: 1-week return", "ret20": f"{name}: 1-month return",
        "ret60": f"{name}: 3-month return", "ret120": f"{name}: 6-month return",
        "vol20": f"{name}: volatility", "volratio": f"{name}: volatility vs normal",
        "ma200": f"{name}: distance from 200-day average",
        "chg5": f"{name}: 1-week change", "chg20": f"{name}: 1-month change",
        "chg60": f"{name}: 3-month change", "level": f"{name}: level vs past year",
    }[kind]


# ---------------------------------------------------------------- models

MODELS = {
    "logit": ("Logistic regression",
              lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000))),
    "gbm": ("Gradient-boosted trees",
            lambda: HistGradientBoostingClassifier(
                max_depth=3, learning_rate=0.04, max_iter=250, min_samples_leaf=120,
                l2_regularization=2.0, max_features=0.6, random_state=0)),
}


class Ensemble:
    def __init__(self):
        self.ms = [MODELS["logit"][1](), MODELS["gbm"][1]()]

    def fit(self, X, y):
        for m in self.ms:
            m.fit(X, y)
        return self

    def predict_proba(self, X):
        return np.mean([m.predict_proba(X) for m in self.ms], axis=0)


def make(name):
    return Ensemble() if name == "ensemble" else MODELS[name][1]()


MODEL_NAMES = {"logit": "Logistic regression", "gbm": "Gradient-boosted trees",
               "ensemble": "Ensemble (average of both)"}


def walk_forward(X, y, h):
    """Train on everything before each year (minus an h-day gap so labels
    never overlap the test year), predict that year. Returns out-of-sample
    probabilities for every model plus the naive guess for each row."""
    data = X.join(y.rename("y")).dropna()
    years = sorted({d.year for d in data.index if d.year >= FIRST_TEST_YEAR})
    rows = []
    for yr in years:
        test = data[data.index.year == yr]
        cut = data.index.searchsorted(pd.Timestamp(f"{yr}-01-01"))
        train = data.iloc[: max(cut - h, 0)]
        if len(train) < 750 or test.empty:
            continue
        naive = float(train["y"].mean() >= 0.5)  # "the usual outcome so far"
        out = pd.DataFrame({"y": test["y"], "naive": naive, "year": yr}, index=test.index)
        for name in ("logit", "gbm", "ensemble"):
            m = make(name).fit(train[X.columns], train["y"])
            out[name] = m.predict_proba(test[X.columns])[:, 1]
        rows.append(out)
    return pd.concat(rows), data


def evaluate(oos, name):
    p, y = oos[name], oos["y"]
    pred = (p >= 0.5).astype(float)
    acc = float((pred == y).mean())
    # "Guessing" = the better of a coin flip and always picking the usual outcome.
    base = max(float((oos["naive"] == y).mean()), 0.5)
    auc = float(roc_auc_score(y, p))
    up = pred == 1
    return {"accuracy": round(acc, 4), "baseline": round(base, 4), "auc": round(auc, 4),
            "hitRateUp": round(float(y[up].mean()), 4) if up.any() else None,
            "brier": round(float(((p - y) ** 2).mean()), 4)}


def score_of(ev):
    """0-100. 50 = no better than guessing. Half comes from ranking skill
    (AUC 0.70 = full marks), half from accuracy gained over the naive guess
    (15 points of accuracy = full marks)."""
    auc_part = np.clip((ev["auc"] - 0.5) / 0.2, -1, 1)
    lift_part = np.clip((ev["accuracy"] - ev["baseline"]) / 0.15, -1, 1)
    return float(50 + 25 * auc_part + 25 * lift_part)


def group_importance(model, X, y, groups, repeats=4):
    """How much worse the model ranks up/down days when one factor's inputs
    are shuffled (permutation importance, grouped by factor)."""
    base = roc_auc_score(y, model.predict_proba(X)[:, 1])
    out = {}
    for g in sorted(set(groups.values())):
        cols = [c for c in X.columns if groups[c] == g]
        drops = []
        for _ in range(repeats):
            Xp = X.copy()
            idx = RNG.permutation(len(Xp))
            Xp[cols] = Xp[cols].to_numpy()[idx]
            drops.append(base - roc_auc_score(y, model.predict_proba(Xp)[:, 1]))
        out[g] = float(np.mean(drops))
    return out


def push_today(model, X_all, latest, groups):
    """Each factor's push on today's forecast: today's probability minus the
    probability if that factor's inputs were at their typical (median) value."""
    p = float(model.predict_proba(latest)[0, 1])
    med = X_all.median()
    out = {}
    for g in set(groups.values()):
        cols = [c for c in latest.columns if groups[c] == g]
        neutral = latest.copy()
        neutral[cols] = med[cols].to_numpy()
        out[g] = p - float(model.predict_proba(neutral)[0, 1])
    return p, out


# ------------------------------------------------------- factor analysis

def factor_analysis(asset, price, s, key):
    t = FACTORS[key]["transform"]
    s = s.reindex(price.index)  # same trading days as the asset
    rets = np.log(price).diff()
    fchg = change(s, 1, t)
    # Weekly changes give a cleaner read than noisy daily ones.
    wk_a, wk_f = np.log(price).diff(5)[::5], change(s, 5, t)[::5]
    corr_1y = float(wk_a.tail(52).corr(wk_f.tail(52)))
    corr_all = float(wk_a.corr(wk_f))
    roll = rets.rolling(252).corr(fchg).resample("ME").last().dropna()
    roll = roll[roll.index >= "2008-01-01"]

    # Does the factor's last month say anything about the asset's next month?
    # Sample every 20 days so periods don't overlap.
    past = change(s, 20, t)
    fwd = price.shift(-20) / price - 1
    pair = pd.DataFrame({"past": past, "fwd": fwd}).dropna()[::20]
    lead = float(pair["past"].corr(pair["fwd"]))

    # What happened next after big rises / falls in the factor.
    pair5 = pd.DataFrame({"past": past, "fwd": fwd}).dropna()[::5]
    lo, hi = pair5["past"].quantile([1 / 3, 2 / 3])
    buckets = []
    for label, mask in (("Fell the most", pair5["past"] <= lo),
                        ("Little change", (pair5["past"] > lo) & (pair5["past"] < hi)),
                        ("Rose the most", pair5["past"] >= hi)):
        sub = pair5[mask]["fwd"]
        buckets.append({"label": label, "avgReturn": round(float(sub.mean()), 4),
                        "upShare": round(float((sub > 0).mean()), 3), "n": int(len(sub))})

    cur = s.dropna()
    recent = float(change(cur, 20, t).iloc[-1])
    hist10 = cur.tail(2520)
    pctile = float((hist10 < cur.iloc[-1]).mean())
    now_bucket = 0 if recent <= lo else 2 if recent >= hi else 1
    return {
        "corr1y": round(corr_1y, 3), "corrAll": round(corr_all, 3), "lead": round(lead, 3),
        "rolling": [[d.strftime("%Y-%m-%d"), round(float(v), 3)] for d, v in roll.items()],
        "buckets": buckets, "nowBucket": now_bucket,
        "recentChange": round(recent, 5), "level": round(float(cur.iloc[-1]), 4),
        "levelPercentile": round(pctile, 3), "transform": t,
    }


def describe(asset, key, fa, push):
    f = FACTORS[key]
    nm, an = f["name"].lower(), asset["name"].lower()
    c = fa["corrAll"]
    rel = ("usually moves in the same direction as" if c > 0.15 else
           "usually moves opposite to" if c < -0.15 else "has only a loose week-to-week link with")
    b_lo, b_hi = fa["buckets"][0], fa["buckets"][2]
    if fa["transform"] == "diff":
        move = f"{'up' if fa['recentChange'] > 0 else 'down'} {abs(fa['recentChange']):.2f} points"
    else:
        move = f"{'up' if fa['recentChange'] > 0 else 'down'} {abs(fa['recentChange']) * 100:.1f}%"
    now = fa["buckets"][fa["nowBucket"]]
    effect = ("pushing the forecast up" if push > 0.01 else
              "pushing the forecast down" if push < -0.01 else "barely moving the forecast")
    stability = ""
    r = [v for _, v in fa["rolling"][-60:]]
    if r and (min(r) < -0.1 < 0.1 < max(r)):
        stability = " The link has flipped sign over the past five years, so it is not reliable on its own."
    return (f"Since 2006, {an} {rel} {nm} (correlation {c:+.2f}). "
            f"After months when {nm} rose the most, {an} was higher a month later "
            f"{b_hi['upShare'] * 100:.0f}% of the time (average {b_hi['avgReturn'] * 100:+.1f}%); after the biggest falls, "
            f"{b_lo['upShare'] * 100:.0f}% of the time ({b_lo['avgReturn'] * 100:+.1f}%).{stability} "
            f"Over the last month it moved {move}, a “{now['label'].lower()}” month, and the model reads it as "
            f"{effect}.")


# ------------------------------------------------------------------ main

def series_out(s, n=None, digits=4):
    s = s.dropna()
    if n:
        s = s.tail(n)
    return [[d.strftime("%Y-%m-%d"), round(float(v), digits)] for d, v in s.items()]


def forecast_path(price, probs, days=60):
    logp = np.log(price.dropna())
    sigma = float(logp.diff().tail(60).std())
    pts = [(0, 0.0)]
    for h, p in sorted(probs.items()):
        typical = float(logp.diff(h).abs().tail(750).mean())
        pts.append((h, (2 * p - 1) * typical))
    xs, ys = zip(*pts)
    dates = pd.bdate_range(price.index[-1], periods=days + 1)[1:]
    last = float(price.dropna().iloc[-1])
    return [[d.strftime("%Y-%m-%d"), last * np.exp(np.interp(i, xs, ys)),
             last * np.exp(np.interp(i, xs, ys) - sigma * np.sqrt(i)),
             last * np.exp(np.interp(i, xs, ys) + sigma * np.sqrt(i))]
            for i, d in enumerate(dates, start=1)]


def recommendation(asset, horizons, score):
    p = 0.25 * horizons[0]["probUp"] + 0.5 * horizons[1]["probUp"] + 0.25 * horizons[2]["probUp"]
    n = asset["name"].lower()
    if p >= 0.60:
        label, text = "Bullish", f"The model expects {n} to rise. A reasonable time to buy or add."
    elif p >= 0.53:
        label, text = "Mildly bullish", f"Slight upward lean. Consider adding to {n} gradually rather than all at once."
    elif p > 0.47:
        label, text = "Neutral", "No clear direction. Holding makes sense; there's no strong case to buy or sell."
    elif p > 0.40:
        label, text = "Mildly bearish", "Slight downward lean. Consider waiting before buying, or trimming a large position."
    else:
        label, text = "Bearish", f"The model expects {n} to fall. Consider reducing exposure or waiting."
    if score < 50:
        lean = "up" if p >= 0.5 else "down"
        label = "No reliable signal"
        text = (f"The model leans {lean} ({p * 100:.0f}% blended chance of rising), but in testing it did "
                f"worse than guessing for {n}, so it shouldn't drive a decision. Use the factor analysis instead.")
    elif score < 55:
        text += " In testing this model was only slightly better than guessing, so treat this as weak evidence."
    return {"label": label, "score": round(float(p), 3), "text": text}


def run_asset(asset, prices, all_factors):
    price = prices[asset["id"]].dropna()
    factors = {k: all_factors[k] for k in asset["factors"]}
    X, groups = build_features(price, factors)
    X = X.loc[price.index]

    horizons, comparison, yearly, importance, pushes = [], {}, None, None, None
    probs = {}
    for h in HORIZONS:
        y = (price.shift(-h) > price).astype(float)
        y[price.shift(-h).isna()] = np.nan
        oos, data = walk_forward(X, y, h)
        evs = {n: evaluate(oos, n) for n in ("logit", "gbm", "ensemble")}
        best = max(evs, key=lambda n: score_of(evs[n]))
        model = make(best).fit(data[X.columns], data["y"])
        latest = X.dropna().iloc[[-1]]
        p, push = push_today(model, data[X.columns], latest, groups)
        probs[h] = p
        ev = evs[best]
        horizons.append({"days": h, "probUp": round(p, 4), "model": best,
                         "modelName": MODEL_NAMES[best], "score": round(score_of(ev)),
                         "testFrom": oos.index[0].strftime("%Y-%m-%d"),
                         "testTo": oos.index[-1].strftime("%Y-%m-%d"),
                         "testSize": len(oos), "trainStart": data.index[0].strftime("%Y-%m-%d"), **ev})
        comparison[h] = [{"model": n, "name": MODEL_NAMES[n], "score": round(score_of(evs[n])), **evs[n]}
                         for n in ("logit", "gbm", "ensemble")]
        if h == 20:
            pushes = push
            yearly = []
            for yr, g in oos.groupby("year"):
                yearly.append({"year": int(yr),
                               "accuracy": round(float(((g[best] >= 0.5) == g["y"]).mean()), 3),
                               "baseline": round(max(float((g["naive"] == g["y"]).mean()), 0.5), 3),
                               "upShare": round(float(g["y"].mean()), 3)})
            # Importance on the last 3 years, from a model trained before them.
            cut = data.index.searchsorted(data.index[-1] - pd.DateOffset(years=3))
            m_imp = make(best).fit(data.iloc[: cut - h][X.columns], data.iloc[: cut - h]["y"])
            importance = group_importance(m_imp, data.iloc[cut:][X.columns], data.iloc[cut:]["y"], groups)
            logit = make("logit").fit(data[X.columns], data["y"])
            coefs = sorted(zip(X.columns, logit[-1].coef_[0]), key=lambda kv: -abs(kv[1]))[:8]

    score = round(float(np.mean([hz["score"] for hz in horizons])))
    out_factors = []
    for k, s in factors.items():
        fa = factor_analysis(asset, price, s, k)
        out_factors.append({
            "id": k, "name": FACTORS[k]["name"], "about": FACTORS[k]["about"],
            "source": FACTORS[k]["label"], "push": round(pushes[k], 4),
            "importance": round(importance[k], 4),
            "explanation": describe(asset, k, fa, pushes[k]),
            "series": series_out(s, 260), **fa,
        })
    out_factors.sort(key=lambda f: -f["importance"])

    conv = asset["convert"]
    last, prev = float(price.iloc[-1]), float(price.iloc[-2])
    return {
        "id": asset["id"], "name": asset["name"], "symbol": asset["symbol"],
        "ticker": asset["ticker"], "unit": asset["unit"], "unitLabel": asset["unit_label"],
        "price": {"perUnit": round(last * conv, 4), "changePct": round(last / prev - 1, 5),
                  "contract": round(last, 4), "asOf": price.index[-1].strftime("%Y-%m-%d")},
        "history": series_out(price * conv, 520),
        "forecast": {"horizons": horizons,
                     "path": [[d, round(m * conv, 4), round(lo * conv, 4), round(hi * conv, 4)]
                              for d, m, lo, hi in forecast_path(price, probs)]},
        "momentum": {"push": round(pushes["momentum"], 4), "importance": round(importance["momentum"], 4)},
        "factors": out_factors,
        "score": score,
        "model": {
            "comparison": {str(h): v for h, v in comparison.items()},
            "yearly": yearly,
            "features": len(X.columns),
            "coefficients": [{"feature": readable(c, asset), "weight": round(float(v), 3)} for c, v in coefs],
        },
        "recommendation": recommendation(asset, horizons, score),
    }


def main():
    print("Downloading data…")
    prices, factors = load_data()
    results = []
    for a in ASSETS:
        try:
            r = run_asset(a, prices, factors)
            results.append(r)
            print(f"{a['name']:<12} score {r['score']:>3}  " + "  ".join(
                f"{h['days']}d:{h['model']:<8} acc {h['accuracy']:.2f} vs {h['baseline']:.2f} auc {h['auc']:.2f}"
                for h in r["forecast"]["horizons"]))
        except Exception as e:  # keep other assets if one fails
            import traceback
            traceback.print_exc()
            print(f"skipping {a['name']}: {e}", file=sys.stderr)

    payload = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "sample": False, "firstTestYear": FIRST_TEST_YEAR, "assets": results}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("window.ASSET_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
