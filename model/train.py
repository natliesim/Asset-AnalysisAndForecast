"""Train one logistic regression per asset and horizon, then write the
results the webpage reads (data/data.js).

    python model/train.py            # real market data from Yahoo Finance
    python model/train.py --sample   # offline demo with simulated data

The model answers a yes/no question: "Will the price be higher in N
trading days?" Inputs are recent moves in the asset itself and in the
factors that drive it (dollar, rates, inflation, risk, demand...).
Because logistic regression is linear, each factor's push on the
prediction can be read straight off the model, which keeps it explainable.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
from config import ASSETS, FACTORS, HORIZONS, YEARS_OF_HISTORY  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "data.js"
LOOKBACKS = [5, 20]  # feature windows in trading days


# ---------------------------------------------------------------- data

def all_tickers():
    tickers = {a["ticker"] for a in ASSETS}
    for f in FACTORS.values():
        tickers.update(f["tickers"])
    return sorted(tickers)


def load_market_data():
    import yfinance as yf

    raw = yf.download(all_tickers(), period=f"{YEARS_OF_HISTORY}y",
                      auto_adjust=True, progress=False)["Close"]
    missing = [t for t in all_tickers() if t not in raw or raw[t].dropna().empty]
    if missing:
        print(f"warning: no data for {missing}", file=sys.stderr)
    return raw.sort_index().ffill()


def load_sample_data(seed=7):
    """Simulated prices with realistic links between assets and factors,
    so the whole pipeline and page can be tried without internet access."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=pd.Timestamp.today().normalize(),
                          periods=252 * YEARS_OF_HISTORY)
    n = len(days)

    def ar(vol, phi=0.0):
        e = rng.normal(0, vol, n)
        out = np.zeros(n)
        for i in range(1, n):
            out[i] = phi * out[i - 1] + e[i]
        return out

    r = {  # daily log-returns (or yield changes) of base factors
        "DX-Y.NYB": ar(0.004, 0.05),
        "^TNX": ar(0.05, 0.03),
        "^GSPC": ar(0.010, -0.02),
        "FXI": None, "TIP": None, "IEF": None, "^VIX": None,
    }
    r["FXI"] = 0.6 * r["^GSPC"] + ar(0.012)
    r["IEF"] = -0.06 * r["^TNX"] + ar(0.001)
    r["TIP"] = r["IEF"] + ar(0.0015, 0.1)
    r["^VIX"] = -3.5 * r["^GSPC"] + ar(0.04, -0.05)

    def lagged(x, k=20):  # slow, partly predictable drift
        s = pd.Series(x).rolling(k, min_periods=1).sum().shift(1).fillna(0)
        return s.to_numpy() / k

    infl = r["TIP"] - r["IEF"]
    r["GC=F"] = (-0.45 * r["DX-Y.NYB"] - 0.02 * r["^TNX"] + 0.012 * r["^VIX"]
                 + 1.5 * infl - 0.35 * lagged(r["DX-Y.NYB"]) * 20 * 0.05
                 + 0.03 * lagged(r["^VIX"]) + ar(0.008) + 0.0003)
    r["HG=F"] = (0.35 * r["FXI"] + 0.3 * r["^GSPC"] - 0.3 * r["DX-Y.NYB"]
                 + 0.1 * lagged(r["FXI"]) * 5 + ar(0.012) + 0.0001)
    r["SI=F"] = (1.1 * r["GC=F"] + 0.3 * r["HG=F"] - 0.1 * r["DX-Y.NYB"]
                 + 0.15 * lagged(r["GC=F"]) * 5 + ar(0.011) + 0.0001)
    r["PL=F"] = (0.6 * r["GC=F"] + 0.25 * r["HG=F"] + 0.1 * r["^GSPC"]
                 + ar(0.012))
    r["CL=F"] = (0.6 * r["^GSPC"] - 0.4 * r["DX-Y.NYB"] + 0.01 * r["^VIX"]
                 + 2.0 * infl + 0.1 * lagged(r["^GSPC"]) * 5 + ar(0.02))
    r["NG=F"] = 0.3 * r["CL=F"] + 0.2 * r["^GSPC"] + ar(0.03, 0.02)

    levels = {"DX-Y.NYB": 99.4, "^TNX": 4.12, "^GSPC": 6720, "FXI": 39.8,
              "TIP": 110.6, "IEF": 96.3, "^VIX": 17.4}
    levels.update({a["ticker"]: a["sample_level"] for a in ASSETS})

    df = pd.DataFrame(index=days)
    for t, x in r.items():
        if t == "^TNX":
            path = np.cumsum(x)
            df[t] = np.clip(path - path[-1] + levels[t], 0.3, None)
        elif t == "^VIX":  # mean-reverting fear index
            v = np.zeros(n)
            for i in range(1, n):
                v[i] = 0.97 * v[i - 1] + x[i]
            df[t] = levels[t] * np.exp(v - v[-1])
        else:
            path = np.cumsum(x)
            df[t] = levels[t] * np.exp(path - path[-1])
    return df


