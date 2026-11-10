"""Assets, the factors that drive them, and where each series comes from.

Sources
  yahoo - daily futures / index closes via yfinance
  fred  - official US data from the St. Louis Fed (FRED), no API key needed
  gpr   - Caldara & Iacoviello daily Geopolitical Risk Index
          (counts of war / terror / tension coverage in major newspapers)

`transform` controls how a factor's moves are measured:
  "pct"  - percentage change (prices, indexes)
  "diff" - change in points (yields and spreads, already in percent)

`lag` is how many trading days late the value is published. Features use
the value as it was known on each day, so the model never peeks ahead.
"""

TROY_OZ_TO_G = 31.1035
LB_TO_KG = 2.20462

START = "2005-06-01"
FIRST_TEST_YEAR = 2012  # walk-forward testing runs from here to today

FACTORS = {
    "usd": {
        "name": "US Dollar", "source": ("fred", "DTWEXBGS"), "transform": "pct", "lag": 1,
        "label": "Broad trade-weighted dollar index (Federal Reserve)",
        "about": "The dollar against a basket of major trading partners. Commodities are "
                 "priced in dollars, so a stronger dollar usually weighs on them.",
    },
    "real_rates": {
        "name": "Real interest rates", "source": ("fred", "DFII10"), "transform": "diff", "lag": 1,
        "label": "10-year TIPS yield, % (inflation-adjusted)",
        "about": "The interest rate after inflation. It is the true cost of holding an asset "
                 "that pays no interest, which makes it the classic driver of gold.",
    },
    "inflation": {
        "name": "Inflation expectations", "source": ("fred", "T10YIE"), "transform": "diff", "lag": 1,
        "label": "10-year breakeven inflation rate, %",
        "about": "The inflation rate bond markets expect over the next ten years. "
                 "Real assets are often bought as a hedge when it climbs.",
    },
    "geopolitical": {
        "name": "Geopolitical risk", "source": ("gpr", "GPRD_MA7"), "transform": "pct", "lag": 1,
        "label": "Geopolitical Risk Index, 7-day average (Caldara & Iacoviello)",
        "about": "Measures how much major newspapers write about wars, terrorism and "
                 "military tension. Safe havens and oil tend to react to spikes.",
    },
    "stress": {
        "name": "Financial stress", "source": ("fred", "STLFSI4"), "transform": "diff", "lag": 6,
        "label": "St. Louis Fed Financial Stress Index (0 = normal)",
        "about": "Combines 18 market signals (credit spreads, volatility, funding costs). "
                 "Above zero means markets are under more strain than usual.",
    },
    "curve": {
        "name": "Growth outlook", "source": ("fred", "T10Y2Y"), "transform": "diff", "lag": 1,
        "label": "Yield curve: 10-year minus 2-year Treasury yield, %",
        "about": "A steepening curve usually signals expected growth; an inverted one "
                 "(below zero) has preceded most US recessions.",
    },
    "equities": {
        "name": "Economic demand", "source": ("yahoo", "^GSPC"), "transform": "pct", "lag": 0,
        "label": "S&P 500 index",
        "about": "A broad read on growth and risk appetite. Stronger growth means more "
                 "demand for industrial commodities and fuel.",
    },
    "china": {
        "name": "China demand", "source": ("yahoo", "FXI"), "transform": "pct", "lag": 0,
        "label": "iShares China Large-Cap ETF",
        "about": "China uses about half the world's copper, so its economy moves the price.",
    },
    "gold": {
        "name": "Gold price", "source": ("yahoo", "GC=F"), "transform": "pct", "lag": 0,
        "label": "Gold futures, $/oz",
        "about": "Precious metals tend to move together, and gold usually leads.",
    },
    "copper": {
        "name": "Industrial demand", "source": ("yahoo", "HG=F"), "transform": "pct", "lag": 0,
        "label": "Copper futures, $/lb",
        "about": "Copper is used in almost everything built, so its price is a gauge of "
                 "global industrial activity.",
    },
    "oil": {
        "name": "Crude oil", "source": ("yahoo", "CL=F"), "transform": "pct", "lag": 0,
        "label": "WTI crude oil futures, $/bbl",
        "about": "Oil and gas compete as fuels and share many demand drivers.",
    },
}

ASSETS = [
    {"id": "gold", "name": "Gold", "symbol": "Au", "ticker": "GC=F",
     "unit": "g", "unit_label": "Price per gram", "convert": 1 / TROY_OZ_TO_G,
     "factors": ["real_rates", "usd", "inflation", "geopolitical", "stress"]},
    {"id": "silver", "name": "Silver", "symbol": "Ag", "ticker": "SI=F",
     "unit": "g", "unit_label": "Price per gram", "convert": 1 / TROY_OZ_TO_G,
     "factors": ["gold", "real_rates", "usd", "copper", "inflation"]},
    {"id": "oil", "name": "Crude oil", "symbol": "WTI", "ticker": "CL=F",
     "unit": "bbl", "unit_label": "Price per barrel", "convert": 1.0,
     "factors": ["equities", "usd", "geopolitical", "inflation", "curve"]},
    {"id": "copper", "name": "Copper", "symbol": "Cu", "ticker": "HG=F",
     "unit": "kg", "unit_label": "Price per kilogram", "convert": LB_TO_KG,
     "factors": ["china", "equities", "usd", "curve", "real_rates"]},
    {"id": "platinum", "name": "Platinum", "symbol": "Pt", "ticker": "PL=F",
     "unit": "g", "unit_label": "Price per gram", "convert": 1 / TROY_OZ_TO_G,
     "factors": ["gold", "copper", "usd", "equities", "real_rates"]},
    {"id": "natgas", "name": "Natural gas", "symbol": "NG", "ticker": "NG=F",
     "unit": "MMBtu", "unit_label": "Price per MMBtu", "convert": 1.0,
     "factors": ["oil", "equities", "usd", "geopolitical", "stress"]},
]

# Forecast horizons in trading days (~1 week, ~1 month, ~1 quarter).
HORIZONS = [5, 20, 60]
