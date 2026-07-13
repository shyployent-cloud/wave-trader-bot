"""
Wave Trader Bot — IG Markets Configuration
==========================================
All credentials loaded from environment variables.
Safe to commit to public GitHub — no secrets in this file.

Set these in Railway dashboard → Variables:
  IG_USERNAME     your IG login username/email
  IG_PASSWORD     your IG account password
  IG_API_KEY      your demo API key
  IG_ACC_TYPE     DEMO or LIVE
  IG_ACC_ID       your account ID (e.g. ZT12345)
"""

import os

# ── IG Credentials ────────────────────────────────────────────────────
IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")
IG_API_KEY  = os.environ.get("IG_API_KEY",  "")
IG_ACC_TYPE = os.environ.get("IG_ACC_TYPE", "DEMO")  # DEMO or LIVE
IG_ACC_ID   = os.environ.get("IG_ACC_ID",  "")

# ── API Endpoints ─────────────────────────────────────────────────────
# Automatically selects demo or live based on IG_ACC_TYPE
BASE_URL = (
    "https://demo-api.ig.com/gateway/deal"
    if IG_ACC_TYPE == "DEMO"
    else "https://api.ig.com/gateway/deal"
)

# ── Strategy Parameters ───────────────────────────────────────────────
WINDOW_HOURS   = 2.5    # Hours from daily open to scan for setups
RR_TARGET      = 3.0    # Take profit = 3x stop loss distance
TOLERANCE_PCT  = 0.35   # Retest tolerance = 35% of yesterday's range
RISK_PCT       = 0.01   # Risk 1% of account per trade
MAX_STAKE      = 2.0    # Hard cap: max £2 per point (safety)
MACD_THRESHOLD = 0.30   # V4a: exclude counter-momentum above 30%
LABEL          = "WaveTrader"

# ── Asset Configuration ───────────────────────────────────────────────
# EPICs to be confirmed once connected to IG demo
# Format: name, epic, macd_mode, session_open_utc
# session_open_utc = hour when daily candle opens on IG platform
ASSETS = [
    {
        "name":     "Gold",
        "epic":     "CS.D.CFDGOLD.CFDGD.IP",   # confirm via API
        "mode":     "exclude_counter",
        "active":   True,
    },
    {
        "name":     "Copper",
        "epic":     "CS.D.COPPER.MONTH1.IP",    # confirm via API
        "mode":     "trending",
        "active":   True,
    },
    {
        "name":     "Silver",
        "epic":     "CS.D.SILVER.CFDSILVER.IP", # confirm via API
        "mode":     "exclude_counter",
        "active":   True,
    },
    {
        "name":     "Crude Oil",
        "epic":     "CS.D.CRUDE.MONTH1.IP",     # confirm via API
        "mode":     "exclude_counter",
        "active":   True,
    },
    {
        "name":     "Natural Gas",
        "epic":     "CS.D.NATGAS.MONTH1.IP",    # confirm via API
        "mode":     "exclude_counter",
        "active":   True,
    },
]

# ── Timing ────────────────────────────────────────────────────────────
SESSION_OPEN_HOUR = 23   # Commodity daily candle opens 23:00 UTC
CHECK_INTERVAL    = 60   # Seconds between strategy checks
LOG_LEVEL         = "INFO"
