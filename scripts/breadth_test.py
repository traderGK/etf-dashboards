#!/usr/bin/env python3
"""Breadth Monitor generator -> test/index.html (unlinked test page).

Computes market-breadth internals from Yahoo daily closes over an
~S&P-100 mega/large-cap panel + 11 SPDR sector ETFs + 18 country ETFs:
  % above 20/50/200-day SMA, advance/decline line, McClellan oscillator,
  Zweig breadth thrust, 52-week highs/lows, equal-weight & small-cap
  leadership ratios, sector participation, global breadth, and a
  rules-based regime label.

Run:  python3 scripts/breadth_test.py   (writes test/index.html)
Standalone — does NOT touch data.json or the trading engine.
"""
import math
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------- universe
PANEL = {
    # ticker: sector ETF
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AVGO": "XLK", "ORCL": "XLK",
    "CRM": "XLK", "ADBE": "XLK", "AMD": "XLK", "CSCO": "XLK", "ACN": "XLK",
    "IBM": "XLK", "INTC": "XLK", "QCOM": "XLK", "TXN": "XLK", "NOW": "XLK",
    "INTU": "XLK", "PLTR": "XLK", "MU": "XLK",
    "GOOGL": "XLC", "META": "XLC", "NFLX": "XLC", "DIS": "XLC",
    "CMCSA": "XLC", "T": "XLC", "VZ": "XLC",
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY", "NKE": "XLY",
    "LOW": "XLY", "SBUX": "XLY", "BKNG": "XLY", "TJX": "XLY", "GM": "XLY",
    "BRK-B": "XLF", "JPM": "XLF", "V": "XLF", "MA": "XLF", "BAC": "XLF",
    "WFC": "XLF", "GS": "XLF", "MS": "XLF", "C": "XLF", "AXP": "XLF",
    "BLK": "XLF", "SCHW": "XLF", "COF": "XLF", "MET": "XLF", "AIG": "XLF",
    "BK": "XLF", "USB": "XLF", "PYPL": "XLF",
    "LLY": "XLV", "UNH": "XLV", "JNJ": "XLV", "ABBV": "XLV", "MRK": "XLV",
    "TMO": "XLV", "ABT": "XLV", "DHR": "XLV", "PFE": "XLV", "AMGN": "XLV",
    "ISRG": "XLV", "MDT": "XLV", "BMY": "XLV", "GILD": "XLV", "CVS": "XLV",
    "ELV": "XLV", "CI": "XLV",
    "GE": "XLI", "CAT": "XLI", "RTX": "XLI", "HON": "XLI", "UNP": "XLI",
    "BA": "XLI", "UPS": "XLI", "LMT": "XLI", "DE": "XLI", "ETN": "XLI",
    "EMR": "XLI", "FDX": "XLI", "GD": "XLI", "MMM": "XLI",
    "PG": "XLP", "COST": "XLP", "WMT": "XLP", "KO": "XLP", "PEP": "XLP",
    "PM": "XLP", "MO": "XLP", "CL": "XLP", "TGT": "XLP", "MDLZ": "XLP",
    "KHC": "XLP",
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE",
    "LIN": "XLB", "DOW": "XLB",
    "NEE": "XLU", "SO": "XLU", "DUK": "XLU",
    "AMT": "XLRE", "SPG": "XLRE",
}
SECTORS = {
    "XLK": "Technology", "XLC": "Communication", "XLY": "Discretionary",
    "XLF": "Financials", "XLV": "Health Care", "XLI": "Industrials",
    "XLP": "Staples", "XLE": "Energy", "XLB": "Materials",
    "XLU": "Utilities", "XLRE": "Real Estate",
}
COUNTRIES = {
    "EWA": "Australia", "EWC": "Canada", "EWG": "Germany", "EWH": "Hong Kong",
    "EWI": "Italy", "EWJ": "Japan", "EWL": "Switzerland", "EWP": "Spain",
    "EWQ": "France", "EWS": "Singapore", "EWT": "Taiwan",
    "EWU": "United Kingdom", "EWW": "Mexico", "EWY": "South Korea",
    "EWZ": "Brazil", "FXI": "China", "INDA": "India", "EZA": "South Africa",
}
BENCH = ["SPY", "RSP", "IWM"]

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "test", "index.html")