def factor_series(prices, key):
    spec = FACTORS[key]
    t = spec["tickers"]
    s = prices[t[0]] if len(t) == 1 else prices[t[0]] / prices[t[1]]
    return s.dropna()


def change(s, k, transform):
    return s.diff(k) if transform == "diff" else s.pct_change(k)


# ---------------------------------------------------------------- model

def build_features(price, factors):
    cols = {}
    groups = {}  # feature column -> factor key (for explanations)
    for k in LOOKBACKS + [60]:
        cols[f"self_{k}"] = price.pct_change(k)
        groups[f"self_{k}"] = "momentum"
    cols["self_vol"] = np.log(price.where(price > 0)).diff().rolling(20).std()
    groups["self_vol"] = "momentum"
    for key, s in factors.items():
        for k in LOOKBACKS:
            c = f"{key}_{k}"
            cols[c] = change(s, k, FACTORS[key]["transform"]).reindex(price.index).ffill()
            groups[c] = key
    return pd.DataFrame(cols), groups


def fit_horizon(X, price, h):
    """Train/test on time order (no peeking at the future), then refit on
    everything and predict from today's features."""
    y = (price.shift(-h) > price).astype(float)
    y[price.shift(-h).isna()] = np.nan
    data = X.join(y.rename("y")).dropna()
    # Gap of h days between train and test so labels don't overlap.
    split = int(len(data) * 0.8)
    train, test = data.iloc[: split - h], data.iloc[split:]

    def model():
        return make_pipeline(StandardScaler(),
                             LogisticRegression(C=0.3, max_iter=1000))

    m = model().fit(train[X.columns], train["y"])
    pred = m.predict(test[X.columns])
    acc = float((pred == test["y"]).mean())
    base = float(max(test["y"].mean(), 1 - test["y"].mean()))
    auc = float(roc_auc_score(test["y"], m.predict_proba(test[X.columns])[:, 1]))
    up = pred == 1
    hit_up = float((test["y"][up] == 1).mean()) if up.any() else None
    period = {"trainFrom": train.index[0].strftime("%Y-%m-%d"),
              "trainTo": train.index[-1].strftime("%Y-%m-%d"),
              "testFrom": test.index[0].strftime("%Y-%m-%d"),
              "testTo": test.index[-1].strftime("%Y-%m-%d"),
              "trainSize": len(train), "testSize": len(test)}

    m = model().fit(data[X.columns], data["y"])
    latest = X.dropna().iloc[[-1]]
    p = float(m.predict_proba(latest)[0, 1])

    scaler, lr = m.named_steps["standardscaler"], m.named_steps["logisticregression"]
    z = scaler.transform(latest)[0]
    contrib = dict(zip(X.columns, lr.coef_[0] * z))
    coefs = dict(zip(X.columns, lr.coef_[0]))
    return {"p": p, "acc": acc, "base": base, "n": len(data), "auc": auc,
            "hitUp": hit_up, "period": period,
            "contrib": contrib, "coefs": coefs}


