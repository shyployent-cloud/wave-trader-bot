"""
Wave Trader Bot — Main Entry Point
=====================================
Break & Bounce + 1h MACD Confluence Strategy
Runs on IG Markets demo/live via REST API

Strategy:
  1. Build daily box from yesterday's high/low
  2. Wait for 15m breakout of box within 2.5h of daily open
  3. Enter on 5m engulfing candle at retest level
  4. MACD histogram filter on 1h confirms direction
  5. Exit: TP = 3x SL distance (or EOD close)

Safety rules:
  - One trade per asset per session maximum
  - Live position check before every entry
  - Hard stake cap of £2/point
  - Full logging of every decision
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timezone, timedelta

import config
from ig_client import IGClient
from indicators import (
    compute_macd, macd_confirms, is_engulfing,
    get_daily_box, check_breakout, near_retest, calculate_stake
)

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log"),
    ]
)
log = logging.getLogger("WaveTrader")


# ── Per-asset state ───────────────────────────────────────────────────
def make_state(asset):
    return {
        "name":         asset["name"],
        "epic":         asset["epic"],
        "mode":         asset["mode"],
        "daily_box":    None,
        "breakout_dir": None,
        "status":       "WAITING",   # WAITING → BREAKOUT → IN_TRADE
        "session_key":  None,
        "traded_today": False,
    }


# ── Timing helpers ────────────────────────────────────────────────────
def get_session_key():
    """
    Returns a session key that changes at 23:00 UTC each day.
    This correctly groups the 23:00 Monday open with 00:00 Tuesday
    into the same trading session.
    """
    t = datetime.now(timezone.utc)
    if t.hour >= config.SESSION_OPEN_HOUR:
        return t.strftime("%Y-%m-%d") + "_session"
    else:
        yesterday = (t - timedelta(days=1)).strftime("%Y-%m-%d")
        return yesterday + "_session"


def in_window():
    """
    True if current UTC time is within the 2.5h trading window.
    Window: 23:00 UTC → 01:30 UTC
    """
    t   = datetime.now(timezone.utc)
    hrs = t.hour + t.minute / 60.0
    return hrs >= 23.0 or hrs <= 1.5


# ── Core strategy check ───────────────────────────────────────────────
def check_asset(ig, state, balance):
    """
    Runs one strategy check cycle for a single asset.
    Called every CHECK_INTERVAL seconds for each active asset.
    """
    name = state["name"]
    epic = state["epic"]

    # ── Reset on new session ─────────────────────────────────────────
    key = get_session_key()
    if key != state["session_key"]:
        state["session_key"]  = key
        state["daily_box"]    = None
        state["breakout_dir"] = None
        state["status"]       = "WAITING"
        state["traded_today"] = False
        log.info(f"[{name}] New session — reset")

    # ── Safety: check live positions every cycle ──────────────────────
    if ig.has_open_position(epic):
        return  # Already in trade — cTrader manages SL/TP

    if state["traded_today"]:
        return  # One trade per session rule

    if not in_window():
        return  # Outside trading window

    # ── Step 1: Build daily box ───────────────────────────────────────
    if state["daily_box"] is None:
        candles_d = ig.get_candles(epic, "DAY", 3)
        if len(candles_d) < 2:
            log.debug(f"[{name}] Not enough daily bars")
            return
        box = get_daily_box(candles_d[-2])  # Yesterday's candle
        if box is None:
            return
        state["daily_box"] = box
        log.info(f"[{name}] Box H={box['high']:.4f} L={box['low']:.4f} "
                 f"R={box['range']:.4f}")

    box = state["daily_box"]

    # ── Step 2: 15m breakout ─────────────────────────────────────────
    if state["status"] == "WAITING":
        candles_15 = ig.get_candles(epic, "MINUTE_15", 5)
        if not candles_15:
            return
        close = candles_15[-1]["close"]
        bdir  = check_breakout(close, box)
        if bdir:
            state["breakout_dir"] = bdir
            state["status"]       = "BREAKOUT"
            log.info(f"[{name}] BREAKOUT {bdir.upper()} at {close:.4f}")

    # ── Step 3: 5m engulfing at retest ───────────────────────────────
    if state["status"] == "BREAKOUT":
        candles_5 = ig.get_candles(epic, "MINUTE_5", 5)
        if len(candles_5) < 2:
            return

        curr = candles_5[-1]
        prev = candles_5[-2]
        bdir = state["breakout_dir"]

        # Near retest level?
        if not near_retest(curr, box, bdir, config.TOLERANCE_PCT):
            return

        # Engulfing pattern?
        if not is_engulfing(curr, prev, bdir):
            return

        log.info(f"[{name}] Engulfing at retest ✓")

        # MACD confluence on 1h
        candles_1h = ig.get_candles(epic, "HOUR", 60)
        closes_1h  = [c["close"] for c in candles_1h]
        macd_data  = compute_macd(closes_1h)

        if not macd_confirms(macd_data, bdir, state["mode"],
                             config.MACD_THRESHOLD):
            log.info(f"[{name}] MACD rejected ({state['mode']})")
            return

        log.info(f"[{name}] MACD confirmed ✓")

        # ── Trade sizing ─────────────────────────────────────────────
        # SL distance in points from entry
        if bdir == "bull":
            entry    = float(prev["high"])
            sl_level = float(curr["low"]) * 0.999
        else:
            entry    = float(prev["low"])
            sl_level = float(curr["high"]) * 1.001

        sl_points = abs(entry - sl_level)
        tp_points = sl_points * config.RR_TARGET

        if sl_points <= 0:
            log.warning(f"[{name}] Invalid SL distance")
            return

        # ── FIX: Correct spread betting stake calculation ─────────────
        stake = calculate_stake(
            balance    = balance,
            risk_pct   = config.RISK_PCT,
            sl_points  = sl_points,
            max_stake  = config.MAX_STAKE
        )

        if stake is None or stake <= 0:
            log.warning(f"[{name}] Invalid stake")
            return

        direction = "BUY" if bdir == "bull" else "SELL"

        log.info(f"[{name}] PLACING ORDER → {direction} | "
                 f"entry≈{entry:.4f} | "
                 f"SL={sl_points:.2f}pts | "
                 f"TP={tp_points:.2f}pts | "
                 f"stake=£{stake:.4f}/pt | "
                 f"risk=£{stake*sl_points:.2f}")

        result = ig.place_order(
            epic        = epic,
            direction   = direction,
            size        = round(stake, 2),
            sl_distance = round(sl_points, 2),
            tp_distance = round(tp_points, 2),
        )

        if result:
            state["status"]       = "IN_TRADE"
            state["traded_today"] = True
            log.info(f"[{name}] ORDER PLACED ✓ | ref={result}")

            # Log to trades file
            with open("trades.log", "a") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "asset":     name,
                    "epic":      epic,
                    "direction": direction,
                    "entry":     entry,
                    "sl_pts":    sl_points,
                    "tp_pts":    tp_points,
                    "stake":     stake,
                    "risk_gbp":  round(stake * sl_points, 2),
                }) + "\n")


# ── Epic validation ───────────────────────────────────────────────────
def validate_epics(ig, assets):
    """
    Checks each EPIC is valid and logs market info.
    Helps confirm correct spread betting instrument.
    """
    log.info("Validating EPICs...")
    valid = []
    for asset in assets:
        info = ig.get_market_info(asset["epic"])
        if info is None:
            log.warning(f"  {asset['name']}: EPIC {asset['epic']} not found — SKIP")
            continue
        instrument = info.get("instrument", {})
        dealing    = info.get("dealingRules", {})
        name_ig    = instrument.get("name", "unknown")
        min_size   = dealing.get("minDealSize", {}).get("value", "?")
        log.info(f"  ✓ {asset['name']}: {name_ig} | "
                 f"min stake={min_size} | epic={asset['epic']}")
        valid.append(asset)
    return valid


# ── Main loop ─────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  Wave Trader Bot — IG Markets")
    log.info("  Strategy: Break & Bounce + 1h MACD Confluence")
    log.info(f"  Account: {config.IG_ACC_ID} ({config.IG_ACC_TYPE})")
    log.info(f"  Risk: {config.RISK_PCT*100:.0f}%/trade | "
             f"RR: {config.RR_TARGET}:1 | "
             f"MaxStake: £{config.MAX_STAKE}/pt")
    log.info("=" * 60)

    # Validate config
    if not config.IG_USERNAME or not config.IG_API_KEY:
        log.error("IG credentials not set — check Railway environment variables")
        sys.exit(1)

    # Connect
    ig = IGClient(
        username = config.IG_USERNAME,
        password = config.IG_PASSWORD,
        api_key  = config.IG_API_KEY,
        acc_type = config.IG_ACC_TYPE,
        acc_id   = config.IG_ACC_ID,
    )

    try:
        ig.connect()
    except Exception as e:
        log.error(f"Connection failed: {e}")
        sys.exit(1)

    # Get balance
    balance = ig.get_balance()
    log.info(f"Balance: £{balance:,.2f}")

    # Validate EPICs — log market info and filter to valid only
    active_assets = [a for a in config.ASSETS if a["active"]]
    valid_assets  = validate_epics(ig, active_assets)

    if not valid_assets:
        log.error("No valid assets found — check EPICs in config.py")
        sys.exit(1)

    # Initialise state per asset
    states = {a["epic"]: make_state(a) for a in valid_assets}

    log.info(f"Monitoring {len(states)} assets: "
             f"{', '.join(s['name'] for s in states.values())}")
    log.info(f"Check interval: {config.CHECK_INTERVAL}s")
    log.info("Bot running — waiting for trading window (23:00-01:30 UTC)")

    # Main loop
    try:
        while True:
            cycle_start = time.time()

            # Refresh balance every cycle
            try:
                balance = ig.get_balance()
            except Exception as e:
                log.warning(f"Balance refresh failed: {e}")

            # Check each asset
            for epic, state in states.items():
                try:
                    check_asset(ig, state, balance)
                except Exception as e:
                    log.error(f"[{state['name']}] Cycle error: {e}")

            # Sleep
            elapsed    = time.time() - cycle_start
            sleep_time = max(0, config.CHECK_INTERVAL - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        log.info("Bot stopped — all positions remain open, manage manually")


if __name__ == "__main__":
    main()
