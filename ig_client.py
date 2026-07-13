"""
Wave Trader Bot — IG Markets API Client
=========================================
Wrapper around the trading-ig library.
Handles authentication, price fetching and order placement.
Uses v2 sessions (simple, long-lived tokens).
"""

import logging
import time
from datetime import datetime, timezone, timedelta

log = logging.getLogger("WaveTrader.IG")


class IGClient:
    """
    Wraps trading-ig IGService for our specific needs.
    Provides clean methods for:
      - Authentication
      - Fetching OHLC candles (daily, 1h, 15m, 5m)
      - Checking open positions
      - Placing and closing orders
      - Account balance
    """

    def __init__(self, username, password, api_key, acc_type, acc_id):
        from trading_ig import IGService
        self.acc_id  = acc_id
        self.service = IGService(
            username, password, api_key, acc_type,
            use_rate_limiter=True
        )
        self._connected = False

    def connect(self):
        """Authenticate and switch to correct account."""
        log.info("Connecting to IG Markets...")
        self.service.create_session(version="2")
        # Switch to specified account
        self.service.switch_account(self.acc_id, default_account=True)
        self._connected = True
        log.info(f"Connected ✓ | Account: {self.acc_id}")

    def get_balance(self):
        """Returns current account balance in account currency."""
        acc = self.service.fetch_accounts()
        for a in acc["accounts"]:
            if a["accountId"] == self.acc_id:
                return float(a["balance"]["balance"])
        return 0.0

    def get_candles(self, epic, resolution, num_points=100):
        """
        Fetches historical OHLC candles.
        resolution: "DAY", "HOUR", "MINUTE_15", "MINUTE_5", "MINUTE"
        Returns list of dicts: open, high, low, close, volume
        """
        try:
            result = self.service.fetch_historical_prices_by_epic_and_num_points(
                epic, resolution, num_points
            )
            prices = result["prices"]
            candles = []
            for p in prices:
                candles.append({
                    "datetime": p["snapshotTime"],
                    "open":  float(p["openPrice"]["bid"] or 0),
                    "high":  float(p["highPrice"]["bid"] or 0),
                    "low":   float(p["lowPrice"]["bid"] or 0),
                    "close": float(p["closePrice"]["bid"] or 0),
                })
            return candles
        except Exception as e:
            log.error(f"get_candles({epic}, {resolution}): {e}")
            return []

    def get_market_info(self, epic):
        """Returns market details including min stake and dealing rules."""
        try:
            return self.service.fetch_market_by_epic(epic)
        except Exception as e:
            log.error(f"get_market_info({epic}): {e}")
            return None

    def get_open_positions(self, label=None):
        """Returns list of open positions, optionally filtered by label."""
        try:
            result = self.service.fetch_open_positions()
            positions = result.get("positions", [])
            if label:
                positions = [p for p in positions
                             if p.get("position", {}).get("dealReference", "").startswith(label)]
            return positions
        except Exception as e:
            log.error(f"get_open_positions: {e}")
            return []

    def has_open_position(self, epic):
        """True if there is already an open position for this epic."""
        try:
            result   = self.service.fetch_open_positions()
            for pos in result.get("positions", []):
                if pos.get("market", {}).get("epic") == epic:
                    return True
            return False
        except Exception as e:
            log.error(f"has_open_position({epic}): {e}")
            return False

    def place_order(self, epic, direction, size, sl_distance,
                    tp_distance, currency="GBP"):
        """
        Places a market order with stop loss and take profit.

        direction:   "BUY" or "SELL"
        size:        stake in £ per point (spread betting)
        sl_distance: stop loss distance in points
        tp_distance: take profit distance in points
        """
        try:
            result = self.service.create_open_position(
                currency_code     = currency,
                direction         = direction,
                epic              = epic,
                expiry            = "DFB",  # DFB = Daily Funded Bet (spread betting)
                force_open        = True,
                guaranteed_stop   = False,
                level             = None,
                limit_distance    = tp_distance,
                limit_level       = None,
                order_type        = "MARKET",
                quote_id          = None,
                size              = size,
                stop_distance     = sl_distance,
                stop_level        = None,
                trailing_stop     = False,
                trailing_stop_increment = None,
            )
            log.info(f"Order placed: {result}")
            return result
        except Exception as e:
            log.error(f"place_order({epic}, {direction}, {size}): {e}")
            return None

    def close_all_positions(self, epic):
        """Closes all open positions for a given epic."""
        try:
            result = self.service.fetch_open_positions()
            for pos in result.get("positions", []):
                if pos.get("market", {}).get("epic") == epic:
                    deal_id   = pos["position"]["dealId"]
                    direction = "SELL" if pos["position"]["direction"] == "BUY" else "BUY"
                    size      = pos["position"]["size"]
                    self.service.close_open_position(
                        deal_id        = deal_id,
                        direction      = direction,
                        epic           = epic,
                        expiry         = "-",
                        level          = None,
                        order_type     = "MARKET",
                        quote_id       = None,
                        size           = size,
                    )
                    log.info(f"Closed position {deal_id} on {epic}")
        except Exception as e:
            log.error(f"close_all_positions({epic}): {e}")