# ---------------------------------------------------------------- data
def fetch_closes(tickers):
    df = yf.download(tickers, period="2y", interval="1d", auto_adjust=True,
                     progress=False, threads=True)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(tickers[0])
    return df.dropna(how="all")

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def main():
    tickers = sorted(set(list(PANEL) + list(SECTORS) + list(COUNTRIES) + BENCH))
    px = fetch_closes(tickers)
    px = px.ffill(limit=3)

    panel_cols = [t for t in PANEL if t in px.columns and px[t].dropna().shape[0] > 260]
    panel = px[panel_cols]
    n_panel = len(panel_cols)
    if n_panel < 80:
        sys.exit(f"panel too small ({n_panel}) — Yahoo fetch problem, aborting")

    # --- moving-average participation
    sma20, sma50, sma200 = panel.rolling(20).mean(), panel.rolling(50).mean(), panel.rolling(200).mean()
    above20 = (panel > sma20).sum(axis=1) / n_panel * 100
    above50 = (panel > sma50).sum(axis=1) / n_panel * 100
    above200 = (panel > sma200).sum(axis=1) / n_panel * 100

    # --- advance/decline internals
    chg = panel.diff()
    adv = (chg > 0).sum(axis=1)
    dec = (chg < 0).sum(axis=1)
    ad_line = (adv - dec).cumsum()
    tot = (adv + dec).replace(0, float("nan")).astype(float)
    rana = (1000 * (adv - dec) / tot).fillna(0.0)
    mcclellan = ema(rana, 19) - ema(rana, 39)
    zweig = ema((adv / tot).fillna(0.5), 10)

    # --- 52-week highs/lows (closing basis)
    hi52 = int((panel.iloc[-1] >= panel.rolling(252).max().iloc[-1] - 1e-9).sum())
    lo52 = int((panel.iloc[-1] <= panel.rolling(252).min().iloc[-1] + 1e-9).sum())

    # --- leadership ratios (3-month change of the ratio)
    def ratio_chg(a, b, days=63):
        r = px[a] / px[b]
        r = r.dropna()
        return (r.iloc[-1] / r.iloc[-days - 1] - 1) * 100
    rsp_spy = ratio_chg("RSP", "SPY")
    iwm_spy = ratio_chg("IWM", "SPY")

    # --- sector table
    sec_rows = []
    for etf, name in SECTORS.items():
        s = px[etf].dropna()
        ret1m = (s.iloc[-1] / s.iloc[-22] - 1) * 100
        a50 = s.iloc[-1] > s.rolling(50).mean().iloc[-1]
        a200 = s.iloc[-1] > s.rolling(200).mean().iloc[-1]
        members = [t for t, e in PANEL.items() if e == etf and t in panel_cols]
        m_above = sum(panel[t].iloc[-1] > sma50[t].iloc[-1] for t in members)
        sec_rows.append(dict(etf=etf, name=name, ret1m=ret1m, a50=bool(a50),
                             a200=bool(a200), n=len(members),
                             pct50=(m_above / len(members) * 100) if members else float("nan")))
    sec_rows.sort(key=lambda r: r["ret1m"], reverse=True)

    # --- global breadth
    glob_rows = []
    for etf, name in COUNTRIES.items():
        s = px[etf].dropna()
        d200 = (s.iloc[-1] / s.rolling(200).mean().iloc[-1] - 1) * 100
        glob_rows.append(dict(etf=etf, name=name, d200=d200))
    glob_rows.sort(key=lambda r: r["d200"], reverse=True)
    glob_above = sum(r["d200"] > 0 for r in glob_rows) / len(glob_rows) * 100

    # --- latest snapshot values
    a20, a50v, a200v = above20.iloc[-1], above50.iloc[-1], above200.iloc[-1]
    mcc = mcclellan.iloc[-1]
    zw = zweig.iloc[-1]
    adv_t, dec_t = int(adv.iloc[-1]), int(dec.iloc[-1])
    spy = px["SPY"].dropna()
    yr_high = spy.rolling(252).max().iloc[-1]
    off_high = (spy.iloc[-1] / yr_high - 1) * 100  # negative when below high

    # --- regime rules
    if a50v <= 20:
        regime, rcolor = "Washout", "#e05555"
        playbook = [
            "Readings under 20% above the 50-day sit far closer to durable lows than to fresh downtrend starts. Panic-selling here has historically been the wrong trade.",
            "Wait for the turn, not the bottom tick: a McClellan swing from deep negative to strongly positive, or a Zweig thrust above 0.615 within 10 days of a sub-0.40 print, is the re-entry trigger.",
            "Size small until the thrust confirms — washouts can washout further.",
        ]
    elif a50v >= 55 and a200v >= 55:
        regime, rcolor = "Broad advance", "#4caf7d"
        playbook = [
            "With this many stocks in uptrends, weakness is participation refreshing, not distribution — pullbacks toward the 20/50-day have historically resolved higher.",
            "Breadth this wide favors owning more names over levering few: rotation across strong sectors tends to beat concentration here.",
            "Pre-plan the exit: the regime typically ends when % above the 50-day slips below ~45 while the index itself still looks fine. That gap is the tell.",
        ]
    elif a200v >= 50 and a50v < 45:
        regime, rcolor = "Narrowing", "#e0a94c"
        playbook = [
            "The index is being carried by fewer names — gains increasingly depend on the leaders holding up.",
            "Tighten stops on laggards; new exposure belongs only in sectors showing green on both trend columns below.",
            "A downside break in the leaders with breadth already thin is how narrowing turns into correction — watch the A/D line for the early warning.",
        ]
    else:
        regime, rcolor = "Mixed", "#e0a94c"
        playbook = [
            "Neither broad strength nor washout — expect chop and rotation rather than a clean trend.",
            "The sector table below is the actionable edge in this tape: own participation, avoid broken trends.",
            "Let the tape declare itself: % above 50-day pushing through 55–60 opens the broad-advance playbook; a drop under 20 arms the washout playbook.",
        ]

    # --- divergence check
    if off_high > -1.0:
        ad_recent_high = ad_line.iloc[-60:].max()
        conf = ad_line.iloc[-1] >= ad_recent_high - 2
        if conf:
            div_txt = ("Index at/near its 1-year high and the A/D line is confirming with its own highs — "
                       "participation validates the price move.")
        else:
            div_txt = ("⚠ Index near its 1-year high while the A/D line lags its recent peak — "
                       "a bearish breadth divergence. It can persist, but it front-runs most corrections.")
    else:
        div_txt = (f"No divergence test running — the index sits {abs(off_high):.1f}% below its 1-year high. "
                   "The test that matters comes on the next approach of the highs: breadth should lead, not lag.")

    zw_state = "Thrust fired" if zw >= 0.615 else ("Compressed" if zw <= 0.40 else "Neutral")

    # ------------------------------------------------------------ SVG helpers
    W, H, PAD = 860, 220, 34

    def scale(vals, lo=None, hi=None):
        lo = min(vals) if lo is None else lo
        hi = max(vals) if hi is None else hi
        rng = (hi - lo) or 1

        def y(v):
            return PAD + (H - 2 * PAD) * (1 - (v - lo) / rng)
        return y, lo, hi

    def polyline(vals, color, lo=None, hi=None, width=1.6):
        y, _, _ = scale(vals, lo, hi)
        n = len(vals)
        pts = " ".join(f"{PAD + (W - 2 * PAD) * i / (n - 1):.1f},{y(v):.1f}"
                       for i, v in enumerate(vals))
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"/>'

    def hline(val, vals, color, dash="4 4", label=""):
        y, _, _ = scale(vals)
        yy = y(val)
        t = (f'<text x="{W - PAD + 4}" y="{yy + 3}" fill="{color}" font-size="10">{label}</text>'
             if label else "")
        return (f'<line x1="{PAD}" x2="{W - PAD}" y1="{yy:.1f}" y2="{yy:.1f}" '
                f'stroke="{color}" stroke-width="0.7" stroke-dasharray="{dash}"/>{t}')

    def frame():
        return (f'<rect x="{PAD}" y="{PAD}" width="{W - 2 * PAD}" height="{H - 2 * PAD}" '
                f'fill="none" stroke="#2a3040" stroke-width="1"/>')

    def svg(body):
        return (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
                f'style="width:100%;height:auto;display:block">{body}</svg>')

    look = 252
    spy_n = spy.iloc[-look:]
    spy_norm = (spy_n / spy_n.iloc[0] * 100).tolist()
    ad_n = ad_line.iloc[-look:]
    ad_norm = ((ad_n - ad_n.min()) / ((ad_n.max() - ad_n.min()) or 1) *
               (max(spy_norm) - min(spy_norm)) + min(spy_norm)).tolist()
    chart_ad = svg(frame() + polyline(spy_norm, "#d4af5a",
                                      lo=min(spy_norm + ad_norm), hi=max(spy_norm + ad_norm)) +
                   polyline(ad_norm, "#4caf7d",
                            lo=min(spy_norm + ad_norm), hi=max(spy_norm + ad_norm)))

    mc = mcclellan.iloc[-look:].tolist()
    mc_all = mc + [0, 70, -70]
    chart_mc = svg(frame() + hline(0, mc_all, "#8891a5", label="0") +
                   hline(70, mc_all, "#4caf7d", label="+70") +
                   hline(-70, mc_all, "#e05555", label="−70") +
                   polyline(mc, "#5aa2d4", lo=min(mc_all), hi=max(mc_all)))

    a50s = above50.iloc[-look:].tolist()
    a50_all = a50s + [0, 100]
    chart_50 = svg(frame() + hline(80, a50_all, "#4caf7d", label="80") +
                   hline(50, a50_all, "#8891a5", label="50") +
                   hline(20, a50_all, "#e05555", label="20") +
                   polyline(a50s, "#d4af5a", lo=0, hi=100))

    # ------------------------------------------------------------ HTML
    def col(v, good, bad):
        return "#4caf7d" if good(v) else ("#e05555" if bad(v) else "#e0a94c")

    def dot(ok):
        return f'<span style="color:{"#4caf7d" if ok else "#e05555"}">●</span>'

    def pct(v, dec=1):
        return f"{v:.{dec}f}%"

    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    lead_txt = ("Broadening — equal-weight and small caps both outperforming."
                if rsp_spy > 0 and iwm_spy > 0 else
                "Mega-cap concentration — both ratios favor the largest names."
                if rsp_spy < 0 and iwm_spy < 0 else
                "Split tape — the ratios disagree; watch which one resolves.")

    sec_tr = "\n".join(
        f'<tr><td><b>{r["etf"]}</b> <span class="muted">{r["name"]}</span></td>'
        f'<td style="color:{col(r["ret1m"], lambda v: v > 0, lambda v: v < 0)}">{r["ret1m"]:+.1f}%</td>'
        f'<td>{dot(r["a50"])}</td><td>{dot(r["a200"])}</td>'
        f'<td>{pct(r["pct50"]) if not math.isnan(r["pct50"]) else "—"} <span class="muted">(n={r["n"]})</span></td></tr>'
        for r in sec_rows)

    glob_li = "\n".join(
        f'<div class="gitem">{dot(r["d200"] > 0)} <b>{r["name"]}</b> '
        f'<span class="muted">{r["etf"]}</span>'
        f'<span class="gval" style="color:{col(r["d200"], lambda v: v > 0, lambda v: v < 0)}">{r["d200"]:+.1f}%</span></div>'
        for r in glob_rows)

    pb_li = "\n".join(f"<li>{p}</li>" for p in playbook)

    stat = lambda label, val, color: (
        f'<div class="stat"><div class="slabel">{label}</div>'
        f'<div class="sval" style="color:{color}">{val}</div></div>')

    stats = "".join([
        stat("Above 20-day", pct(a20), col(a20, lambda v: v >= 50, lambda v: v < 40)),
        stat("Above 50-day", pct(a50v), col(a50v, lambda v: v >= 50, lambda v: v < 40)),
        stat("Above 200-day", pct(a200v), col(a200v, lambda v: v >= 50, lambda v: v < 40)),
        stat("McClellan osc.", f"{mcc:+.1f}", col(mcc, lambda v: v > 0, lambda v: v < 0)),
        stat("New 52w highs · lows", f"{hi52} · {lo52}", col(hi52 - lo52, lambda v: v > 0, lambda v: v < 0)),
        stat("Advancers · decliners", f"{adv_t} · {dec_t}", col(adv_t - dec_t, lambda v: v > 0, lambda v: v < 0)),
        stat(f"Zweig thrust ({zw_state})", f"{zw:.2f}", col(zw, lambda v: v >= 0.615, lambda v: v <= 0.40)),
    ])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Breadth Monitor — TraderGK test</title>
