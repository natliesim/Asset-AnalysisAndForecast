# Asset Analysis & Forecast

A clean, white webpage that forecasts gold, silver, oil, copper, platinum and
natural gas with machine learning, and explains *why* through the factors that
drive each market (US dollar, interest rates, inflation, geopolitical risk,
demand).

## How it works

1. `model/train.py` downloads ~8 years of daily prices from Yahoo Finance for
   each asset and its factors (tickers are in `model/config.py`).
2. For each asset it trains a **logistic regression** per horizon
   (1 week, 1 month, 3 months) that predicts: *will the price be higher?*
   Inputs are recent moves in each factor plus the asset's own momentum.
3. The model is tested on the latest 20% of history it never saw; that accuracy
   and a naive baseline are shown on the page so you can judge how much to trust it.
4. Because the model is linear, each factor's push up or down is read directly
   from its coefficients and shown next to the factor.
5. Results are written to `data/data.js`, which the page reads.

| Factor | Proxy |
| --- | --- |
| US Dollar | DXY index (`DX-Y.NYB`) |
| Interest rates | 10-year Treasury yield (`^TNX`) |
| Inflation | TIP / IEF ratio (inflation expectations) |
| Geopolitical risk | VIX volatility index |
| Demand | S&P 500, China large caps (FXI), copper |

## Run it

```bash
pip install -r requirements.txt
python model/train.py          # live market data
python model/train.py --sample # simulated data, no internet needed
open index.html                # or: python -m http.server
```

The committed `data/data.js` holds real market data. If you run with
`--sample`, the page shows a banner saying the data is simulated.

## Keep it up to date

`.github/workflows/update-forecasts.yml` re-trains every weekday after the US
close and commits fresh data. Turn on GitHub Pages (Settings → Pages → deploy
from branch) to host the site for free.

## Add an asset

Add an entry to `ASSETS` in `model/config.py` with its Yahoo ticker, unit
conversion and factor list, then re-run the script.

*Educational tool, not financial advice.*