def forecast_path(price, probs, days=60):
    """Turn up/down probabilities into a price path with an uncertainty band.
    Expected move at each horizon = (2p - 1) x typical size of an N-day move."""
    logp = np.log(price.where(price > 0)).dropna()
    sigma = float(logp.diff().tail(60).std())
    pts = [(0, 0.0)]
    for h, p in sorted(probs.items()):
        typical = float(logp.diff(h).abs().tail(750).mean())
        pts.append((h, (2 * p - 1) * typical))
    xs, ys = zip(*pts)
    dates = pd.bdate_range(price.index[-1], periods=days + 1)[1:]
    last = float(price.iloc[-1])
    path = []
    for i, d in enumerate(dates, start=1):
        mu = float(np.interp(i, xs, ys))
        band = sigma * np.sqrt(i)
        path.append([d.strftime("%Y-%m-%d"), last * np.exp(mu),
                     last * np.exp(mu - band), last * np.exp(mu + band)])
    return path


# ---------------------------------------------------------- explanation

def describe_factor(asset, key, s, price, contrib, corr):
    spec = FACTORS[key]
    recent = change(s, 20, spec["transform"]).iloc[-1]
    if spec["transform"] == "diff":
        move = f"{'rose' if recent > 0 else 'fell'} {abs(recent):.2f} points"
    else:
        move = f"{'rose' if recent > 0 else 'fell'} {abs(recent) * 100:.1f}%"
    rel = ("tends to move with" if corr > 0.15 else
           "tends to move against" if corr < -0.15 else
           "has only a loose day-to-day link with")
    effect = ("supports" if contrib > 0.05 else
              "weighs on" if contrib < -0.05 else "has little effect on")
    return (f"{asset['name']} {rel} {spec['name'].lower()} "
            f"(1-year correlation {corr:+.2f}). Over the last month it {move}. "
            f"The model reads this as something that {effect} the outlook.")


def recommendation(asset, horizons):
    score = 0.25 * horizons[0]["probUp"] + 0.5 * horizons[1]["probUp"] + 0.25 * horizons[2]["probUp"]
    edge = np.mean([h["accuracy"] - h["baseline"] for h in horizons])
    if score >= 0.60:
        label, text = "Bullish", f"The factors point to {asset['name'].lower()} rising. A reasonable time to buy or add."
    elif score >= 0.53:
        label, text = "Mildly bullish", f"Slight upward lean. Consider adding to {asset['name'].lower()} gradually rather than all at once."
    elif score > 0.47:
        label, text = "Neutral", "No clear signal either way. Holding makes sense; there's no strong case to buy or sell."
    elif score > 0.40:
        label, text = "Mildly bearish", "Slight downward lean. Consider waiting before buying, or trimming a large position."
    else:
        label, text = "Bearish", f"The factors point to {asset['name'].lower()} falling. Consider reducing exposure or waiting."
    if edge < 0.02:
        text += (" Note: in back-testing this model was barely better than "
                 "a simple guess, so treat this as weak evidence.")
    return {"label": label, "score": round(float(score), 3), "text": text}


# ---------------------------------------------------------------- main

def series_out(s, n):
    s = s.dropna().tail(n)
    return [[d.strftime("%Y-%m-%d"), round(float(v), 4)] for d, v in s.items()]


def readable(col, asset):
    key, win = col.rsplit("_", 1)
    name = asset["name"] if key == "self" else FACTORS[key]["name"]
    return f"{name} volatility (20d)" if win == "vol" else f"{name} change ({win}d)"