<style>
:root {{ --bg:#0d1017; --card:#141926; --line:#232a3a; --tx:#d6dae3; --muted:#8891a5;
        --gold:#d4af5a; --green:#4caf7d; --red:#e05555; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:var(--bg); color:var(--tx);
       font:14px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; padding:24px 16px 60px; }}
.wrap {{ max-width:920px; margin:0 auto; }}
h1 {{ font-size:22px; letter-spacing:.3px; }}
h2 {{ font-size:15px; margin:34px 0 4px; color:var(--gold); text-transform:uppercase; letter-spacing:1px; }}
.sub {{ color:var(--muted); font-size:12px; margin:6px 0 18px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-top:10px; }}
.regime {{ font-size:19px; font-weight:700; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-top:14px; }}
.slabel {{ font-size:11px; color:var(--muted); }}
.sval {{ font-size:19px; font-weight:600; font-variant-numeric:tabular-nums; }}
table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
th,td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); font-size:13px; }}
th {{ color:var(--muted); font-weight:500; font-size:11px; text-transform:uppercase; letter-spacing:.5px; }}
.muted {{ color:var(--muted); }}
ul.pb {{ margin:8px 0 0 18px; }} ul.pb li {{ margin:7px 0; }}
.legend {{ font-size:11px; color:var(--muted); margin-top:6px; }}
.gwrap {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:6px 20px; }}
.gitem {{ display:flex; gap:7px; align-items:baseline; padding:3px 0; font-size:13px; }}
.gval {{ margin-left:auto; font-variant-numeric:tabular-nums; }}
.foot {{ margin-top:44px; font-size:11px; color:var(--muted); border-top:1px solid var(--line); padding-top:14px; }}
</style>
</head>
<body><div class="wrap">

