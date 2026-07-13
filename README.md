# Wave Trader Bot — IG Markets

Break & Bounce + 1h MACD Confluence strategy running on IG Markets demo/live.

## Setup

### 1. Railway Environment Variables
Set these in Railway → Your Service → Variables:
```
IG_USERNAME   your IG login username
IG_PASSWORD   your IG account password
IG_API_KEY    your demo API key (from IG Settings → API Keys)
IG_ACC_TYPE   DEMO
IG_ACC_ID     your demo account ID (e.g. ZT12345)
```

### 2. Confirm EPICs
On first run the bot logs all market info for each EPIC.
Check the logs to confirm correct spread betting instruments.
Update config.py if any EPIC needs correcting.

### 3. Switch to Live
When ready:
- Change IG_ACC_TYPE to LIVE
- Update IG_ACC_ID to live account ID
- Generate live API key and update IG_API_KEY

## Strategy Rules
- Box: yesterday's daily high/low
- Breakout: 15m candle close outside box
- Entry: 5m engulfing candle at retest level
- MACD: 1h histogram filter (V4a — exclude counter-momentum)
- Exit: TP = 3x SL (managed by IG), EOD close if not hit
- Risk: 1% of account per trade, max £2/point stake

## Assets (commodity session 23:00-01:30 UTC)
- Gold
- Copper
- Silver
- Crude Oil
- Natural Gas
