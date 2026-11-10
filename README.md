# Asset Analysis & Forecast

A clean, white webpage that analyses and forecasts gold, silver, oil, copper,
platinum and natural gas with machine learning, and explains each forecast
through the factors that drive the market.

## Data (~20 years, daily)

| Factor | Series | Source |
| --- | --- | --- |
| US Dollar | Broad trade-weighted dollar index (`DTWEXBGS`) | FRED |
| Real interest rates | 10-year TIPS yield (`DFII10`) | FRED |
| Inflation expectations | 10-year breakeven inflation (`T10YIE`) | FRED |
| Financial stress | St. Louis Fed Financial Stress Index (`STLFSI4`) | FRED |
| Growth outlook | 10y − 2y Treasury yield curve (`T10Y2Y`) | FRED |
| Geopolitical risk | Daily Geopolitical Risk Index, 7-day avg | Caldara & Iacoviello |
| Demand | S&P 500, China large caps (FXI), copper, oil | Yahoo Finance |
| Asset prices | Gold, silver, oil, copper, platinum, gas futures | Yahoo Finance |

Each factor is delayed by its publication lag, so the model only uses values
that were actually known on each day.

## How it works (`model/train.py`)

1. **Factor analysis.** For every asset/factor pair: correlation since 2006
   and over the last year, whether the factor's last month predicted the
   asset's next month, a 1-year rolling correlation showing how the link
   changed, and the asset's average next-month return after the factor's
   biggest rises, biggest falls, and quiet months.
2. **Models.** Logistic regression, gradient-boosted trees
   (scikit-learn `HistGradientBoostingClassifier`) and an ensemble of both
   predict whether the price is higher in 3, 6 and 12 months.
   Inputs: 1, 3, 6 and 12-month changes in each factor, each factor's level
   vs its past 1 and 3 years (and the raw level for interest rates), and the
   asset's own 1–12 month returns, volatility, distance from its 200-day
   average and position vs its past 3 years.
3. **Walk-forward testing.** For each year since 2012, models train only on
   earlier data (with a gap so labels never overlap) and predict that year.
   "Guessing" is the better of a coin flip and always picking the usual
   outcome. The best model per horizon makes today's forecast, with its
   probabilities calibrated against its own walk-forward record.
5. **Evidence rating.** Overlapping forecasts are nearly the same bet, so
   each horizon is also scored on non-overlapping forecasts only, with a
   binomial test against guessing: *Solid* (p < 0.05), *Suggestive*
   (p < 0.2) or *Could be luck*.
6. **Explanations.** Each factor's push on today's forecast (probability with
   vs without that factor at a typical value), permutation importance over the
   last 3 years, and logistic regression weights.

Accuracy score (0–100): 50 = guessing. Half from AUC (0.70 = full marks), half
from accuracy gained over guessing (+15 points = full marks).

## Run it

```bash
pip install -r requirements.txt
python model/train.py   # ~3 minutes; writes data/data.js
open index.html         # or: python -m http.server
```

`.github/workflows/update-forecasts.yml` re-runs this every weekday once
merged into the default branch.

*Educational tool, not financial advice.*