<h1>Breadth Monitor <span class="muted" style="font-size:13px">· internal test page</span></h1>
<div class="sub">How many stocks are actually participating in the index move — the structural health
underneath the tape.<br>
Snapshot generated <b>{now}</b> · Yahoo Finance daily closes · {n_panel}-stock mega/large-cap panel
+ 11 sector ETFs + 18 country ETFs · regenerated on demand</div>

<div class="card">
  <div class="slabel">CURRENT BREADTH REGIME · {n_panel}-stock panel</div>
  <div class="regime" style="color:{rcolor}">{regime}</div>
  <div class="muted" style="margin-top:4px">{pct(a50v)} above 50-day · {pct(a200v)} above 200-day ·
  {pct(glob_above, 0)} of country ETFs above their 200-day</div>
  <div class="stats">{stats}</div>
</div>

<div class="card">
  <div class="slabel">PLAYBOOK FOR THIS REGIME</div>
  <ul class="pb">{pb_li}</ul>
</div>

<h2>Divergence check</h2>
<div class="sub">Do the troops confirm the index? New index highs need the A/D line to make them too.</div>
<div class="card">
  <div>{div_txt}</div>
  {chart_ad}
  <div class="legend"><span style="color:var(--gold)">▬</span> SPY (indexed) &nbsp;·&nbsp;
  <span style="color:var(--green)">▬</span> cumulative advance/decline line of the panel · last 12 months.
  Healthy: highs together. Warning: price up while the green line stalls.</div>
