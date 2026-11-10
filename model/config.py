"""Assets, the factors that drive them, and where their data comes from.

Every series comes from Yahoo Finance (via yfinance), so one data source
covers prices and factors. Each factor is either a single ticker or a
ratio of two tickers.
"""

TROY_OZ_TO_G = 31.1035
LB_TO_KG = 2.20462

# Factor definitions. `transform` controls how changes are measured:
#   "pct"  - percentage change (prices, indexes)
#   "diff" - absolute change (yields, already in percent)
FACTORS = {
    "usd": {
        "name": "US Dollar",
        "tickers": ["DX-Y.NYB"],
        "transform": "pct",
        "about": "The US Dollar Index (DXY). Commodities are priced in dollars, "
                 "so a stronger dollar usually makes them more expensive for "
                 "everyone else and weighs on prices.",
    },
    "rates": {
        "name": "Interest rates",
        "tickers": ["^TNX"],
        "transform": "diff",
        "about": "The 10-year US Treasury yield. Higher yields raise the "
                 "opportunity cost of holding assets that pay no interest.",
    },
    "inflation": {
        "name": "Inflation",
        "tickers": ["TIP", "IEF"],
        "transform": "pct",
        "about": "Inflation-protected Treasuries (TIP) relative to regular "
                 "Treasuries (IEF). When this ratio rises, the market expects "
                 "more inflation.",
    },
    "geopolitical": {
        "name": "Geopolitical risk",
        "tickers": ["^VIX"],
        "transform": "pct",
        "about": "Measured through the VIX volatility index, which spikes during "
                 "wars, crises and market panics. Safe havens tend to benefit.",
    },
    "equities": {
        "name": "Economic demand",
        "tickers": ["^GSPC"],
        "transform": "pct",
        "about": "The S&P 500, a broad read on growth and risk appetite. "
                 "Stronger growth means more demand for industrial commodities.",
    },
    "china": {
        "name": "China demand",
        "tickers": ["FXI"],
        "transform": "pct",
        "about": "Large-cap Chinese equities (FXI). China consumes about half "
                 "the world's copper, so its economy moves the price.",
    },
    "gold": {
        "name": "Gold price",
        "tickers": ["GC=F"],
        "transform": "pct",
        "about": "Precious metals tend to move together; gold often leads.",
    },
    "copper": {
        "name": "Industrial demand",
        "tickers": ["HG=F"],
        "transform": "pct",
        "about": "Copper futures, a common gauge of global industrial activity.",
    },
    "oil": {
        "name": "Crude oil",
        "tickers": ["CL=F"],
        "transform": "pct",
        "about": "WTI crude oil. Gas and oil compete as fuels and share demand drivers.",
    },
}

ASSETS = [
    {
        "id": "gold", "name": "Gold", "symbol": "Au", "ticker": "GC=F",
        "unit": "g", "unit_label": "Price per gram", "convert": 1 / TROY_OZ_TO_G,
        "factors": ["usd", "geopolitical", "inflation", "rates"],
        "sample_level": 4050.0,
    },
    {
        "id": "silver", "name": "Silver", "symbol": "Ag", "ticker": "SI=F",
        "unit": "g", "unit_label": "Price per gram", "convert": 1 / TROY_OZ_TO_G,
        "factors": ["gold", "usd", "copper", "rates"],
        "sample_level": 48.5,
    },
    {
        "id": "oil", "name": "Crude oil", "symbol": "WTI", "ticker": "CL=F",
        "unit": "bbl", "unit_label": "Price per barrel", "convert": 1.0,
        "factors": ["equities", "usd", "geopolitical", "inflation"],
        "sample_level": 61.2,
    },
    {
        "id": "copper", "name": "Copper", "symbol": "Cu", "ticker": "HG=F",
        "unit": "kg", "unit_label": "Price per kilogram", "convert": LB_TO_KG,
        "factors": ["china", "equities", "usd", "rates"],
        "sample_level": 5.05,
    },
    {
        "id": "platinum", "name": "Platinum", "symbol": "Pt", "ticker": "PL=F",
        "unit": "g", "unit_label": "Price per gram", "convert": 1 / TROY_OZ_TO_G,
        "factors": ["gold", "copper", "usd", "equities"],
        "sample_level": 1560.0,
    },
    {
        "id": "natgas", "name": "Natural gas", "symbol": "NG", "ticker": "NG=F",
        "unit": "MMBtu", "unit_label": "Price per MMBtu", "convert": 1.0,
        "factors": ["oil", "equities", "usd", "geopolitical"],
        "sample_level": 3.55,
    },
]

# Forecast horizons in trading days (~1 week, ~1 month, ~1 quarter).
HORIZONS = [5, 20, 60]
YEARS_OF_HISTORY = 8
