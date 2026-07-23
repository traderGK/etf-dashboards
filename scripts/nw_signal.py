#!/usr/bin/env python3
"""NW crypto strategy journal engine — ETH/USD 4h, Nadaraya-Watson BW=66.

Exact server-side port of GK's TradingView strategy
"AI - LuxAlgo - Nadaraya-Watson Smoothers with Alerts" (script "GK NW test 1"),
non-repainting endpoint mode, long-only:

    w[i]   = exp(-i^2 / (2*h^2)),  i = 0..499   (h = bandwidth = 66)
    out[t] = sum(close[t-i] * w[i]) / sum(w[i])
    colorIsUp[t] = out[t] > out[t-1]
    LONG entry  when colorIsUp flips false -> true   (fill: next 4h bar open)
    LONG exit   when colorIsUp flips true  -> false  (fill: next 4h bar open)

This journal is SEPARATE from the stock-setups book (GK 2026-07-23): its state
lives under the single `nw` key of the KV "latest" object and is never mixed
into hist/stats/open. Tracking starts only at the first fresh buy signal after
`armed_at` — an uptrend already in progress when armed is ignored.

Data: Kraken public OHLC (ETH/USD, interval=240, ~720 bars) with a Yahoo
ETH-USD 1h→4h resample fallback. Both are UTC-aligned like TV crypto bars.
Net P&L includes 0.1% commission per side (matches the backtest).
"""
import json
import math
import time
import urllib.request
from datetime import datetime, timezone

BW = 66
WINDOW = 500                      # Pine: i = 0..499
BAR_SEC = 4 * 3600
FEE = 0.001                       # 0.1% per side, as in the backtest
JOURNAL_CAP = 400

_W = [math.exp(-(i * i) / (2.0 * BW * BW)) for i in range(WINDOW)]
_DEN = sum(_W)


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# ── data feeds ───────────────────────────────────────────────────────────────

def fetch_kraken(now=None):
    """Closed 4h bars (ts_ms, open, close) oldest→newest + in-progress bar open."""
    url = "https://api.kraken.com/0/public/OHLC?pair=ETHUSD&interval=240"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.load(r)
    if d.get("error"):
        raise RuntimeError(f"kraken: {d['error']}")
    rows = next(v for k, v in d["result"].items() if k != "last")
    now = now or time.time()
    bars, live_open = [], None
    for row in rows:
        ts, o, c = int(row[0]), float(row[1]), float(row[4])
        if ts + BAR_SEC <= now:
            bars.append((ts * 1000, o, c))
        else:
            live_open = (ts * 1000, o)
    return bars, live_open, "kraken"