</div>

<h2>McClellan oscillator</h2>
<div class="sub">EMA19 − EMA39 of ratio-adjusted net advances — the momentum of participation.</div>
<div class="card">
  {chart_mc}
  <div class="legend">Extremes carry the signal: prints at −70 or lower cluster near tradeable lows;
  a fast sweep from deep negative to firmly positive is a breadth thrust — historically the market's
  highest-conviction bullish pattern.</div>
</div>

<h2>% of panel above the 50-day</h2>
<div class="sub">Share of the panel in short-term uptrends — a mean-reverting oscillator, last 12 months.</div>
<div class="card">
  {chart_50}
  <div class="legend">Above 80% = stretched but a sign of initiation strength, not an automatic sell.
  Below 20% = washout territory, which has sat far closer to bottoms than to the start of new bear legs.</div>
</div>

<h2>Leadership check</h2>
<div class="sub">Equal-weight vs cap-weight and small vs large — who is doing the lifting.</div>
<div class="card">
  <div><b>RSP/SPY</b> 3-month: <b style="color:{col(rsp_spy, lambda v: v > 0, lambda v: v < 0)}">{rsp_spy:+.1f}%</b>
  &nbsp;·&nbsp; <b>IWM/SPY</b> 3-month: <b style="color:{col(iwm_spy, lambda v: v > 0, lambda v: v < 0)}">{iwm_spy:+.1f}%</b></div>
  <div class="muted" style="margin-top:6px">{lead_txt}</div>
