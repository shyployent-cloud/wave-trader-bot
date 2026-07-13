"""
Wave Trader Bot — Technical Indicators
=======================================
Pure Python implementations — no cTrader dependencies.
Works on any list/series of OHLC data.
"""


def compute_macd(closes, fast=12, slow=26, signal=9):
    """
    Computes MACD histogram on a list of closing prices.
    Returns dict with current bar values or None if insufficient data.
    """
    if len(closes) < slow + signal:
        return None

    def ema(prices, period):
        k = 2 / (period + 1)
        e = prices[0]
        for p in prices[1:]:
            e = p * k + e * (1 - k)
        return e

    # Build full EMA series
    k12 = 2 / (fast + 1)
    k26 = 2 / (slow + 1)
    k9  = 2 / (signal + 1)

    e12 = e26 = closes[0]
    macd_vals = []

    for c in closes:
        e12 = c * k12 + e12 * (1 - k12)
        e26 = c * k26 + e26 * (1 - k26)
        macd_vals.append(e12 - e26)

    sig = macd_vals[0]
    hist_vals = []
    for m in macd_vals:
        sig = m * k9 + sig * (1 - k9)
        hist_vals.append(m - sig)

    if len(hist_vals) < 2:
        return None

    h_cur  = hist_vals[-1]
    h_prev = hist_vals[-2]
    recent = [abs(h) for h in hist_vals[-20:]]
    h_rng  = sum(recent) / len(recent) if recent else 1e-9
    rel    = abs(h_cur) / h_rng if h_rng > 0 else 0

    return {
        "hist":         h_cur,
        "hist_prev":    h_prev,
        "hist_range":   h_rng,
        "rel_strength": rel,
        "trending_up":  h_cur > h_prev,
        "trending_dn":  h_cur < h_prev,
        "positive":     h_cur > 0,
        "negative":     h_cur < 0,
    }


def macd_confirms(macd_data, direction, mode, threshold=0.30):
    """
    Returns True if MACD condition passes for this variation.

    Modes:
      none             — V5: no filter, always passes
      exclude_counter  — V4a: exclude only strong counter-momentum
      trending         — V4_Loose: must be trending right direction
      correct_side     — V4b: histogram on correct side of zero
      weak_trend       — V4c: trending or near zero
    """
    if macd_data is None:
        return mode == "none"

    if mode == "none":
        return True

    if mode == "trending":
        return (macd_data["trending_up"] if direction == "bull"
                else macd_data["trending_dn"])

    if mode == "correct_side":
        return (macd_data["positive"] if direction == "bull"
                else macd_data["negative"])

    if mode == "weak_trend":
        near_zero = macd_data["rel_strength"] < 0.30
        trending  = (macd_data["trending_up"] if direction == "bull"
                     else macd_data["trending_dn"])
        return trending or near_zero

    if mode == "exclude_counter":
        strongly_counter = (
            (macd_data["trending_dn"] and direction == "bull"
             and macd_data["rel_strength"] > threshold) or
            (macd_data["trending_up"] and direction == "bear"
             and macd_data["rel_strength"] > threshold)
        )
        return not strongly_counter

    return True


def is_engulfing(curr, prev, direction="bull"):
    """
    Detects engulfing candle pattern.
    curr/prev: dicts with open, high, low, close keys.
    """
    co, cc = float(curr["open"]), float(curr["close"])
    po, pc = float(prev["open"]), float(prev["close"])

    if direction == "bull":
        return (pc < po        # prev candle red
                and cc > co    # curr candle green
                and cc > po    # curr close above prev open
                and co < pc)   # curr open below prev close
    else:
        return (pc > po        # prev candle green
                and cc < co    # curr candle red
                and cc < po    # curr close below prev open
                and co > pc)   # curr open above prev close


def get_daily_box(daily_candle):
    """Returns box dict from yesterday's daily candle."""
    bhi = float(daily_candle["high"])
    blo = float(daily_candle["low"])
    if bhi <= blo:
        return None
    return {"high": bhi, "low": blo, "range": bhi - blo}


def check_breakout(close, box):
    """Returns 'bull', 'bear', or None."""
    if close > box["high"]: return "bull"
    if close < box["low"]:  return "bear"
    return None


def near_retest(candle, box, direction, tolerance_pct=0.35):
    """True if candle is within tolerance of the retest level."""
    level = box["high"] if direction == "bull" else box["low"]
    tol   = box["range"] * tolerance_pct
    price = float(candle["low"]) if direction == "bull" else float(candle["high"])
    return abs(price - level) <= tol


def calculate_stake(balance, risk_pct, sl_points, max_stake=2.0):
    """
    Correct spread betting stake calculation.
    stake (£/point) = risk_amount / sl_points
    Capped at max_stake for safety.
    """
    risk_amount = balance * risk_pct
    if sl_points <= 0:
        return None
    raw_stake = risk_amount / sl_points
    return min(raw_stake, max_stake)