def fetch_yahoo(now=None):
    """Fallback: Yahoo ETH-USD 1h chart API resampled to UTC-aligned 4h bars."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/ETH-USD"
           "?interval=1h&range=180d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    buckets = {}
    for i, t in enumerate(ts):
        o, c = q["open"][i], q["close"][i]
        if o is None or c is None:
            continue
        b = (t // BAR_SEC) * BAR_SEC
        if b not in buckets:
            buckets[b] = [o, c]
        else:
            buckets[b][1] = c
    now = now or time.time()
    bars, live_open = [], None
    for b in sorted(buckets):
        if b + BAR_SEC <= now:
            bars.append((b * 1000, buckets[b][0], buckets[b][1]))
        else:
            live_open = (b * 1000, buckets[b][0])
    return bars, live_open, "yahoo"


def fetch_bars():
    try:
        return fetch_kraken()
    except Exception:
        return fetch_yahoo()


# ── NW math ──────────────────────────────────────────────────────────────────

def nw_out(closes, t):
    """Endpoint NW estimate at bar index t (needs t >= WINDOW-1)."""
    s = 0.0
    for i in range(WINDOW):
        s += closes[t - i] * _W[i]
    return s / _DEN


def flip_events(bars):
    """All entry/exit signal events computable from `bars`.

    Returns [(signal_bar_ts_ms, 'entry'|'exit', signal_bar_index)], oldest first.
    Signals exist for t >= WINDOW+1 (need out[t], out[t-1], colorIsUp[t-1]).
    """
    closes = [b[2] for b in bars]
    n = len(closes)
    if n < WINDOW + 2:
        return [], None
    outs = {t: nw_out(closes, t) for t in range(WINDOW - 1, n)}
    events = []
    for t in range(WINDOW + 1, n):
        up, up_prev = outs[t] > outs[t - 1], outs[t - 1] > outs[t - 2]
        if up and not up_prev:
            events.append((bars[t][0], "entry", t))
        elif up_prev and not up:
            events.append((bars[t][0], "exit", t))
    last = {"out": round(outs[n - 1], 2), "out_prev": round(outs[n - 2], 2),
            "dir": "up" if outs[n - 1] > outs[n - 2] else "down"}
    return events, last


# ── journal state machine ────────────────────────────────────────────────────

def update_nw(prev, now_ms=None):
    """Advance the NW journal one refresh cycle. Never raises on feed trouble —
    caller keeps `prev` if this throws. `prev` is the previous `nw` KV object."""
    now_ms = now_ms or int(time.time() * 1000)
    bars, live_open, src = fetch_bars()
    if len(bars) < WINDOW + 2:
        raise RuntimeError(f"only {len(bars)} closed bars from {src}")

    st = dict(prev) if isinstance(prev, dict) else {}
    st.setdefault("v", 1)
    st.setdefault("strategy", "Nadaraya-Watson BW66")
    st.setdefault("symbol", "ETH/USD")
    st.setdefault("tf", "4h")
    st.setdefault("armed_at", now_ms)          # first run: arm NOW, no backfill
    st.setdefault("status", "waiting")         # waiting | long
    st.setdefault("journal", [])
    # Ignore every signal bar already CLOSED at arming time (no backfill), but
    # let the bar currently forming produce the first signal when it closes.
    st.setdefault("last_bar", bars[-1][0])

    events, line = flip_events(bars)

    def fill_after(idx):
        """Fill price/ts for a signal on closed bar idx = next bar's open."""
        if idx + 1 < len(bars):
            return bars[idx + 1][0], bars[idx + 1][1]
        if live_open:
            return live_open
        return bars[idx][0] + BAR_SEC * 1000, bars[idx][2]  # approx: signal close

    for ts, kind, idx in events:
        if ts <= st["last_bar"]:
            continue
        if kind == "entry" and st["status"] == "waiting":
            f_ts, f_px = fill_after(idx)
            st["status"] = "long"
            st["pos"] = {"entry_ts": f_ts, "entry": round(f_px, 2),
                         "entry_iso": _iso(f_ts), "signal_ts": ts}
        elif kind == "exit" and st["status"] == "long":
            f_ts, f_px = fill_after(idx)
            pos = st.pop("pos", None) or {}
            entry = pos.get("entry") or f_px
            net = (f_px * (1 - FEE)) / (entry * (1 + FEE)) - 1
            st["journal"].insert(0, {
                "entry_ts": pos.get("entry_ts"), "entry_iso": pos.get("entry_iso"),
                "entry": entry,
                "exit_ts": f_ts, "exit_iso": _iso(f_ts), "exit": round(f_px, 2),
                "pnl_pct": round(net * 100, 2),
                "bars": int((f_ts - pos.get("entry_ts", f_ts)) / (BAR_SEC * 1000)),
            })
            st["journal"] = st["journal"][:JOURNAL_CAP]
            st["status"] = "waiting"
        st["last_bar"] = max(st["last_bar"], ts)

    # even with no events, advance last_bar so a >36-day gap is detectable
    st["last_bar"] = max(st["last_bar"], bars[-1][0])

    # live display fields
    px = live_open[1] if live_open else bars[-1][2]
    st["px"] = round(px, 2)
    st["px_ts"] = now_ms
    st["line"] = line
    st["src"] = src
    st["armed_iso"] = _iso(st["armed_at"])
    if st["status"] == "long" and st.get("pos"):
        e = st["pos"]["entry"]
        st["pos"]["upnl_pct"] = round(((px * (1 - FEE)) / (e * (1 + FEE)) - 1) * 100, 2)
    # summary stats over the journal
    j = st["journal"]
    wins = [r for r in j if r["pnl_pct"] > 0]
    cum = 1.0
    for r in j:
        cum *= 1 + r["pnl_pct"] / 100
    st["stats"] = {"n": len(j), "wins": len(wins),
                   "winRate": round(len(wins) / len(j) * 100, 1) if j else None,
                   "cumPct": round((cum - 1) * 100, 2) if j else 0.0}
    return st


if __name__ == "__main__":
    prev = None
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            prev = json.load(f)
    print(json.dumps(update_nw(prev), indent=1))