def accuracy_score(horizons):
    """0-100 score: how much better than guessing, averaged over horizons.
    50 = no better than guessing; 100 = right every time."""
    vals = []
    for h in horizons:
        lift = (h["accuracy"] - h["baseline"]) / max(1 - h["baseline"], 1e-6)
        vals.append(50 + 25 * np.clip(lift, -1, 1) + 25 * np.clip((h["auc"] - 0.5) * 2, -1, 1))
    return int(round(float(np.clip(np.mean(vals), 0, 100))))


def run_asset(asset, prices):
    price = prices[asset["ticker"]].dropna()
    factors = {k: factor_series(prices, k) for k in asset["factors"]}
    X, groups = build_features(price, factors)

    horizons, contrib_by_factor = [], {}
    probs = {}
    for h in HORIZONS:
        r = fit_horizon(X, price, h)
        probs[h] = r["p"]
        horizons.append({"days": h, "probUp": round(r["p"], 4),
                         "accuracy": round(r["acc"], 4),
                         "baseline": round(r["base"], 4), "samples": r["n"],
                         "auc": round(r["auc"], 4),
                         "hitRateUp": None if r["hitUp"] is None else round(r["hitUp"], 4),
                         **r["period"]})
        if h == 20:  # explain the 1-month model
            coef_rows = sorted(r["coefs"].items(), key=lambda kv: -abs(kv[1]))
            for col, v in r["contrib"].items():
                contrib_by_factor[groups[col]] = contrib_by_factor.get(groups[col], 0) + v

    rets = np.log(price.where(price > 0)).diff()
    out_factors = []
    for k, s in factors.items():
        fr = change(s, 1, FACTORS[k]["transform"]).reindex(rets.index)
        corr = float(rets.tail(252).corr(fr.tail(252)))
        c = float(contrib_by_factor.get(k, 0.0))
        out_factors.append({
            "id": k, "name": FACTORS[k]["name"], "about": FACTORS[k]["about"],
            "source": " / ".join(FACTORS[k]["tickers"]),
            "correlation": round(corr, 3), "contribution": round(c, 3),
            "explanation": describe_factor(asset, k, s, price, c, corr),
            "series": series_out(s, 260),
        })
    mom = float(contrib_by_factor.get("momentum", 0.0))

    conv = asset["convert"]
    last, prev = float(price.iloc[-1]), float(price.iloc[-2])
    return {
        "id": asset["id"], "name": asset["name"], "symbol": asset["symbol"],
        "ticker": asset["ticker"], "unit": asset["unit"],
        "unitLabel": asset["unit_label"],
        "price": {"perUnit": round(last * conv, 4),
                  "changePct": round(last / prev - 1, 5),
                  "contract": round(last, 4),
                  "asOf": price.index[-1].strftime("%Y-%m-%d")},
        "history": series_out(price * conv, 520),
        "forecast": {
            "horizons": horizons,
            "path": [[d, round(m * conv, 4), round(lo * conv, 4), round(hi * conv, 4)]
                     for d, m, lo, hi in forecast_path(price, probs)],
        },
        "momentum": round(mom, 3),
        "model": {
            "type": "Logistic regression (L2, C=0.3) on standardised features",
            "features": len(X.columns),
            "coefficients": [{"feature": readable(c, asset), "weight": round(float(v), 3)}
                             for c, v in coef_rows],
        },
        "factors": out_factors,
        "recommendation": recommendation(asset, horizons),
        "score": accuracy_score(horizons),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true",
                    help="use simulated data (no internet needed)")
    args = ap.parse_args()

    prices = load_sample_data() if args.sample else load_market_data()
    results = []
    for a in ASSETS:
        try:
            results.append(run_asset(a, prices))
            h = results[-1]["forecast"]["horizons"][1]
            print(f"{a['name']:<12} P(up in 20d)={h['probUp']:.2f}  "
                  f"test acc={h['accuracy']:.2f} vs baseline {h['baseline']:.2f}")
        except Exception as e:  # keep other assets if one feed fails
            print(f"skipping {a['name']}: {e}", file=sys.stderr)

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sample": args.sample,
        "assets": results,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("window.ASSET_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