</div>

<h2>Sector participation</h2>
<div class="sub">Each SPDR sector vs its own trend, plus the breadth of its panel members — sorted by 1-month return.</div>
<div class="card">
  <table>
    <tr><th>Sector</th><th>1m return</th><th>&gt; 50d</th><th>&gt; 200d</th><th>Panel % &gt; 50d</th></tr>
    {sec_tr}
  </table>
  <div class="legend">When the regime reads Mixed or Narrowing, this table is the trade list:
  green on both trend columns with strong member breadth marks the sectors doing the carrying.</div>
</div>

<h2>Global breadth</h2>
<div class="sub">Country ETFs vs their 200-day average — is the advance worldwide or a US-only story?</div>
<div class="card"><div class="gwrap">{glob_li}</div></div>

<div class="foot">TraderGK research · internal test page, not linked from the site · education only,
not financial advice. Indicators: SMA participation, cumulative A/D, McClellan (EMA19−EMA39 of
ratio-adjusted net advances), Zweig breadth thrust (10-day EMA of adv/(adv+dec); armed &lt;0.40,
fired &ge;0.615 within 10 sessions), 52-week closing highs/lows. Data: Yahoo Finance daily closes.</div>

</div></body></html>"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(html)
    print(f"wrote {OUT} ({len(html)/1024:.0f} KB) — regime={regime}, "
          f"panel={n_panel}, a50={a50v:.1f}%, mcc={mcc:+.1f}")

if __name__ == "__main__":
    main()
