#!/usr/bin/env python3
"""TraderGK research terminal generator -> terminal/ (private, unlinked).

Builds a multi-page market-analysis terminal from free data sources:
  Yahoo Finance daily closes, FRED public CSV endpoints, CFTC public COT API.
Every module is wrapped so one failing data source never kills the build —
its page just shows "data unavailable this run".

Run:  python3 scripts/terminal_test.py     (writes terminal/index.html + terminal/<slug>/)
Standalone — does NOT touch data.json or the trading engine.
"""
import json
import math
import os
import urllib.request
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "terminal")
NOW = datetime.now(timezone.utc)
STAMP = NOW.strftime("%d %b %Y, %H:%M UTC")

# ---------------------------------------------------------------- universe
PANEL = {
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
ASSETS = ["SPY", "QQQ", "IWM", "DIA", "RSP", "EFA", "EEM", "TLT", "IEF", "HYG",
          "LQD", "GLD", "SLV", "USO", "DBC", "UUP", "BTC-USD", "ETH-USD",
          "^VIX", "^VIX3M", "^SKEW", "^TNX", "^IRX", "ZQ=F"]
ANAMES = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Small caps", "DIA": "Dow",
          "RSP": "S&P equal-wt", "EFA": "Dev. intl", "EEM": "Emerging mkts",
          "TLT": "20y+ Treasuries", "IEF": "7-10y Treasuries", "HYG": "High yield",
          "LQD": "IG credit", "GLD": "Gold", "SLV": "Silver", "USO": "Oil",
          "DBC": "Commodities", "UUP": "US dollar", "BTC-USD": "Bitcoin",
          "ETH-USD": "Ethereum"}

# ---------------------------------------------------------------- helpers
GREEN, RED, AMBER, GOLD, BLUE, MUT = "#4caf7d", "#e05555", "#e0a94c", "#d4af5a", "#5aa2d4", "#8891a5"

def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def pct(v, d=1): return f"{v:.{d}f}%"
def sgn(v, d=1): return f"{v:+.{d}f}%"
def col(v, good, bad=None):
    bad = bad if bad else (lambda x: not good(x))
    return GREEN if good(v) else (RED if bad(v) else AMBER)
def cnum(v, d=1): return f'<b style="color:{GREEN if v > 0 else RED}">{v:+.{d}f}%</b>'
def dot(ok): return f'<span style="color:{GREEN if ok else RED}">●</span>'
def pctile(series, val):
    s = series.dropna()
    return float((s < val).mean() * 100)

def fred(series_id, years=6):
    start = (NOW - timedelta(days=365 * years)).strftime("%Y-%m-%d")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    df = pd.read_csv(url, na_values=".")
    df.columns = ["date", "v"]
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna().set_index("date")["v"].astype(float)

W, H, PAD = 820, 210, 34
def _scale(vals, lo=None, hi=None):
    lo = min(vals) if lo is None else lo
    hi = max(vals) if hi is None else hi
    rng = (hi - lo) or 1
    return lambda v: PAD + (H - 2 * PAD) * (1 - (v - lo) / rng), lo, hi

def line_chart(series_list, colors, hlines=(), lo=None, hi=None):
    """series_list: list of value-lists (same length not required)."""
    allv = [v for s in series_list for v in s] + [h[0] for h in hlines]
    y, lo, hi = _scale(allv, lo, hi)
    out = [f'<rect x="{PAD}" y="{PAD}" width="{W-2*PAD}" height="{H-2*PAD}" fill="none" stroke="#2a3040"/>']
    for val, color, label in hlines:
        yy = y(val)
        out.append(f'<line x1="{PAD}" x2="{W-PAD}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{color}" stroke-width="0.7" stroke-dasharray="4 4"/>')
        out.append(f'<text x="{W-PAD+3}" y="{yy+3:.1f}" fill="{color}" font-size="10">{label}</text>')
    for s, color in zip(series_list, colors):
        n = len(s)
        pts = " ".join(f"{PAD+(W-2*PAD)*i/(n-1):.1f},{y(v):.1f}" for i, v in enumerate(s))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/>')
    return (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;height:auto;display:block">{"".join(out)}</svg>')

def bar_chart(labels, vals, highlight=-1):
    y, lo, hi = _scale(list(vals) + [0])
    y0 = y(0)
    n = len(vals)
    bw = (W - 2 * PAD) / n * 0.62
    out = [f'<line x1="{PAD}" x2="{W-PAD}" y1="{y0:.1f}" y2="{y0:.1f}" stroke="{MUT}" stroke-width="0.7"/>']
    for i, (lab, v) in enumerate(zip(labels, vals)):
        x = PAD + (W - 2 * PAD) * (i + 0.19) / n
        yy = y(v)
        top, hgt = (yy, y0 - yy) if v >= 0 else (y0, yy - y0)
        c = GOLD if i == highlight else (GREEN if v >= 0 else RED)
        out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(hgt,1):.1f}" fill="{c}" opacity="0.85"/>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{H-10}" fill="{MUT}" font-size="9" text-anchor="middle">{lab}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;height:auto;display:block">{"".join(out)}</svg>')

def card(body, label=""):
    lab = f'<div class="slabel">{label}</div>' if label else ""
    return f'<div class="card">{lab}{body}</div>'

def stat_grid(items):
    cells = "".join(f'<div><div class="slabel">{l}</div><div class="sval" style="color:{c}">{v}</div></div>'
                    for l, v, c in items)
    return f'<div class="stats">{cells}</div>'

def table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    tr = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{th}</tr>{tr}</table>"

STANCE_COL = {"bullish": GREEN, "bearish": RED, "neutral": AMBER, "info": MUT}

# ---------------------------------------------------------------- page shell
GROUPS = [
    ("Overview", [("", "Overview"), ("confluence", "Confluence")]),
    ("Trend & structure", [("key-levels", "Key Levels"), ("valuation", "Valuation"),
                           ("relative-strength", "Relative Strength"), ("breadth", "Market Breadth"),
                           ("volatility", "Volatility Regime"), ("correlation", "Correlation Matrix")]),
    ("Cycles & positioning", [("momentum", "Momentum"), ("cot", "COT Positioning"),
                              ("seasonality", "Seasonality"), ("sentiment", "Sentiment"),
                              ("crypto", "Crypto"), ("calendar", "Calendar Effects")]),
    ("Macro", [("fed-path", "Fed Path"), ("business-cycle", "Business Cycle"),
               ("yield-curve", "Yield Curve"), ("credit-spreads", "Credit Spreads"),
               ("liquidity", "Global Liquidity"), ("financial-conditions", "Financial Conditions"),
               ("election-cycle", "Election Cycle"), ("astrology", "Market Astrology")]),
    ("Tools", [("screener", "Screener"), ("calculators", "Calculators"), ("glossary", "Glossary")]),
]

CSS = """
:root { --bg:#0d1017; --card:#141926; --line:#232a3a; --tx:#d6dae3; --muted:#8891a5;
        --gold:#d4af5a; --green:#4caf7d; --red:#e05555; }
* { box-sizing:border-box; margin:0; }
body { background:var(--bg); color:var(--tx);
       font:14px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
a { color:inherit; text-decoration:none; }
.layout { display:flex; min-height:100vh; }
nav { width:212px; flex:none; border-right:1px solid var(--line); padding:20px 0 40px; }
nav .brand { padding:0 16px 14px; font-weight:700; letter-spacing:.4px; }
nav .brand small { display:block; color:var(--muted); font-weight:400; font-size:10px; }
nav .g { padding:14px 16px 4px; font-size:10px; text-transform:uppercase; letter-spacing:1px; color:var(--muted); }
nav a { display:block; padding:5px 16px; font-size:13px; color:var(--muted); border-left:2px solid transparent; }
nav a:hover { color:var(--tx); }
nav a.on { color:var(--gold); border-left-color:var(--gold); background:rgba(212,175,90,.06); }
main { flex:1; min-width:0; padding:26px 26px 70px; max-width:960px; }
h1 { font-size:21px; } h1 .tag { font-size:12px; color:var(--muted); font-weight:400; }
h2 { font-size:14px; margin:30px 0 4px; color:var(--gold); text-transform:uppercase; letter-spacing:1px; }
.sub { color:var(--muted); font-size:12px; margin:6px 0 14px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:15px 17px; margin-top:10px; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:13px; margin-top:12px; }
.slabel { font-size:11px; color:var(--muted); }
.sval { font-size:18px; font-weight:600; font-variant-numeric:tabular-nums; }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
th,td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); font-size:13px; }
th { color:var(--muted); font-weight:500; font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
.muted { color:var(--muted); }
ul.pb { margin:8px 0 0 18px; } ul.pb li { margin:6px 0; }
.legend { font-size:11px; color:var(--muted); margin-top:6px; }
.pill { display:inline-block; padding:2px 10px; border-radius:20px; font-size:12px; font-weight:600; }
.ovgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; }
.ovgrid .card { margin:0; } .ovgrid .card:hover { border-color:var(--gold); }
.foot { margin-top:44px; font-size:11px; color:var(--muted); border-top:1px solid var(--line); padding-top:14px; }
input.calc { background:#0d1017; border:1px solid var(--line); border-radius:6px; color:var(--tx);
             padding:6px 9px; width:110px; font-size:13px; }
label.cl { display:inline-block; font-size:12px; color:var(--muted); margin:6px 14px 2px 0; }
@media (max-width:760px){ .layout{display:block} nav{width:auto;border-right:0;border-bottom:1px solid var(--line);
  white-space:nowrap;overflow-x:auto;display:flex;align-items:center;padding:10px}
  nav .brand{padding:0 12px} nav .g{display:none} nav a{display:inline-block;border-left:0;padding:5px 9px} }
"""

def nav_html(active):
    out = ['<div class="brand">TraderGK <small>research terminal</small></div>']
    for gname, items in GROUPS:
        out.append(f'<div class="g">{gname}</div>')
        for slug, name in items:
            on = ' class="on"' if slug == active else ""
            out.append(f'<a href="/terminal/{slug + "/" if slug else ""}"{on}>{name}</a>')
    return "".join(out)

def write_page(slug, title, subtitle, body):
    path = os.path.join(ROOT, slug, "index.html") if slug else os.path.join(ROOT, "index.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title} — TraderGK terminal</title><style>{CSS}</style></head>
<body><div class="layout"><nav>{nav_html(slug)}</nav><main>
<h1>{title} <span class="tag">· private</span></h1>
<div class="sub">{subtitle}<br>Snapshot generated <b>{STAMP}</b> · free public data
(Yahoo Finance, FRED, CFTC) · regenerated on demand</div>
{body}
<div class="foot">TraderGK research · private page — reachable by direct link only · education only, not financial advice.
Data may be delayed or approximate; nothing here is a recommendation.</div>
</main></div></body></html>"""
    with open(path, "w") as f:
        f.write(html)

# ---------------------------------------------------------------- data load
def load_data():
    tickers = sorted(set(list(PANEL) + list(SECTORS) + list(COUNTRIES) + ASSETS))
    px = yf.download(tickers, period="5y", interval="1d", auto_adjust=True,
                     progress=False, threads=True)["Close"].ffill(limit=3)
    gspc_m = yf.download("^GSPC", period="max", interval="1mo", auto_adjust=True,
                         progress=False)["Close"].squeeze().dropna()
    gspc_d = yf.download("^GSPC", period="25y", interval="1d", auto_adjust=True,
                         progress=False)["Close"].squeeze().dropna()
    return px, gspc_m, gspc_d

# ================================================================ modules
# each module fn returns dict(slug, title, sub, body, stance, headline)

def m_breadth(px):
    panel_cols = [t for t in PANEL if t in px.columns and px[t].dropna().shape[0] > 260]
    panel = px[panel_cols].iloc[-560:]
    n = len(panel_cols)
    sma20, sma50, sma200 = (panel.rolling(k).mean() for k in (20, 50, 200))
    above = {k: float((panel.iloc[-1] > s.iloc[-1]).sum()) / n * 100
             for k, s in (("20", sma20), ("50", sma50), ("200", sma200))}
    a50_series = ((panel > sma50).sum(axis=1) / n * 100).iloc[-252:]
    chg = panel.diff()
    adv, dec = (chg > 0).sum(axis=1), (chg < 0).sum(axis=1)
    ad_line = (adv - dec).cumsum()
    tot = (adv + dec).replace(0, float("nan")).astype(float)
    rana = (1000 * (adv - dec) / tot).fillna(0.0)
    mcc = (ema(rana, 19) - ema(rana, 39)).iloc[-1]
    zw = ema((adv / tot).fillna(0.5), 10).iloc[-1]
    hi52 = int((panel.iloc[-1] >= panel.rolling(252).max().iloc[-1] - 1e-9).sum())
    lo52 = int((panel.iloc[-1] <= panel.rolling(252).min().iloc[-1] + 1e-9).sum())
    spy = px["SPY"].dropna()
    off_high = (spy.iloc[-1] / spy.rolling(252).max().iloc[-1] - 1) * 100

    a50, a200 = above["50"], above["200"]
    if a50 <= 20:
        regime, rc, stance = "Washout", RED, "bullish"
        pb = ["Sub-20% readings have historically sat much closer to durable lows than to fresh downlegs — chasing weakness here has been the losing trade.",
              "The re-entry trigger is a thrust, not a level: McClellan sweeping from deep negative to firmly positive, or Zweig ≥ 0.615 shortly after a sub-0.40 print.",
              "Until the thrust confirms, keep size small — washouts can extend."]
    elif a50 >= 55 and a200 >= 55:
        regime, rc, stance = "Broad advance", GREEN, "bullish"
        pb = ["Participation this wide means dips refresh the move rather than end it — pullbacks toward the 20/50-day have the odds on their side.",
              "Wide breadth rewards owning more names over levering few; rotation beats concentration in this regime.",
              "Pre-plan the exit: the regime usually dies when % above the 50-day slides under ~45 while the index still looks fine."]
    elif a200 >= 50 and a50 < 45:
        regime, rc, stance = "Narrowing", AMBER, "bearish"
        pb = ["Fewer soldiers carrying the general — index gains increasingly depend on a shrinking leadership group.",
              "New exposure belongs only in sectors green on both trend columns; tighten stops on laggards.",
              "Narrowing turns into correction when the leaders finally crack — the A/D line gives the early warning."]
    else:
        regime, rc, stance = "Mixed", AMBER, "neutral"
        pb = ["Neither broad strength nor washout — expect rotation and chop rather than clean trend.",
              "The sector table is the actionable edge: own participation, avoid broken trends.",
              "% above 50-day through 55–60 opens the broad-advance playbook; under 20 arms the washout playbook."]

    sec_rows = []
    for etf, name in SECTORS.items():
        s = px[etf].dropna()
        r1m = (s.iloc[-1] / s.iloc[-22] - 1) * 100
        mem = [t for t, e in PANEL.items() if e == etf and t in panel_cols]
        m50 = sum(panel[t].iloc[-1] > sma50[t].iloc[-1] for t in mem)
        sec_rows.append((etf, name, r1m, s.iloc[-1] > s.rolling(50).mean().iloc[-1],
                         s.iloc[-1] > s.rolling(200).mean().iloc[-1],
                         m50 / len(mem) * 100 if mem else float("nan"), len(mem)))
    sec_rows.sort(key=lambda r: r[2], reverse=True)
    glob = sorted(((nm, e, (px[e].dropna().iloc[-1] / px[e].dropna().rolling(200).mean().iloc[-1] - 1) * 100)
                   for e, nm in list(COUNTRIES.items()) + [("SPY", "United States")] if e in px),
                  key=lambda r: r[2], reverse=True)
    glob_above = sum(g[2] > 0 for g in glob) / len(glob) * 100
    rsp_spy = float(((px["RSP"] / px["SPY"]).dropna().iloc[-1] /
                     (px["RSP"] / px["SPY"]).dropna().iloc[-64] - 1) * 100)
    iwm_spy = float(((px["IWM"] / px["SPY"]).dropna().iloc[-1] /
                     (px["IWM"] / px["SPY"]).dropna().iloc[-64] - 1) * 100)

    look = 252
    spy_n = spy.iloc[-look:]; spy_norm = (spy_n / spy_n.iloc[0] * 100).tolist()
    ad_n = ad_line.iloc[-look:]
    ad_norm = ((ad_n - ad_n.min()) / ((ad_n.max() - ad_n.min()) or 1) *
               (max(spy_norm) - min(spy_norm)) + min(spy_norm)).tolist()
    mc_series = (ema(rana, 19) - ema(rana, 39)).iloc[-look:].tolist()

    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{rc}">{regime}</div>'
        f'<div class="muted" style="margin-top:3px">{pct(a50)} above 50-day · {pct(a200)} above 200-day · '
        f'{pct(glob_above,0)} of country ETFs above their 200-day</div>' +
        stat_grid([("Above 20-day", pct(above["20"]), col(above["20"], lambda v: v >= 50)),
                   ("Above 50-day", pct(a50), col(a50, lambda v: v >= 50)),
                   ("Above 200-day", pct(a200), col(a200, lambda v: v >= 50)),
                   ("McClellan", f"{mcc:+.1f}", col(mcc, lambda v: v > 0)),
                   ("52w highs · lows", f"{hi52} · {lo52}", col(hi52 - lo52, lambda v: v >= 0)),
                   ("Zweig thrust", f"{zw:.2f}", AMBER if 0.4 < zw < 0.615 else (GREEN if zw >= 0.615 else RED))]),
        f"BREADTH REGIME · {n}-STOCK PANEL")
    body += card("<ul class='pb'>" + "".join(f"<li>{p}</li>" for p in pb) + "</ul>", "PLAYBOOK FOR THIS REGIME")
    div_txt = (f"No divergence test running — the index sits {abs(off_high):.1f}% below its 1-year high; "
               "the test that matters comes on the next approach of the highs."
               if off_high <= -1 else
               "Index at/near its 1-year highs — check that the A/D line (green) is printing its own highs too. "
               "Price highs without breadth highs front-run most corrections.")
    body += "<h2>Divergence check</h2>" + card(
        div_txt + line_chart([spy_norm, ad_norm], [GOLD, GREEN]) +
        f'<div class="legend"><span style="color:{GOLD}">▬</span> SPY (indexed) · '
        f'<span style="color:{GREEN}">▬</span> panel cumulative A/D line · 12 months</div>')
    body += "<h2>McClellan oscillator</h2>" + card(
        line_chart([mc_series], [BLUE], hlines=[(0, MUT, "0"), (70, GREEN, "+70"), (-70, RED, "−70")]) +
        '<div class="legend">EMA19 − EMA39 of ratio-adjusted net advances. Deep prints ≤ −70 cluster near '
        'tradeable lows; a fast negative→positive sweep is a breadth thrust.</div>')
    body += "<h2>% of panel above the 50-day</h2>" + card(
        line_chart([a50_series.tolist()], [GOLD], hlines=[(80, GREEN, "80"), (50, MUT, "50"), (20, RED, "20")], lo=0, hi=100) +
        '<div class="legend">Mean-reverting oscillator: &gt;80% = stretched but initiation-strong; '
        '&lt;20% = washout, historically nearer bottoms than new bear legs.</div>')
    body += "<h2>Leadership check</h2>" + card(
        f'<div><b>RSP/SPY</b> (equal-weight vs cap-weight) 3-month: '
        f'<b style="color:{GREEN if rsp_spy > 0 else RED}">{rsp_spy:+.1f}%</b> &nbsp;·&nbsp; '
        f'<b>IWM/SPY</b> (small vs large) 3-month: '
        f'<b style="color:{GREEN if iwm_spy > 0 else RED}">{iwm_spy:+.1f}%</b></div>'
        f'<div class="muted" style="margin-top:6px">' +
        ("Broad leadership — the average stock and small caps are both beating the index; the healthiest configuration."
         if rsp_spy > 0 and iwm_spy > 0 else
         "Mega-cap squeeze — both ratios favor the largest names; the index is stronger than its market."
         if rsp_spy < 0 and iwm_spy < 0 else
         "Mixed leadership — neither a broad advance nor an extreme concentration; watch which ratio resolves first.")
        + "</div>")
    body += "<h2>Sector participation</h2>" + card(table(
        ["Sector", "1m return", "> 50d", "> 200d", "Panel % > 50d"],
        [(f"<b>{e}</b> <span class='muted'>{nm}</span>", cnum(r), dot(a), dot(b),
          f"{pct(p) if not math.isnan(p) else '—'} <span class='muted'>(n={k})</span>")
         for e, nm, r, a, b, p, k in sec_rows]) +
        '<div class="legend">In a Mixed or Narrowing regime this table IS the trade list: green on both '
        'trend columns with strong member breadth marks the sectors doing the carrying.</div>')
    body += "<h2>Global breadth</h2>" + card(
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:4px 18px">' +
        "".join(f'<div style="display:flex;gap:7px;align-items:baseline;font-size:13px">{dot(d>0)} <b>{nm}</b> '
                f'<span class="muted">{e}</span><span style="margin-left:auto;color:{GREEN if d>0 else RED}">{d:+.1f}%</span></div>'
                for nm, e, d in glob) + "</div>" +
        f'<div class="legend">{sum(g[2] > 0 for g in glob)}/{len(glob)} markets above their 200-day. Global '
        'confirmation strengthens any US signal; the US rallying alone while the world sits below trend is a '
        'narrower story than the index chart suggests.</div>',
        "COUNTRY ETFs vs THEIR 200-DAY · IS THE ADVANCE GLOBAL OR US-ONLY?")
    return dict(slug="breadth", title="Market Breadth",
                sub="How many stocks are actually participating — the structural health under the index.",
                body=body, stance=stance,
                headline=f"{regime} — {pct(a50)} of the panel above its 50-day")

VOL_IDX = [("^VIX", "VIX", "S&P 500 30d"), ("^VIX9D", "VIX9D", "S&P 500 9d"),
           ("^VIX3M", "VIX3M", "S&P 500 3m"), ("^VVIX", "VVIX", "Vol of VIX"),
           ("^SKEW", "SKEW", "Tail-risk pricing"), ("^MOVE", "MOVE", "Treasury vol"),
           ("^OVX", "OVX", "Crude oil vol"), ("^GVZ", "GVZ", "Gold vol")]

def _spy_gex():
    """Net dealer gamma from SPY option chains (Black-Scholes gamma x OI)."""
    import numpy as np
    tk = yf.Ticker("SPY")
    spot = float(tk.fast_info["last_price"])
    r = 0.04
    exps = [e for e in tk.options
            if (pd.Timestamp(e) - pd.Timestamp.now()).days <= 90][:8]
    per_strike = {}
    tot = 0.0
    pc_oi = [0, 0]
    exp_move = None
    for ei, e in enumerate(exps):
        ch = tk.option_chain(e)
        T = max((pd.Timestamp(e) - pd.Timestamp.now()).days, 0.5) / 365
        for df, sign, slot in ((ch.calls, 1, 0), (ch.puts, -1, 1)):
            iv = df["impliedVolatility"].clip(0.01, 3).values
            K = df["strike"].values
            oi = df["openInterest"].fillna(0).values
            d1 = (np.log(spot / K) + (r + iv ** 2 / 2) * T) / (iv * np.sqrt(T))
            gamma = np.exp(-d1 ** 2 / 2) / np.sqrt(2 * np.pi) / (spot * iv * np.sqrt(T))
            # dollar gamma per 1% move, in $bn
            dg = gamma * oi * 100 * spot ** 2 * 0.01 / 1e9
            pc_oi[slot] += oi.sum()
            for k, g in zip(K, dg * sign):
                per_strike[k] = per_strike.get(k, 0.0) + g
            tot += float((dg * sign).sum())
        if ei == 0:
            atm_i = (ch.calls["strike"] - spot).abs().idxmin()
            atm_k = ch.calls.loc[atm_i, "strike"]
            call_m = ch.calls.loc[atm_i, "lastPrice"]
            put_r = ch.puts[ch.puts["strike"] == atm_k]
            if len(put_r):
                exp_move = (call_m + float(put_r["lastPrice"].iloc[0])) / spot * 100
                exp_date = e
    ks = sorted(per_strike)
    cum, flip = 0.0, None
    for k in ks:
        prev = cum
        cum += per_strike[k]
        if prev < 0 <= cum and abs(k - spot) / spot < 0.15:
            flip = k
    calls_w = sorted((k for k in ks if per_strike[k] > 0 and k >= spot * 0.97),
                     key=lambda k: -per_strike[k])[:3]
    puts_w = sorted((k for k in ks if per_strike[k] < 0 and k <= spot * 1.03),
                    key=lambda k: per_strike[k])[:3]
    return dict(tot=tot, flip=flip, spot=spot, exp_move=exp_move,
                exp_date=exp_date if exp_move else None,
                pc=pc_oi[1] / pc_oi[0] if pc_oi[0] else None,
                calls=sorted(calls_w), puts=sorted(puts_w, reverse=True))

def m_volatility(px):
    hist = yf.download([t for t, *_ in VOL_IDX], period="2y", interval="1d",
                       auto_adjust=True, progress=False)["Close"].ffill(limit=3)
    old = yf.download(["^GSPC", "^VIX"], period="max", interval="1d",
                      auto_adjust=True, progress=False)["Close"].dropna()
    old = old[old.index.year >= 1990]
    vix = hist["^VIX"].dropna()
    lvl = float(vix.iloc[-1])
    p10y = pctile(old["^VIX"], lvl)
    v9d = hist["^VIX9D"].dropna().iloc[-1]
    v3m = hist["^VIX3M"].dropna().iloc[-1]
    ts = v9d / v3m  # <1 contango (calm), >1 inverted (stress)
    skew = float(hist["^SKEW"].dropna().iloc[-1])
    rv21 = float(px["SPY"].dropna().pct_change().rolling(21).std().iloc[-1] * math.sqrt(252) * 100)
    vrp = lvl - rv21

    # --- regime + playbook (rule-based, own wording)
    if ts >= 1.0 or lvl >= 30:
        regime, rc, stance = "Stress", RED, "bearish"
        pb = ["The near curve is inverted — the market pays a premium for protection RIGHT NOW. Trend day "
              "risk is elevated in both directions; fade nothing.",
              "Reduce size before adjusting direction: realized moves cluster far above average in this state.",
              "Watch the 9D/3M ratio for the exit — it re-steepens below 1.0 before price bottoms convincingly."]
    elif lvl < 20 and ts < 0.9:
        regime, rc, stance = "Calm", GREEN, "neutral"
        pb = ["Mean-reversion tape: moves toward range extremes tend to fail, breakouts have a poor hit rate.",
              "Premium-selling and theta approaches are being paid — but always against a tail hedge; "
              "this regime ends abruptly, not gradually.",
              "The early warning is the 9D/3M ratio climbing toward 1.0 while price still looks fine."]
    else:
        regime, rc, stance = "Transitional", AMBER, "neutral"
        pb = ["Between regimes — neither the calm-pin nor the stress-trend playbook is reliable here.",
              "Trade smaller and let the term structure pick the side: back under 0.9 = calm resumes; "
              "through 1.0 = stress rules apply.",
              "Divergences across the vol complex (MOVE or OVX waking up first) usually resolve the direction."]

    # --- vol complex table
    vrows = []
    for sym, name, meas in VOL_IDX:
        s = hist[sym].dropna()
        if len(s) < 60:
            continue
        d5 = float(s.iloc[-1] - s.iloc[-6])
        p1y = pctile(s.iloc[-252:], float(s.iloc[-1]))
        vrows.append((name, meas, float(s.iloc[-1]), d5, p1y))
    vol_tbl = table(["Index", "Measures", "Level", "5d Δ", "1y pctile"],
                    [(f"<b>{n}</b>", f'<span class="muted">{m}</span>', f"{l:,.2f}",
                      f'<span style="color:{RED if d > 0 else GREEN}">{d:+.2f}</span>',
                      f"{p:.0f}%") for n, m, l, d, p in vrows])

    # --- VIX bucket forward returns since 1990
    fwd = old["^GSPC"].shift(-21) / old["^GSPC"] - 1
    buckets = [("VIX < 15", old["^VIX"] < 15), ("15–20", (old["^VIX"] >= 15) & (old["^VIX"] < 20)),
               ("20–25", (old["^VIX"] >= 20) & (old["^VIX"] < 25)),
               ("25–30", (old["^VIX"] >= 25) & (old["^VIX"] < 30)), ("VIX ≥ 30", old["^VIX"] >= 30)]
    cur_b = 0 if lvl < 15 else 1 if lvl < 20 else 2 if lvl < 25 else 3 if lvl < 30 else 4
    brows = []
    for i, (bname, mask) in enumerate(buckets):
        f = fwd[mask].dropna() * 100
        now_tag = ' <span class="pill" style="background:rgba(212,175,90,.15);color:#d4af5a">now</span>' if i == cur_b else ""
        brows.append((f"<b>{bname}</b>{now_tag}", cnum(f.mean(), 2), cnum(f.median(), 2),
                      f"{(f > 0).mean() * 100:.0f}%", f"{len(f):,}"))
    bucket_tbl = table(["VIX bucket", "Avg fwd 21d", "Median", "Win rate", "n"], brows)

    # --- implied vs realized chart
    rv_series = (px["SPY"].dropna().pct_change().rolling(21).std() * math.sqrt(252) * 100).iloc[-252:]
    chart_ivrv = line_chart([vix.iloc[-252:].tolist(), rv_series.tolist()], [GOLD, GREEN])

    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{rc}">{regime}</div>'
        f'<div class="muted" style="margin-top:3px">VIX {lvl:.1f} ({p10y:.0f}th 10-year percentile) · '
        f'9D/3M {ts:.2f} ({"inverted — stress" if ts >= 1 else "contango — normal"}) · '
        f'SKEW {skew:.0f} · implied − realized {vrp:+.1f} pts</div>' +
        stat_grid([("VIX", f"{lvl:.1f}", col(lvl, lambda v: v < 18, lambda v: v > 25)),
                   ("10y percentile", f"{p10y:.0f}th", col(p10y, lambda v: v < 60, lambda v: v > 85)),
                   ("9D / 3M ratio", f"{ts:.2f}", col(ts, lambda v: v < 0.9, lambda v: v >= 1.0)),
                   ("SKEW", f"{skew:.0f}", col(skew, lambda v: v < 140, lambda v: v > 155)),
                   ("Realized 21d", pct(rv21), MUT),
                   ("Vol premium", f"{vrp:+.1f} pts", col(vrp, lambda v: v > 0))]),
        "VOLATILITY REGIME") + card(
        "<ul class='pb'>" + "".join(f"<li>{p}</li>" for p in pb) + "</ul>", "PLAYBOOK FOR THIS REGIME")
    body += "<h2>The vol complex</h2>" + card(
        vol_tbl + '<div class="legend">Every liquid volatility index with its 5-session change and 1-year '
        'percentile. Rising vol prints red because for these indices up usually means risk-off. The '
        'cross-asset divergences carry the most information — Treasury vol (MOVE) waking up while VIX '
        'sleeps has preceded equity stress repeatedly.</div>')
    body += "<h2>Term structure</h2>" + card(
        f'<div><b style="color:{RED if ts >= 1 else GREEN}">{("Inverted" if ts >= 1 else "Contango")}</b> — '
        f'9-day vol at {v9d:.1f} vs 3-month at {v3m:.1f} (ratio {ts:.2f})</div>'
        '<div class="muted" style="margin-top:6px">An upward-sloping curve is the normal state: near-term '
        'calm priced below far-dated uncertainty. The inversion of this ratio through 1.0 is the single '
        'cleanest "regime is breaking" signal in the vol space — it usually flips before price confirms.</div>')
    body += "<h2>Implied vs realized</h2>" + card(
        chart_ivrv +
        f'<div class="legend"><span style="color:{GOLD}">▬</span> VIX (what options price) · '
        f'<span style="color:{GREEN}">▬</span> 21-day realized vol (what the market delivered) · 12 months. '
        'The gap is the variance risk premium — persistently positive because insurance costs money. '
        'Extremes are the signal: a huge gap = fear is overpaid; realized ABOVE implied = the market is '
        'under-hedged for what is already happening.</div>')
    # --- dealer gamma (best effort)
    try:
        g = _spy_gex()
        flip_txt = f"{g['flip']:,.0f}" if g["flip"] else "—"
        em_txt = (f"±{g['exp_move']:.2f}% → {g['exp_date']}" if g["exp_move"] else "—")
        body += "<h2>Dealer gamma (SPY)</h2>" + card(
            stat_grid([("Net dealer gamma", f"${g['tot']:+.2f}bn / 1%",
                        col(g["tot"], lambda v: v > 0)),
                       ("Gamma flip", flip_txt, MUT),
                       ("Spot", f"{g['spot']:,.1f}", MUT),
                       ("Expected move", em_txt, MUT),
                       ("Put/Call OI", f"{g['pc']:.2f}" if g["pc"] else "—", MUT)]) +
            f'<div style="margin-top:8px">Call walls (pin/resistance): <b>{" · ".join(f"{k:,.0f}" for k in g["calls"])}</b>'
            f' &nbsp;·&nbsp; Put walls (support→accelerant): <b>{" · ".join(f"{k:,.0f}" for k in g["puts"])}</b></div>'
            '<div class="muted" style="margin-top:8px">Computed from the SPY option chain (Black-Scholes '
            'gamma × open interest, calls positive / puts negative, expiries ≤ 90 days). Positive net gamma: '
            'dealer hedging leans AGAINST price — moves get suppressed and pinned near the big strikes. '
            'Negative: the same hedging chases price and moves accelerate; most trend days and crashes live '
            'there. The flip strike is where the tape changes character.</div>')
    except Exception:
        body += "<h2>Dealer gamma (SPY)</h2>" + card(
            '<span class="muted">Option-chain data unavailable this run — section skipped.</span>')
    body += "<h2>What VIX levels have meant</h2>" + card(
        bucket_tbl + '<div class="legend">S&P 500 forward 21-session returns grouped by the VIX level on '
        'entry day, daily observations since 1990. The famous asymmetry: the highest-VIX bucket has the '
        'BEST average forward return (panic gets bought) but also the widest spread of outcomes — the 2008 '
        'tail lives inside it. Low VIX earns less, far more reliably.</div>')
    return dict(slug="volatility", title="Volatility Regime",
                sub="The price of risk read three ways: what options price, what the market delivers, and how dealers are positioned.",
                body=body, stance=stance,
                headline=f"{regime} — VIX {lvl:.1f} ({p10y:.0f}th pctile), 9D/3M {ts:.2f}")

RRG_UNIS = [
    ("sectors", "US Sectors", "SPY", dict(SECTORS)),
    ("industries", "Industries", "SPY",
     {"IGV": "Software", "SMH": "Semis", "XBI": "Biotech", "KRE": "Reg. banks",
      "XHB": "Homebuilders", "ITA": "Defense", "XOP": "Oil & gas E&P",
      "XME": "Metals & mining", "JETS": "Airlines", "TAN": "Solar"}),
    ("styles", "Styles & Factors", "SPY",
     {"MTUM": "Momentum", "VLUE": "Value factor", "QUAL": "Quality", "USMV": "Min vol",
      "IWF": "Growth", "IWD": "Value (large)", "RSP": "Equal weight", "IWM": "Small caps"}),
    ("assets", "Asset Classes", "SPY",
     {"TLT": "Long bonds", "IEF": "7-10y bonds", "GLD": "Gold", "DBC": "Commodities",
      "HYG": "HY credit", "EEM": "Emerging mkts", "EFA": "Dev. intl", "BTC-USD": "Bitcoin"}),
    ("global", "Global Markets", "SPY",
     {"EWJ": "Japan", "EWG": "Germany", "EWU": "UK", "EWQ": "France", "EWI": "Italy",
      "EWP": "Spain", "EWY": "South Korea", "EWT": "Taiwan", "FXI": "China",
      "INDA": "India", "EWZ": "Brazil"}),
    ("crypto", "Crypto (vs BTC)", "BTC-USD",
     {"ETH-USD": "Ethereum", "SOL-USD": "Solana", "BNB-USD": "BNB", "XRP-USD": "XRP",
      "ADA-USD": "Cardano", "DOGE-USD": "Dogecoin"}),
]

def _rrg_quad(x, y):
    if x >= 100 and y >= 100: return "LEADING"
    if x >= 100: return "WEAKENING"
    if y >= 100: return "IMPROVING"
    return "LAGGING"

RRG_JS = r"""
(function(){
const D=__DATA__,GRN='#4caf7d',RED='#e05555',GOLDC='#d4af5a',BLU='#5aa2d4',MUT='#8891a5';
const QC={LEADING:GRN,WEAKENING:GOLDC,LAGGING:RED,IMPROVING:BLU};
let uni=Object.keys(D)[0];
const wrap=document.getElementById('rrgw');
function render(){
 const u=D[uni];
 let h='<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">'+Object.keys(D).map(k=>
  '<button data-u="'+k+'" style="cursor:pointer;font-size:11px;padding:3px 12px;border-radius:14px;border:1px solid '+
  (k===uni?GOLDC:'#232a3a')+';background:'+(k===uni?'rgba(212,175,90,.12)':'transparent')+';color:'+(k===uni?GOLDC:MUT)+'">'+D[k].name+'</button>').join('')+'</div>';
 // scatter
 const S=560,P=44;let xs=[],ys=[];
 u.rows.forEach(r=>r.trail.forEach(p=>{xs.push(p[0]);ys.push(p[1]);}));
 const sp=Math.max(1.6,...xs.map(v=>Math.abs(v-100)),...ys.map(v=>Math.abs(v-100)))*1.15;
 const X=v=>P+(S-2*P)*((v-(100-sp))/(2*sp)),Y=v=>S-P-(S-2*P)*((v-(100-sp))/(2*sp));
 const cx=X(100),cy=Y(100);
 let g='<rect x="'+P+'" y="'+P+'" width="'+(cx-P)+'" height="'+(cy-P)+'" fill="rgba(90,162,212,.05)"/>'+
  '<rect x="'+cx+'" y="'+P+'" width="'+(S-P-cx)+'" height="'+(cy-P)+'" fill="rgba(76,175,125,.05)"/>'+
  '<rect x="'+P+'" y="'+cy+'" width="'+(cx-P)+'" height="'+(S-P-cy)+'" fill="rgba(224,85,85,.05)"/>'+
  '<rect x="'+cx+'" y="'+cy+'" width="'+(S-P-cx)+'" height="'+(S-P-cy)+'" fill="rgba(212,175,90,.05)"/>'+
  '<line x1="'+cx+'" x2="'+cx+'" y1="'+P+'" y2="'+(S-P)+'" stroke="'+MUT+'" stroke-width="0.6"/>'+
  '<line x1="'+P+'" x2="'+(S-P)+'" y1="'+cy+'" y2="'+cy+'" stroke="'+MUT+'" stroke-width="0.6"/>'+
  '<text x="'+(S-P-8)+'" y="'+(P+16)+'" text-anchor="end" fill="'+GRN+'" font-size="11" font-weight="600">LEADING</text>'+
  '<text x="'+(S-P-8)+'" y="'+(S-P-8)+'" text-anchor="end" fill="'+GOLDC+'" font-size="11" font-weight="600">WEAKENING</text>'+
  '<text x="'+(P+8)+'" y="'+(S-P-8)+'" fill="'+RED+'" font-size="11" font-weight="600">LAGGING</text>'+
  '<text x="'+(P+8)+'" y="'+(P+16)+'" fill="'+BLU+'" font-size="11" font-weight="600">IMPROVING</text>'+
  '<text x="'+(S/2)+'" y="'+(S-6)+'" text-anchor="middle" fill="'+MUT+'" font-size="10">RS-Ratio (trend of relative strength) →</text>'+
  '<text x="12" y="'+(S/2)+'" fill="'+MUT+'" font-size="10" transform="rotate(-90 12 '+(S/2)+')" text-anchor="middle">RS-Momentum →</text>';
 u.rows.forEach(r=>{
  const c=QC[r.q];
  const pts=r.trail.map(p=>X(p[0]).toFixed(1)+','+Y(p[1]).toFixed(1)).join(' ');
  g+='<polyline points="'+pts+'" fill="none" stroke="'+c+'" stroke-width="1.1" opacity="0.45"/>';
  r.trail.slice(0,-1).forEach(p=>{g+='<circle cx="'+X(p[0]).toFixed(1)+'" cy="'+Y(p[1]).toFixed(1)+'" r="1.6" fill="'+c+'" opacity="0.4"/>';});
  const e=r.trail[r.trail.length-1];
  g+='<circle cx="'+X(e[0]).toFixed(1)+'" cy="'+Y(e[1]).toFixed(1)+'" r="4" fill="'+c+'"><title>'+r.t+' · '+r.q+'</title></circle>'+
   '<text x="'+(X(e[0])+6).toFixed(1)+'" y="'+(Y(e[1])-5).toFixed(1)+'" fill="'+c+'" font-size="10" font-weight="600">'+r.t+'</text>';});
 h+='<svg viewBox="0 0 '+S+' '+S+'" style="width:100%;max-width:620px;height:auto;display:block;margin:0 auto">'+g+'</svg>';
 h+='<div style="overflow-x:auto;margin-top:12px"><table><tr><th>Asset</th><th>Quadrant</th><th>RS-Ratio</th><th>RS-Mom</th><th>Dir</th><th>1m vs bench</th><th>3m vs bench</th><th>Action</th></tr>';
 u.rows.forEach(r=>{const e=r.trail[r.trail.length-1];
  h+='<tr><td style="white-space:nowrap"><b>'+r.t+'</b> <span class="muted">'+r.n+'</span></td>'+
   '<td><span style="color:'+QC[r.q]+';font-weight:600">'+r.q+'</span>'+(r.nw?' <span class="pill" style="background:rgba(212,175,90,.15);color:'+GOLDC+';font-size:10px">NEW</span>':'')+'</td>'+
   '<td>'+e[0].toFixed(2)+'</td><td>'+e[1].toFixed(2)+'</td><td style="color:'+GOLDC+'">'+r.dir+'</td>'+
   '<td style="color:'+(r.r1>=0?GRN:RED)+'">'+(r.r1>=0?'+':'')+r.r1+'%</td>'+
   '<td style="color:'+(r.r3>=0?GRN:RED)+'">'+(r.r3>=0?'+':'')+r.r3+'%</td>'+
   '<td class="muted" style="font-size:12px">'+r.act+'</td></tr>';});
 h+='</table></div>';
 wrap.innerHTML=h;
 wrap.querySelectorAll('button').forEach(b=>b.onclick=()=>{uni=b.dataset.u;render();});
}
render();
})();
"""

def m_relative_strength(px):
    syms = sorted({s for *_, mems in RRG_UNIS for s in mems} |
                  {b for _, _, b, _ in RRG_UNIS})
    hist = yf.download(syms, period="2y", interval="1d", auto_adjust=True,
                       progress=False)["Close"].ffill(limit=3)
    data, rotations = {}, []
    for key, uname, bench, mems in RRG_UNIS:
        wk = hist.resample("W-FRI").last()
        rows = []
        for t, n in mems.items():
            if t not in wk.columns or t == bench:
                continue
            rs = (100 * wk[t] / wk[bench]).dropna()
            if len(rs) < 25:
                continue
            rsr = (100 * rs / rs.rolling(14).mean()).dropna()
            rsm = (100 * rsr / rsr.rolling(5).mean()).dropna()
            pts = [[round(float(rsr.loc[i]), 2), round(float(rsm.loc[i]), 2)]
                   for i in rsm.index[-8:]]
            if len(pts) < 4:
                continue
            q_now, q_prev1, q_prev2 = (_rrg_quad(*pts[-1]), _rrg_quad(*pts[-2]),
                                       _rrg_quad(*pts[-3]))
            nw = q_now != q_prev1 or q_now != q_prev2
            dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
            ang = math.degrees(math.atan2(dy, dx)) % 360
            dirs = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]
            arrow = dirs[int((ang + 22.5) // 45) % 8]
            ratio_d = (hist[t] / hist[bench]).dropna()
            r1 = round(float((ratio_d.iloc[-1] / ratio_d.iloc[-22] - 1) * 100), 1)
            r3 = round(float((ratio_d.iloc[-1] / ratio_d.iloc[-64] - 1) * 100), 1)
            up = arrow in ("↗", "↑", "↖")
            down = arrow in ("↘", "↓", "↙")
            if q_now == "IMPROVING":
                act = ("Accumulate — freshly turned off the lows; best risk/reward of the cycle"
                       if nw and q_prev1 == "LAGGING" or q_prev2 == "LAGGING"
                       else "Wait — turn not confirmed")
            elif q_now == "LEADING":
                act = "Tighten stops — momentum fading" if down else "Hold / buy pullbacks"
            elif q_now == "WEAKENING":
                act = "Watch — possible re-acceleration" if up else "Reduce — rotation out underway"
            else:
                act = "Watchlist — early turn forming" if up else "Avoid / underweight"
            rows.append(dict(t=t.replace("-USD", ""), n=n, trail=pts, q=q_now, nw=nw,
                             dir=arrow, r1=r1, r3=r3, act=act))
            if q_now != q_prev1:
                rotations.append((uname, f"{n} ({t.replace('-USD','')}) rotated "
                                  f"{q_prev1.title()} → {q_now.title()}, last week — {act.lower()}"))
            elif q_prev1 != q_prev2:
                rotations.append((uname, f"{n} ({t.replace('-USD','')}) rotated "
                                  f"{q_prev2.title()} → {q_prev1.title()}, two weeks ago — {act.lower()}"))
        order = {"LEADING": 0, "IMPROVING": 1, "WEAKENING": 2, "LAGGING": 3}
        rows.sort(key=lambda r: (order[r["q"]], -r["trail"][-1][0]))
        data[key] = dict(name=uname, rows=rows)
    rot_html = "".join(
        f'<div style="padding:5px 0;border-bottom:1px solid var(--line);font-size:13px">'
        f'<span class="muted" style="font-size:11px">{u}</span><br>{txt}</div>'
        for u, txt in rotations[:10]) or '<span class="muted">No quadrant changes in the last two weeks.</span>'
    payload = json.dumps(data, separators=(",", ":"))
    body = card(rot_html, "FRESH ROTATIONS — QUADRANT CHANGES, LAST TWO WEEKS") + card(
        '<div id="rrgw">loading…</div><script>' + RRG_JS.replace("__DATA__", payload) + "</script>",
        "RELATIVE ROTATION · WEEKLY RS-RATIO × RS-MOMENTUM · 8-WEEK TRAILS") + card(
        "<ul class='pb'>"
        "<li><b>The cycle is clockwise</b>: strength builds (Improving, top-left), peaks (Leading, "
        "top-right), fades (Weakening, bottom-right), bottoms (Lagging, bottom-left) — then repeats. "
        "Where a name IS matters less than where its trail is HEADED.</li>"
        "<li><b>Improving is where alpha is born</b> — relative strength has turned before the crowd "
        "repriced it. Names freshly arrived from Lagging (the NEW badge) are the highest risk/reward "
        "entries in rotation strategy.</li>"
        "<li><b>Leading is for holding, not chasing</b> — buy pullbacks, and treat a south-pointing arrow "
        "as the start of distribution even while price still looks fine.</li>"
        "<li><b>Weakening is the exit ramp</b> — still outperforming on trend, but the money is already "
        "leaving. Most traders overstay here.</li>"
        "<li><b>Lagging is only interesting when its arrow points north</b> — that's next quarter's "
        "Improving story, a watchlist entry rather than a position.</li></ul>"
        '<div class="muted" style="margin-top:8px">RS-Ratio = the asset/benchmark ratio versus its own '
        '14-week average (×100); RS-Momentum = the same normalization applied to RS-Ratio. Both center on '
        '100 — the crosshair — computed on weekly closes with 8-week trails.</div>', "HOW TO TRADE THE QUADRANTS")
    leaders = [r["t"] for r in data["sectors"]["rows"] if r["q"] == "LEADING"]
    return dict(slug="relative-strength", title="Relative Strength",
                sub="Relative rotation across six universes — sectors, industries, factors, asset classes, countries, crypto — with 8-week trails.",
                body=body, stance="info",
                headline=(f"Leading sectors: {', '.join(leaders[:4])}" if leaders
                          else f"{len(rotations)} fresh rotations — no sector in Leading"))

KL_TICKERS = ["SPY", "QQQ", "IWM", "NVDA", "GLD", "TLT", "BTC-USD", "ETH-USD"]

def _swings(h, l, w=5):
    sh, sl = [], []
    for i in range(w, len(h) - w):
        if h.iloc[i] == h.iloc[i - w:i + w + 1].max():
            sh.append((h.index[i], float(h.iloc[i])))
        if l.iloc[i] == l.iloc[i - w:i + w + 1].min():
            sl.append((l.index[i], float(l.iloc[i])))
    return sh, sl

def _vprofile(close, vol, bins=40):
    lo, hi = float(close.min()), float(close.max())
    if hi <= lo:
        return None
    step = (hi - lo) / bins
    hist = [0.0] * bins
    for c, v in zip(close, vol):
        b = min(int((c - lo) / step), bins - 1)
        hist[b] += float(v)
    poc_i = max(range(bins), key=lambda i: hist[i])
    total = sum(hist)
    inc, i0, i1 = hist[poc_i], poc_i, poc_i
    while inc < 0.70 * total and (i0 > 0 or i1 < bins - 1):
        left = hist[i0 - 1] if i0 > 0 else -1
        right = hist[i1 + 1] if i1 < bins - 1 else -1
        if right >= left:
            i1 += 1; inc += hist[i1]
        else:
            i0 -= 1; inc += hist[i0]
    ctr = lambda i: lo + (i + 0.5) * step
    hvn = sorted(range(bins), key=lambda i: -hist[i])[:3]
    lvn = [i for i in sorted(range(i0, i1 + 1), key=lambda i: hist[i])[:3]]
    return dict(poc=ctr(poc_i), vah=ctr(i1), val=ctr(i0),
                hvn=[ctr(i) for i in hvn], lvn=[ctr(i) for i in lvn])

def _kl_options(tkr, spot):
    tk = yf.Ticker(tkr)
    exps = tk.options
    if not exps:
        return None
    near = exps[0]
    month = next((e for e in exps if (pd.Timestamp(e) - pd.Timestamp.now()).days >= 25), None)
    out = dict(near=near)
    ch = tk.option_chain(near)
    co = ch.calls[["strike", "openInterest", "lastPrice"]].fillna(0)
    po = ch.puts[["strike", "openInterest", "lastPrice"]].fillna(0)
    win = (co["strike"] > spot * 0.9) & (co["strike"] < spot * 1.12)
    out["cwalls"] = co[win & (co["strike"] >= spot * 0.985)].nlargest(3, "openInterest")["strike"].tolist()
    winp = (po["strike"] > spot * 0.88) & (po["strike"] < spot * 1.1)
    out["pwalls"] = po[winp & (po["strike"] <= spot * 1.015)].nlargest(3, "openInterest")["strike"].tolist()
    ks = sorted(set(co["strike"]) & set(po["strike"]))
    if ks:
        def pain(K):
            call_pay = ((K - co["strike"]).clip(lower=0) * co["openInterest"]).sum()
            put_pay = ((po["strike"] - K).clip(lower=0) * po["openInterest"]).sum()
            return call_pay + put_pay
        out["maxpain"] = min((k for k in ks if spot * 0.85 < k < spot * 1.15), key=pain, default=None)
    atm_i = (co["strike"] - spot).abs().idxmin()
    atm_k = co.loc[atm_i, "strike"]
    pr = po[po["strike"] == atm_k]
    if len(pr):
        out["em_near"] = float(co.loc[atm_i, "lastPrice"] + pr["lastPrice"].iloc[0]) / spot * 100
    if month:
        ch2 = tk.option_chain(month)
        c2, p2 = ch2.calls, ch2.puts
        ai = (c2["strike"] - spot).abs().idxmin()
        ak = c2.loc[ai, "strike"]
        pr2 = p2[p2["strike"] == ak]
        if len(pr2):
            out["em_month"] = float(c2.loc[ai, "lastPrice"] + pr2["lastPrice"].iloc[0]) / spot * 100
            out["month"] = month
    return out

def _kl_ticker(tkr, df):
    o, h, l, c, v = (df[k].dropna() for k in ("Open", "High", "Low", "Close", "Volume"))
    spot = float(c.iloc[-1])
    fmt = lambda p: f"{p:,.0f}" if spot > 2000 else f"{p:,.2f}"
    # --- structure
    sh, sl = _swings(h, l, 5)
    def trend(hs, ls):
        if len(hs) < 2 or len(ls) < 2:
            return "Insufficient swings"
        hh, hl_ = hs[-1][1] > hs[-2][1], ls[-1][1] > ls[-2][1]
        if hh and hl_: return "Uptrend (HH + HL)"
        if not hh and not hl_: return "Downtrend (LH + LL)"
        return "Mixed structure"
    d_tr = trend(sh, sl)
    wdf = df.resample("W-FRI").agg({"High": "max", "Low": "min"}).dropna()
    wsh, wsl = _swings(wdf["High"], wdf["Low"], 3)
    w_tr = trend(wsh, wsl)
    # --- volume profile
    profs = {lab: _vprofile(c.iloc[-n:], v.iloc[-n:])
             for lab, n in (("1M", 22), ("3M", 63), ("1Y", 252))}
    p3 = profs["3M"]
    va_pos = ("Above value — acceptance up here is bullish; a fall back inside targets the POC" if spot > p3["vah"]
              else "Below value — the auction has rejected higher prices; rallies into VAL often fade" if spot < p3["val"]
              else "Inside value — rotation between VAH and VAL is the base case")
    # --- order flow
    rets = c.pct_change().iloc[-21:]
    vv = v.iloc[-21:]
    upv = float(vv[rets > 0].sum()); dnv = float(vv[rets < 0].sum())
    udr = upv / dnv if dnv else float("inf")
    obv = (v * rets.reindex(v.index).fillna(0).apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))).cumsum()
    obv_rising = bool(obv.iloc[-1] > obv.iloc[-20])
    relv = float(v.iloc[-1] / v.iloc[-21:-1].mean())
    flow = ("Accumulation: up days carry the heavier volume and OBV is rising — buyers are lifting offers. "
            "Support retests are buyable until this flips." if udr > 1.15 and obv_rising else
            "Distribution: down days carry the heavier volume and OBV is falling — sellers are hitting bids. "
            "Treat support retests with suspicion; bounces are for selling until this flips."
            if udr < 0.87 and not obv_rising else
            "Balanced flow — neither side has the volume edge; take the levels more seriously than the tape.")
    # --- reference levels
    levels = []
    for n, lab in ((20, "20-day MA"), (50, "50-day MA"), (100, "100-day MA"), (200, "200-day MA")):
        levels.append((lab, float(c.rolling(n).mean().iloc[-1]), "ma"))
    levels += [("Prior day high", float(h.iloc[-2]), "prior"), ("Prior day low", float(l.iloc[-2]), "prior")]
    wk = df.iloc[-6:-1] if len(df) > 6 else df
    pw = df[df.index >= df.index[-1] - pd.Timedelta(days=12)].iloc[:-1]
    levels += [("Prior week high", float(wdf["High"].iloc[-2]), "prior"),
               ("Prior week low", float(wdf["Low"].iloc[-2]), "prior")]
    mdf = df.resample("ME").agg({"High": "max", "Low": "min"}).dropna()
    if len(mdf) >= 2:
        levels += [("Prior month high", float(mdf["High"].iloc[-2]), "prior"),
                   ("Prior month low", float(mdf["Low"].iloc[-2]), "prior")]
    hi52, lo52 = float(h.iloc[-252:].max()), float(l.iloc[-252:].min())
    levels += [("52-week high", hi52, "prior"), ("52-week low", lo52, "prior")]
    swing_rows = []
    for d, pv in sh[-2:]:
        levels.append((f"Swing high ({d.date()})", pv, "swing")); swing_rows.append((f"Swing high ({d.date()})", pv))
    for d, pv in sl[-2:]:
        levels.append((f"Swing low ({d.date()})", pv, "swing")); swing_rows.append((f"Swing low ({d.date()})", pv))
    # AVWAPs
    avws = []
    for anchor, lab in ((l.iloc[-252:].idxmin(), "AVWAP from 52w low"),
                        (h.iloc[-252:].idxmax(), "AVWAP from 52w high"),
                        (c[c.index.year == NOW.year].index[0] if (c.index.year == NOW.year).any() else None, "AVWAP YTD")):
        if anchor is None:
            continue
        cc, vv2 = c.loc[anchor:], v.loc[anchor:]
        aw = float((cc * vv2).sum() / vv2.sum())
        levels.append((lab, aw, "avwap")); avws.append((lab, aw))
    for lab, prof in profs.items():
        if not prof:
            continue
        levels += [(f"{lab} POC", prof["poc"], "vp"), (f"{lab} VAH", prof["vah"], "vp"),
                   (f"{lab} VAL", prof["val"], "vp")]
        levels += [(f"{lab} HVN", x, "vp") for x in prof["hvn"][:2]]
    # options
    opt = None
    if "-USD" not in tkr:
        try:
            opt = _kl_options(tkr, spot)
            if opt:
                levels += [("Call wall", k, "opt") for k in opt.get("cwalls", [])]
                levels += [("Put wall", k, "opt") for k in opt.get("pwalls", [])]
                if opt.get("maxpain"):
                    levels.append(("Max pain", opt["maxpain"], "opt"))
        except Exception:
            opt = None
    # --- confluence clustering (0.6%)
    levels = [(lab, p, m) for lab, p, m in levels if p and 0.5 * spot < p < 1.6 * spot]
    levels.sort(key=lambda x: x[1])
    clusters = []
    for lab, p, m in levels:
        if clusters and abs(p - clusters[-1]["px"]) / clusters[-1]["px"] < 0.006:
            cl = clusters[-1]
            cl["labels"].append(lab); cl["methods"].add(m)
            cl["px"] = (cl["px"] * (len(cl["labels"]) - 1) + p) / len(cl["labels"])
        else:
            clusters.append(dict(px=p, labels=[lab], methods={m}))
    for cl in clusters:
        cl["score"] = len(cl["labels"])
    above = sorted([c_ for c_ in clusters if c_["px"] > spot], key=lambda c_: c_["px"])[:5]
    below = sorted([c_ for c_ in clusters if c_["px"] <= spot], key=lambda c_: -c_["px"])[:6]
    def ladder_rows(cls_, up):
        out = []
        for cl in cls_:
            d = (cl["px"] / spot - 1) * 100
            sc = cl["score"]
            out.append(
                f'<div style="display:flex;gap:10px;align-items:baseline;padding:7px 0;border-bottom:1px solid var(--line)">'
                f'<b style="min-width:86px">{fmt(cl["px"])}</b>'
                f'<span style="color:{GREEN if up else RED};min-width:64px">{d:+.2f}%</span>'
                f'<span class="pill" style="background:rgba(212,175,90,{min(.06*sc,.35):.2f});color:{GOLD};min-width:26px;text-align:center">{sc}</span>'
                f'<span class="muted" style="font-size:12px">{" · ".join(cl["labels"][:6])}</span></div>')
        return "".join(out)
    nearest_up = above[0] if above else None
    nearest_dn = below[0] if below else None
    pocket = ""
    if nearest_up and nearest_dn:
        pocket = (f"The trade map is the {abs(nearest_dn['px']/spot-1)*100:.2f}% pocket down to "
                  f"{fmt(nearest_dn['px'])} ({nearest_dn['labels'][0]}) versus "
                  f"{(nearest_up['px']/spot-1)*100:.2f}% up to {fmt(nearest_up['px'])} "
                  f"({nearest_up['labels'][0]}).")
    conflict = "" if d_tr.split(" ")[0] == w_tr.split(" ")[0] else " — NOT confirmed by the weekly"
    # --- assemble html
    hh = card(
        f'<div><b>Daily:</b> <span style="color:{GREEN if d_tr.startswith("Up") else (RED if d_tr.startswith("Down") else AMBER)}">{d_tr}</span>'
        f' &nbsp;·&nbsp; <b>Weekly:</b> <span style="color:{GREEN if w_tr.startswith("Up") else (RED if w_tr.startswith("Down") else AMBER)}">{w_tr}</span>'
        f' &nbsp;·&nbsp; <b>Last:</b> {fmt(spot)}</div>'
        f'<div class="muted" style="margin-top:6px">{va_pos}. Daily structure {d_tr.lower()}{conflict}. {pocket}</div>'
        f'<div style="margin-top:8px;font-size:13px">{flow}</div>'
        f'<div class="muted" style="font-size:11px;margin-top:4px">[up/down volume {udr:.2f}× · OBV '
        f'{"rising" if obv_rising else "falling"} · relative volume {relv:.2f}×]</div>', "STRUCTURE & ORDER FLOW")
    hh += card('<div class="slabel" style="margin-bottom:4px">RESISTANCE ABOVE</div>' + ladder_rows(above, True) +
               '<div class="slabel" style="margin:10px 0 4px">SUPPORT BELOW</div>' + ladder_rows(below, False) +
               '<div class="legend">Every level source clustered (0.6% tolerance) and scored by how many '
               'independent inputs agree — a score of 5+ is major structure worth marking before the open.</div>',
               "CONFLUENCE LADDER")
    vp_html = "".join(
        f'<div style="display:inline-block;margin-right:26px"><div class="slabel">{lab}</div>'
        f'<div style="font-size:13px">VAH {fmt(pr["vah"])} · POC <b style="color:{GOLD}">{fmt(pr["poc"])}</b> · VAL {fmt(pr["val"])}</div></div>'
        for lab, pr in profs.items() if pr)
    lvz = " · ".join(fmt(x) for x in (profs["1Y"]["lvn"] if profs["1Y"] else []))
    hh += card(vp_html + (f'<div class="muted" style="margin-top:8px;font-size:12px">Thin zones (price travels '
                          f'fast through these): {lvz}</div>' if lvz else ""),
               "VOLUME PROFILE · POC = the auction's fairest price, value area = 70% of volume")
    if opt:
        em1 = f"±{opt['em_near']:.2f}% → {opt['near']}" if opt.get("em_near") else "—"
        em2 = f"±{opt['em_month']:.2f}% → {opt['month']}" if opt.get("em_month") else "—"
        hh += card(
            f'<div>Call walls (pin/resistance): <b>{" · ".join(fmt(k) for k in opt.get("cwalls", [])) or "—"}</b>'
            f' &nbsp;·&nbsp; Put walls (support→accelerant): <b>{" · ".join(fmt(k) for k in opt.get("pwalls", [])) or "—"}</b>'
            f' &nbsp;·&nbsp; Max pain ({opt["near"][5:]}): <b>{fmt(opt["maxpain"]) if opt.get("maxpain") else "—"}</b></div>'
            f'<div class="muted" style="margin-top:6px">Expected move: {em1} &nbsp;·&nbsp; {em2}. '
            'Walls are where dealer hedging concentrates — call walls cap pinned tapes; put walls hold as '
            'support until they break, then accelerate the move. A confluence level INSIDE the weekly '
            'expected-move band is the one in play this week.</div>', "OPTIONS LEVELS")
    ref_rows = [(lab, fmt(p)) for lab, p, m in levels if m == "ma"] + \
               [(lab, fmt(p)) for lab, p, m in levels if m == "prior"] + \
               [(lab, fmt(p)) for lab, p in avws] + [(lab, fmt(p)) for lab, p in swing_rows]
    hh += card('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:3px 18px">' +
               "".join(f'<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;'
                       f'border-bottom:1px solid var(--line)"><span class="muted">{a}</span><span>{b}</span></div>'
                       for a, b in ref_rows) + "</div>", "REFERENCE LEVELS — THE RAW INPUTS BEHIND THE LADDER")
    return hh

def m_key_levels(px):
    raw = yf.download(KL_TICKERS, period="2y", interval="1d", auto_adjust=True,
                      progress=False, group_by="ticker")
    sections, first_spy = {}, ""
    for t in KL_TICKERS:
        try:
            sections[t] = _kl_ticker(t, raw[t].dropna(how="all"))
        except Exception as e:
            sections[t] = card(f'<span class="muted">Levels unavailable this run ({e}).</span>')
    tabs = "".join(
        f'<button onclick="klshow(\'{t}\')" id="klb-{t}" style="cursor:pointer;font-size:12px;padding:4px 12px;'
        f'border-radius:16px;border:1px solid #232a3a;background:transparent;color:#8891a5;margin:0 6px 8px 0">{t.replace("-USD","")}</button>'
        for t in KL_TICKERS)
    divs = "".join(f'<div id="kl-{t}" style="display:none">{body}</div>' for t, body in sections.items())
    js = ("<script>function klshow(t){%s.forEach(x=>{document.getElementById('kl-'+x).style.display=x===t?'block':'none';"
          "const b=document.getElementById('klb-'+x);b.style.color=x===t?'#d4af5a':'#8891a5';"
          "b.style.borderColor=x===t?'#d4af5a':'#232a3a';});}klshow('SPY');</script>"
          ) % json.dumps(KL_TICKERS)
    body = f"<div>{tabs}</div>{divs}{js}" + card(
        "A level only matters if the market has a reason to defend it. This page generates levels from six "
        "independent methods — volume profile on three windows (where positions actually changed hands), "
        "anchored VWAPs (institutional cost bases), swing structure, prior-period extremes, moving averages, "
        "and dealer options positioning — then clusters anything within 0.6% and scores the cluster by how "
        "many methods agree. One moving average is a line on a chart; a price where the 3-month POC, an "
        "anchored VWAP and a put wall coincide is real structure. Mark the 5+ scores on your TradingView "
        "chart before the open and trade the reactions.", "THE 60-SECOND VERSION")
    spy = px["SPY"].dropna()
    return dict(slug="key-levels", title="Key Levels",
                sub="Six level-generation methods, clustered and scored into one confluence ladder — per ticker.",
                body=body, stance="info",
                headline=f"SPY {spy.iloc[-1]:,.0f} — ladder built from volume, VWAPs, swings, MAs and options")

def _multpl(page, fallback=None):
    try:
        req = urllib.request.Request(f"https://www.multpl.com/{page}",
                                     headers={"User-Agent": "Mozilla/5.0"})
        import re as _re
        html = urllib.request.urlopen(req, timeout=20).read().decode()
        m = _re.search(r"Current[^:]*:\s*<b>?\s*([\d.]+)", html) or \
            _re.search(r'id="current"[^>]*>[^0-9]*([\d.]+)', html)
        return float(m.group(1)) if m else fallback
    except Exception:
        return fallback

def _log_trend_fv(s, since=None):
    import numpy as np
    if since:
        s = s[s.index.year >= since]
    y = np.log(s.values.astype(float))
    x = np.arange(len(y))
    b, a = np.polyfit(x, y, 1)
    fit = float(np.exp(a + b * (len(y) - 1)))
    growth = (math.exp(b * 252) - 1) * 100 if len(s) > 500 else (math.exp(b * 12) - 1) * 100
    return fit, growth

def _anchor_200w(s):
    w = s.resample("W-FRI").last().dropna()
    sma = w.rolling(200).mean().dropna()
    if not len(sma):
        return None
    ratio = (w.loc[sma.index] / sma).loc[lambda r: r.index.year >= 2020]
    return float(sma.iloc[-1] * ratio.median())

VAL_JS = r"""
(function(){
const D=__DATA__,GRN='#4caf7d',RED='#e05555',GOLDC='#d4af5a',MUT='#8891a5';
let asset=Object.keys(D)[0];const off={};
const wrap=document.getElementById('valw');
function fmtp(v,p){return (p>2000?v.toLocaleString(undefined,{maximumFractionDigits:0}):v.toLocaleString(undefined,{maximumFractionDigits:2}));}
function render(){
 const a=D[asset],act=a.models.filter(m=>!off[asset+m.name]);
 const fvs=act.map(m=>m.fv);
 const comp=fvs.length?fvs.reduce((x,y)=>x+y,0)/fvs.length:null;
 const med=fvs.length?fvs.slice().sort((x,y)=>x-y)[Math.floor((fvs.length-1)/2)]:null;
 let h='<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">'+Object.keys(D).map(k=>{
  const dd=D[k],allfv=dd.models.map(m=>m.fv),cc=allfv.reduce((x,y)=>x+y,0)/allfv.length,dv=(cc/dd.price-1)*100;
  return '<button data-a="'+k+'" style="cursor:pointer;font-size:11px;padding:4px 10px;border-radius:14px;border:1px solid '+
   (k===asset?GOLDC:'#232a3a')+';background:'+(k===asset?'rgba(212,175,90,.12)':'transparent')+';color:'+(k===asset?GOLDC:MUT)+'">'+
   dd.name+' <b style="color:'+(dv>=0?GRN:RED)+'">'+(dv>=0?'+':'')+dv.toFixed(1)+'%</b></button>';}).join('')+'</div>';
 if(comp!=null){const dv=(comp/a.price-1)*100;
  h+='<div style="font-size:20px;font-weight:700">'+(a.unit||'')+fmtp(comp,a.price)+
   ' <span style="color:'+(dv>=0?GRN:RED)+'">'+(dv>=0?'+':'')+dv.toFixed(1)+'% vs price</span> '+
   '<span class="pill" style="background:'+(dv<-15?RED:(dv>15?GRN:'#e0a94c'))+'22;color:'+(dv<-15?RED:(dv>15?GRN:'#e0a94c'))+'">'+
   (dv<-15?'OVERVALUED':(dv>15?'UNDERVALUED':'FAIRLY VALUED'))+'</span></div>'+
  '<div class="muted" style="font-size:12px;margin:4px 0 12px">Composite = average of '+act.length+'/'+a.models.length+
   ' active models · median '+(a.unit||'')+fmtp(med,a.price)+' · current price '+(a.unit||'')+fmtp(a.price,a.price)+
   ' · active range '+(a.unit||'')+fmtp(Math.min(...fvs),a.price)+' – '+(a.unit||'')+fmtp(Math.max(...fvs),a.price)+'</div>';}
 a.models.forEach(m=>{const on=!off[asset+m.name],dv=(m.fv/a.price-1)*100;
  h+='<div style="display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--line);opacity:'+(on?1:.4)+'">'+
   '<button data-m="'+m.name+'" style="cursor:pointer;min-width:34px;height:18px;border-radius:9px;border:0;background:'+(on?GRN:'#232a3a')+'"></button>'+
   '<div style="flex:1"><b>'+m.name+'</b> <span style="color:'+(dv>=0?GRN:RED)+'">'+(a.unit||'')+fmtp(m.fv,a.price)+' ('+(dv>=0?'+':'')+dv.toFixed(1)+'%)</span>'+
   '<div class="muted" style="font-size:12px">'+m.f+'</div>'+
   '<div class="muted" style="font-size:11px;font-style:italic">'+m.note+'</div></div></div>';});
 wrap.innerHTML=h;
 wrap.querySelectorAll('button[data-a]').forEach(b=>b.onclick=()=>{asset=b.dataset.a;render();});
 wrap.querySelectorAll('button[data-m]').forEach(b=>b.onclick=()=>{off[asset+b.dataset.m]=!off[asset+b.dataset.m];render();});
}
render();
})();
"""

def m_valuation(px, gspc_m):
    hist = yf.download(["^GSPC", "^NDX", "^RUT", "BTC-USD", "ETH-USD", "GC=F", "SPY", "TLT"],
                       period="max", interval="1d", auto_adjust=True, progress=False)["Close"]
    pe = _multpl("s-p-500-pe-ratio", None)
    if not pe:
        try:
            pe = yf.Ticker("SPY").info.get("trailingPE")
        except Exception:
            pe = None
    cape = _multpl("shiller-pe", None)
    cpi_idx = fred("CPIAUCSL", 4)
    cpi = float((cpi_idx.iloc[-1] / cpi_idx.iloc[-13] - 1) * 100)
    tnx = float(px["^TNX"].dropna().iloc[-1])
    tips = None
    try:
        tips = float(fred("DFII10", 1).iloc[-1])
    except Exception:
        pass
    hy = float(fred("BAMLH0A0HYM2", 1).iloc[-1] * 100)
    data = {}

    def models_for(sym, name, since, unit=""):
        s = hist[sym].dropna()
        price = float(s.iloc[-1])
        ms = []
        fv, gr = _log_trend_fv(s, since)
        ms.append(dict(name="Log-price trend", fv=round(fv, 2),
                       f=f"Exponential fit of log price since {since} · growth {gr:.1f}%/yr",
                       note="Pure time-series gravity — ignores valuation entirely; assumes the historical growth rate persists."))
        a200 = _anchor_200w(s)
        if a200:
            ms.append(dict(name="200-week anchor", fv=round(a200, 2),
                           f="200-week average × the median price/average ratio since 2020",
                           note="A trader's fair value, not an economist's — where price sits vs its own 4-year habit."))
        return s, price, ms

    # --- S&P 500 (full model set)
    s, price, ms = models_for("^GSPC", "S&P 500", 1985)
    if pe:
        eps = price / pe
        ms.insert(0, dict(name="Rule of 20", fv=round(eps * max(20 - cpi, 4), 2),
                          f=f"EPS (${eps:.0f}) × (20 − CPI inflation {cpi:.1f}%)",
                          note="The old desk heuristic: fair P/E plus inflation sums to 20. Simple, venerable, blind to rates and margins."))
        ms.insert(1, dict(name="Fed model", fv=round(eps / (tnx / 100), 2),
                          f=f"EPS ÷ 10-year Treasury yield ({tnx:.2f}%)",
                          note="Sets the earnings yield equal to the 10-year. Famous and flawed — implies infinite value at zero rates; use as a rates-sensitivity bound."))
        ms.insert(2, dict(name="Equity risk premium", fv=round(eps / ((tnx + 2.5) / 100), 2),
                          f=f"EPS ÷ (10y {tnx:.2f}% + 2.5% required premium)",
                          note="Demands stocks out-yield bonds by 2.5pts — near the post-2000 norm. The premium assumption IS the model."))
    if cape:
        ms.insert(3 if pe else 0, dict(name="CAPE reversion", fv=round(price * 26 / cape, 2),
                                       f=f"Price × (post-1990 median CAPE 26 ÷ current {cape:.1f})",
                                       note="Shiller's cyclically-adjusted P/E pulled to its modern-era median. CAPE has read 'expensive' for 30 years — reversion can take a decade."))
    data["spx"] = dict(name="S&P 500", price=price, models=ms)
    # --- NDX / RUT
    for sym, key, name, since in (("^NDX", "ndx", "Nasdaq 100", 1995), ("^RUT", "rut", "Russell 2000", 1995)):
        s2, p2, ms2 = models_for(sym, name, since)
        ratio = (hist[sym] / hist["^GSPC"]).dropna()
        med = float(ratio.iloc[-2520:].median())
        ms2.append(dict(name="S&P-relative reversion", fv=round(float(hist["^GSPC"].dropna().iloc[-1]) * med, 2),
                        f=f"S&P price × 10-year median {name}/S&P ratio ({med:.3f})",
                        note="Relative-value anchor: assumes the index reverts to its decade-normal weight vs the S&P."))
        data[key] = dict(name=name, price=p2, models=ms2)
    # --- BTC / ETH
    s3, p3, ms3 = models_for("BTC-USD", "Bitcoin", 2015, "$")
    import numpy as np
    days = (s3.index - pd.Timestamp("2009-01-03")).days.values.astype(float)
    bpl = np.polyfit(np.log(days), np.log(s3.values.astype(float)), 1)
    ms3.append(dict(name="Power law", fv=round(float(np.exp(bpl[1] + bpl[0] * math.log(days[-1]))), 0),
                    f=f"log(price) = {bpl[1]:.1f} + {bpl[0]:.2f}·log(days since genesis)",
                    note="Bitcoin's price has tracked a power law of its own age for a decade — descriptive, not causal."))
    data["btc"] = dict(name="Bitcoin", price=p3, models=ms3, unit="$")
    s4, p4, ms4 = models_for("ETH-USD", "Ethereum", 2017, "$")
    eb = (hist["ETH-USD"] / hist["BTC-USD"]).dropna()
    ms4.append(dict(name="BTC-relative reversion", fv=round(p3 * float(eb.iloc[-1000:].median()), 0),
                    f=f"BTC price × 4-year median ETH/BTC ratio ({float(eb.iloc[-1000:].median()):.4f})",
                    note="Anchors ETH to its habitual weight against Bitcoin — a pair-trade view of fair value."))
    data["eth"] = dict(name="Ethereum", price=p4, models=ms4, unit="$")
    # --- Gold
    s5, p5, ms5 = models_for("GC=F", "Gold", 2000, "$")
    if tips is not None:
        try:
            ty = fred("DFII10", 10)
            g = hist["GC=F"].dropna()
            both = pd.concat([g, ty], axis=1).dropna()
            bfit = np.polyfit(both.iloc[:, 1].values, np.log(both.iloc[:, 0].values), 1)
            ms5.append(dict(name="Real-yield model", fv=round(float(np.exp(bfit[1] + bfit[0] * tips)), 0),
                            f=f"Regression of log gold on the 10y real yield · today's real yield {tips:.2f}%",
                            note="Gold's classic driver is the real rate: high real yields raise the cost of holding it. Breaks down when central-bank buying dominates — as it has recently."))
        except Exception:
            pass
    data["gold"] = dict(name="Gold", price=p5, models=ms5, unit="$")
    # --- equities vs bonds
    rat = (hist["SPY"] / hist["TLT"]).dropna()
    pr = float(rat.iloc[-1])
    fvr, grr = _log_trend_fv(rat, 2004)
    a200r = _anchor_200w(rat)
    msr = [dict(name="Ratio trend", fv=round(fvr, 2), f=f"Log-trend of SPY/TLT since 2004 · {grr:.1f}%/yr",
                note="Where the stocks-vs-bonds pendulum sits against its long swing.")]
    if a200r:
        msr.append(dict(name="200-week anchor", fv=round(a200r, 2),
                        f="200-week average of the ratio × median deviation since 2020",
                        note="The medium-term habit of the pair."))
    data["eqbond"] = dict(name="Equities vs Bonds", price=pr, models=msr)

    comp_dev = {}
    for k, d in data.items():
        fvs = [m["fv"] for m in d["models"]]
        comp_dev[k] = (sum(fvs) / len(fvs) / d["price"] - 1) * 100
    stance = "bearish" if comp_dev["spx"] < -25 else ("bullish" if comp_dev["spx"] > 15 else "neutral")
    inputs = [("S&P trailing P/E", f"{pe:.1f}" if pe else "—", MUT),
              ("Shiller CAPE", f"{cape:.1f}" if cape else "—", MUT),
              ("10y Treasury", pct(tnx, 2), MUT),
              ("10y real (TIPS)", pct(tips, 2) if tips is not None else "—", MUT),
              ("CPI inflation", pct(cpi), MUT),
              ("HY OAS", f"{hy:.0f} bps", MUT)]
    body = card('<div id="valw">loading…</div><script>' +
                VAL_JS.replace("__DATA__", json.dumps(data, separators=(",", ":"))) + "</script>",
                "MULTI-MODEL FAIR VALUE · TOGGLE ANY MODEL AND EVERYTHING RECOMPUTES") + card(
        stat_grid(inputs), "LIVE MODEL INPUTS") + card(
        "No single valuation model is right, but a panel of independent ones is hard to fool — each attacks "
        "fair value from a different direction (earnings, rates, history, trend, relative value), each shows "
        "its formula and its main weakness, and the composite is simply the average of whatever you leave "
        "switched on. Use it as a return forecast for YEARS, not a signal for Tuesday: a 30% overvaluation "
        "historically means thin forward returns, not an imminent crash — expensive markets get more "
        "expensive all the time. Size positions with it; time entries with the other tabs.",
        "HOW TO USE FAIR VALUE")
    return dict(slug="valuation", title="Valuation",
                sub="A panel of independent fair-value models per asset — composite, median, range, and every formula shown.",
                body=body, stance=stance,
                headline=f"S&P composite {comp_dev['spx']:+.1f}% vs price · BTC {comp_dev['btc']:+.0f}% · Gold {comp_dev['gold']:+.0f}%")

CORR_ASSETS = [("SPY", "S&P 500"), ("QQQ", "NASDAQ"), ("IWM", "Small caps"),
               ("TLT", "Long bonds"), ("GLD", "Gold"), ("DX-Y.NYB", "Dollar"),
               ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ether"), ("CL=F", "Crude"),
               ("HG=F", "Copper"), ("HYG", "HY credit"), ("^VIX", "VIX")]

def m_correlation(px):
    syms = [s for s, _ in CORR_ASSETS]
    extra = [s for s in syms if s not in px.columns]
    dfx = px[[s for s in syms if s in px.columns]].copy()
    if extra:
        add = yf.download(extra, period="1y", interval="1d", auto_adjust=True,
                          progress=False)["Close"]
        if isinstance(add, pd.Series):
            add = add.to_frame(extra[0])
        dfx = dfx.join(add, how="outer")
    rets = dfx[syms].pct_change()
    rets = rets.dropna(how="any")  # align to sessions where every asset traded
    cur = rets.iloc[-60:].corr()
    prev = rets.iloc[-120:-60].corr()
    names = {s: n for s, n in CORR_ASSETS}
    def cell(a, b):
        if a == b:
            return '<td class="muted" style="text-align:center">·</td>'
        v, pv = cur.loc[a, b], prev.loc[a, b]
        d = v - pv
        arrow = (f'<span style="color:{GOLD};font-size:9px"> ▲</span>' if d >= 0.30 else
                 f'<span style="color:{GOLD};font-size:9px"> ▼</span>' if d <= -0.30 else "")
        c = GREEN if v > 0.5 else (RED if v < -0.3 else "var(--tx)")
        return (f'<td title="{names[a]} × {names[b]}: {pv:+.2f} → {v:+.2f} (Δ{d:+.2f})" '
                f'style="color:{c};white-space:nowrap">{v:+.2f}{arrow}</td>')
    hdr = "".join(f'<th style="white-space:nowrap">{n}</th>' for _, n in CORR_ASSETS)
    trs = "".join(f"<tr><td style='white-space:nowrap'><b>{names[a]}</b></td>" +
                  "".join(cell(a, b) for b, _ in CORR_ASSETS) + "</tr>"
                  for a, _ in CORR_ASSETS)
    matrix = (f'<div style="overflow-x:auto"><table style="font-size:12px"><tr><th></th>{hdr}</tr>{trs}</table></div>'
              '<div class="legend">60-session rolling correlation of daily returns (sessions where all 12 '
              'assets traded). Green &gt; +0.5, red &lt; −0.3. ▲▼ flags pairs that shifted ±0.30 or more '
              'versus the prior 60 sessions — hover any cell for the exact change.</div>')
    # regime shifts
    shifts = []
    for i, (a, _) in enumerate(CORR_ASSETS):
        for b, _n in CORR_ASSETS[i + 1:]:
            d = cur.loc[a, b] - prev.loc[a, b]
            if abs(d) >= 0.30:
                shifts.append((abs(d), a, b, prev.loc[a, b], cur.loc[a, b]))
    shifts.sort(reverse=True)
    sh_html = "".join(
        f'<div style="padding:6px 0;border-bottom:1px solid var(--line)"><b>{names[a]} × {names[b]}</b> '
        f'<span class="muted">({pv:+.2f} → {v:+.2f})</span><div class="muted" style="font-size:12px">' +
        ("These two are converging into the same trade — diversification between them is disappearing."
         if v > pv and v > 0.4 else
         "The relationship is decoupling — any hedge that leaned on it needs a recheck." if v < pv else
         "Co-movement is rebuilding after a period of independence.") + "</div></div>"
        for _, a, b, pv, v in shifts[:6]) or '<span class="muted">No ±0.30 shifts this period.</span>'
    # diversifier ranking
    divs = sorted(((cur.loc[a].drop(a).abs().mean(), names[a]) for a, _ in CORR_ASSETS))
    div_html = "".join(
        f'<div style="display:flex;gap:8px;align-items:center;padding:2px 0"><span style="width:90px">{n}</span>'
        f'<div style="flex:1;background:#232a3a;border-radius:3px;height:8px">'
        f'<div style="width:{v*100:.0f}%;background:{GREEN if v<0.42 else (AMBER if v<0.55 else RED)};height:8px;border-radius:3px"></div></div>'
        f'<span class="muted" style="width:40px;text-align:right">{v:.2f}</span></div>' for v, n in divs)
    sb = cur.loc["SPY", "TLT"]
    body = card(matrix, "CROSS-ASSET CORRELATION MATRIX · 60 SESSIONS") + \
        "<h2>Regime shifts — last 60 sessions vs the 60 before</h2>" + card(sh_html) + \
        "<h2>Diversifier ranking</h2>" + card(
            div_html + '<div class="legend">Average |correlation| against the other 11 assets — lowest bar '
            '= the asset actually adding balance to a book right now, measured rather than assumed.</div>') + \
        card("<ul class='pb'>"
             f"<li><b>Stock–bond is the keystone pair</b> — currently {sb:+.2f}. Negative means bonds still "
             "cushion equity drawdowns; positive (as in 2022) removes the shock absorber and changes every "
             "portfolio's risk math.</li>"
             "<li><b>Crypto–NASDAQ measures the narrative</b> — high correlation means crypto is trading as "
             "leveraged tech; a decoupling means its own drivers (liquidity, flows, halving cycle) are in "
             "charge. Check it before calling BTC diversification.</li>"
             "<li><b>Everything → 1 is the fire alarm</b> — in a panic, correlations converge and "
             "diversification fails exactly when it's needed; a uniformly green matrix with a deep-red VIX "
             "row is the crash signature.</li></ul>", "HOW TO READ IT")
    return dict(slug="correlation", title="Correlation Matrix",
                sub="What moves with what — 12 assets, shift detection, and a measured diversifier ranking.",
                body=body, stance="info",
                headline=f"Stock–bond {sb:+.2f} · best diversifier: {divs[0][1]} ({divs[0][0]:.2f})")

MOM_ASSETS = [("^TNX", "10y yield", "rates"), ("TLT", "Long bonds", "rates"),
              ("SPY", "S&P 500", "indices"), ("QQQ", "NASDAQ 100", "indices"),
              ("DIA", "Dow", "indices"), ("IWM", "Russell 2000", "indices"),
              ("DX-Y.NYB", "US dollar", "fx"), ("EURUSD=X", "EUR/USD", "fx"),
              ("BTC-USD", "Bitcoin", "crypto"), ("ETH-USD", "Ethereum", "crypto"),
              ("SOL-USD", "Solana", "crypto"), ("CL=F", "Crude oil", "energy"),
              ("NG=F", "Nat gas", "energy"), ("GC=F", "Gold", "metals"),
              ("SI=F", "Silver", "metals"), ("HG=F", "Copper", "metals"),
              ("^VIX", "VIX", "vol")]

def _rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

MOM_PLAYS = {
    "Trending up": "Pullback and breakout entries with the trend are supported; the stop goes under the last higher low, not under the noise.",
    "Trending down": "Rallies are for selling or standing aside — knife-catching against four aligned timeframes is the lowest-expectancy trade there is.",
    "Extended": "Trail, don't initiate: momentum this stretched rewards holders and punishes chasers. New entries wait for the first real pullback.",
    "Washout": "Mean-reversion only — washouts bounce hard, but the bounce is a trade, not a trend, until the score rebuilds through 50.",
    "Chop": "Stand aside or fade extremes small. Momentum styles bleed here; let the TF blocks realign before pressing.",
}

MOM_JS = r"""
(function(){
const R=__ROWS__,PLAYS=__PLAYS__,GRN='#4caf7d',RED='#e05555',GOLDC='#d4af5a',MUT='#8891a5';
let cat='all',open=null;
const wrap=document.getElementById('momw');
const CATS=['rates','indices','fx','crypto','energy','metals','vol'];
function blocks(r){return ['t','w','m','q'].map(k=>'<span style="color:'+(r[k]>=0?GRN:RED)+'">▮</span>').join('');}
function pc(v,d){return '<span style="color:'+(v>=0?GRN:RED)+'">'+(v>=0?'+':'')+v.toFixed(d===undefined?1:d)+'%</span>';}
function render(){
 const rows=R.filter(r=>cat==='all'||r.cat===cat);
 let h='<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">'+
  [['all','All ('+R.length+')'],...CATS.map(c=>[c,c[0].toUpperCase()+c.slice(1)])]
  .map(([k,l])=>'<button data-c="'+k+'" style="cursor:pointer;font-size:11px;padding:3px 10px;border-radius:14px;border:1px solid '+
   (k===cat?GOLDC:'#232a3a')+';background:'+(k===cat?'rgba(212,175,90,.12)':'transparent')+';color:'+(k===cat?GOLDC:MUT)+'">'+l+'</button>').join('')+'</div>';
 h+='<div style="overflow-x:auto"><table><tr><th>Asset (ranked)</th><th>Score</th><th>Today</th><th>1W</th><th>1M</th><th>3M</th><th>RSI</th><th>TF align</th><th>52w</th><th>Flags</th><th>Regime</th></tr>';
 rows.forEach((r,i)=>{
  const rc=r.regime==='Trending up'?GRN:(r.regime==='Trending down'?RED:(r.regime==='Chop'?MUT:GOLDC));
  h+='<tr data-i="'+i+'" style="cursor:pointer"><td style="white-space:nowrap"><b>'+r.n+'</b> <span class="muted" style="font-size:10px">'+r.cat+'</span></td>'+
   '<td><b style="color:'+(r.score>=65?GRN:(r.score<=35?RED:'#d6dae3'))+'">'+r.score+'</b></td>'+
   '<td>'+pc(r.t,2)+'</td><td>'+pc(r.w)+'</td><td>'+pc(r.m)+'</td><td>'+pc(r.q)+'</td>'+
   '<td style="color:'+(r.rsi>70?RED:(r.rsi<30?GRN:'#d6dae3'))+'">'+r.rsi.toFixed(1)+'</td>'+
   '<td style="letter-spacing:1px">'+blocks(r)+'</td>'+
   '<td><div style="width:56px;background:#232a3a;height:6px;border-radius:3px"><div style="width:'+(r.p52*100).toFixed(0)+'%;background:'+GOLDC+';height:6px;border-radius:3px"></div></div></td>'+
   '<td style="color:'+GOLDC+'">'+(r.acc===1?'▲ ':'')+(r.acc===-1?'▼ ':'')+(r.div?'◆':'')+'</td>'+
   '<td style="color:'+rc+';white-space:nowrap">'+r.regime+'</td></tr>';
  if(open===i)h+='<tr><td colspan="11" style="background:rgba(212,175,90,.05);font-size:12px;color:'+MUT+'">'+
   '<b style="color:'+GOLDC+'">'+r.regime+' playstyle:</b> '+PLAYS[r.regime]+'</td></tr>';});
 h+='</table></div>';
 wrap.innerHTML=h;
 wrap.querySelectorAll('button').forEach(b=>b.onclick=()=>{cat=b.dataset.c;open=null;render();});
 wrap.querySelectorAll('tr[data-i]').forEach(t=>t.onclick=()=>{const i=+t.dataset.i;open=open===i?null:i;render();});
}
render();
})();
"""

def m_momentum(px):
    syms = [s for s, *_ in MOM_ASSETS]
    hist = yf.download(syms, period="2y", interval="1d", auto_adjust=True,
                       progress=False)["Close"].ffill(limit=3)
    rows, callouts = [], []
    for sym, name, catg in MOM_ASSETS:
        s = hist[sym].dropna()
        if len(s) < 260:
            continue
        last = float(s.iloc[-1])
        def ret(d):
            return float((s.iloc[-1] / s.iloc[-d - 1] - 1) * 100)
        t, w, m1, q = ret(1), ret(5), ret(21), ret(63)
        rsi = float(_rsi(s).iloc[-1])
        s20, s50, s200 = (float(s.rolling(k).mean().iloc[-1]) for k in (20, 50, 200))
        struct = (7.5 * (last > s20) + 7.5 * (last > s50) + 7.5 * (last > s200) +
                  7.5 * (s20 > s50 > s200))
        roc21 = s.pct_change(21).dropna().iloc[-252:]
        rocp = float((roc21 < roc21.iloc[-1]).mean()) * 20
        lo52, hi52 = float(s.iloc[-252:].min()), float(s.iloc[-252:].max())
        p52 = (last - lo52) / (hi52 - lo52) if hi52 > lo52 else 0.5
        macd = s.ewm(span=12).mean() - s.ewm(span=26).mean()
        sig = macd.ewm(span=9).mean()
        macd_pts = 7.5 * (macd.iloc[-1] > sig.iloc[-1]) + 7.5 * (macd.iloc[-1] > 0)
        score = round(struct + rsi / 100 * 20 + rocp + p52 * 15 + macd_pts)
        # acceleration: 5-day pace vs the month's run rate
        pace5, pace21 = w / 5, m1 / 21
        acc = 1 if pace5 - pace21 > 0.08 else (-1 if pace21 - pace5 > 0.08 else 0)
        # RSI divergence at fresh 20d extremes
        div = False
        rsis = _rsi(s)
        if last >= float(s.iloc[-20:].max()) - 1e-9:
            prior = s.iloc[-120:-20]
            if len(prior) and float(rsis.iloc[-1]) < float(rsis.loc[prior.idxmax()]) - 2:
                div = True
        elif last <= float(s.iloc[-20:].min()) + 1e-9:
            prior = s.iloc[-120:-20]
            if len(prior) and float(rsis.iloc[-1]) > float(rsis.loc[prior.idxmin()]) + 2:
                div = True
        if rsi > 75 and p52 > 0.95:
            regime = "Extended"
        elif rsi < 25:
            regime = "Washout"
        elif score >= 65 and last > s50:
            regime = "Trending up"
        elif score <= 35:
            regime = "Trending down"
        else:
            regime = "Chop"
        if acc == 1:
            callouts.append(f"▲ Momentum building in {name} — this week is outrunning the monthly trend.")
        if div:
            callouts.append(f"◆ RSI divergence on {name} at a fresh 20-day extreme — reversal watchlist.")
        rows.append(dict(n=name, cat=catg, score=score, t=round(t, 2), w=round(w, 1),
                         m=round(m1, 1), q=round(q, 1), rsi=round(rsi, 1),
                         p52=round(p52, 2), acc=acc, div=div, regime=regime))
    rows.sort(key=lambda r: -r["score"])
    spy_m = px["SPY"].dropna().resample("ME").last()
    sig10 = bool(spy_m.iloc[-1] > spy_m.rolling(10).mean().iloc[-1])
    co_html = "".join(f'<div style="color:{GOLD};font-size:13px;padding:2px 0">{c}</div>'
                      for c in callouts[:5]) or '<span class="muted">No acceleration or divergence callouts this run.</span>'
    payload = json.dumps(rows, separators=(",", ":"))
    body = card(co_html, "SCANNER CALLOUTS — WHAT SURFACED ITSELF") + card(
        '<div id="momw">loading…</div><script>' +
        MOM_JS.replace("__ROWS__", payload).replace("__PLAYS__", json.dumps(MOM_PLAYS)) +
        "</script>",
        f"{len(rows)} ASSETS, FULL MOMENTUM STACK · CLICK A ROW FOR ITS PLAYSTYLE") + card(
        "<ul class='pb'>"
        "<li><b>Score (0–100)</b> = 30% trend structure (price vs the 20/50/200-day averages and their "
        "stacking) + 20% RSI(14) + 20% one-month rate-of-change percentile vs the asset's own year + "
        "15% 52-week range position + 15% MACD(12,26,9) state.</li>"
        "<li><b>TF align</b> — the four blocks are today / 1-week / 1-month / 3-month direction. Four green "
        "= every horizon pushing the same way; mixed = chop, where momentum styles lose their edge.</li>"
        "<li><b>Flags</b> — ▲ the 5-day pace is outrunning the month (freshest momentum); ▼ the week is "
        "fading versus the month; ◆ a fresh 20-day price extreme that RSI refused to confirm.</li>"
        "<li><b>Use the spread</b> — pairing the strongest against the weakest name inside a group is the "
        "cleanest relative-value expression of this table.</li></ul>"
        f"<div style='margin-top:8px'>The slow filter behind it all: the S&P vs its 10-month average is "
        f"<b style='color:{GREEN if sig10 else RED}'>{'RISK-ON' if sig10 else 'RISK-OFF'}</b> — blunt, "
        "whipsaw-prone, and it has still kept accounts out of every major bear market for a century.</div>",
        "METHODOLOGY")
    top = rows[0]
    return dict(slug="momentum", title="Momentum",
                sub="The full momentum stack across 17 assets — scored, ranked, and scanned for what's building, fading, and lying.",
                body=body, stance="bullish" if sig10 else "bearish",
                headline=f"Strongest: {top['n']} ({top['score']}) · 10-month filter {'risk-on' if sig10 else 'risk-off'}")

SEAS_INSTRUMENTS = [("ES", "S&P 500 E-mini", "ES=F"), ("GC", "Gold futures", "GC=F"),
                    ("BTC", "Bitcoin", "BTC-USD"), ("NG", "Natural gas", "NG=F")]

def _seas_pack(s):
    """Per-instrument seasonality dataset for the client-side charts."""
    s = s.dropna()
    cur_y = NOW.year
    years = sorted(set(s.index.year))
    # day-of-year aligned cumulative % paths, one array[367] per year
    paths = {}
    for y in years:
        sy = s[s.index.year == y]
        if len(sy) < 30 and y != cur_y:
            continue
        cum = (sy / sy.iloc[0] - 1) * 100
        arr = [None] * 367
        arr[0] = 0.0
        for d, v in cum.items():
            arr[d.dayofyear] = round(float(v), 2)
        last = 0.0
        for i in range(1, 367):
            if arr[i] is None:
                arr[i] = last
            else:
                last = arr[i]
        paths[y] = arr
    def avg_path(w):
        yrs = [y for y in paths if y < cur_y][-w:]
        if len(yrs) < 3:
            return None
        return [round(sum(paths[y][i] for y in yrs) / len(yrs), 2) for i in range(367)]
    ytd = paths.get(cur_y)
    doy_now = NOW.timetuple().tm_yday
    if ytd:
        ytd = [v if i <= doy_now else None for i, v in enumerate(ytd)]
    # monthly averages + hit rate
    mr = s.resample("ME").last().pct_change().dropna() * 100
    mo = [[round(float(mr[mr.index.month == m].mean()), 2),
           round(float((mr[mr.index.month == m] > 0).mean() * 100), 0)] for m in range(1, 13)]
    # trading-day-of-month grid (12 x 23)
    dr = s.pct_change().dropna() * 100
    tdi = dr.groupby([dr.index.year, dr.index.month]).cumcount() + 1
    grid = []
    for m in range(1, 13):
        row = []
        for td in range(1, 24):
            v = dr[(dr.index.month == m) & (tdi == td)]
            row.append(round(float(v.mean()), 3) if len(v) >= 5 else None)
        grid.append(row)
    return dict(w5=avg_path(5), w10=avg_path(10), w15=avg_path(15), ytd=ytd,
                mo=mo, grid=grid, since=int(years[0]), bars=len(s),
                last=round(float(s.iloc[-1]), 2),
                chg=round(float((s.iloc[-1] / s.iloc[-2] - 1) * 100), 2))

SEAS_JS = r"""
(function(){
const D=__DATA__,MN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const GRN='#4caf7d',RED='#e05555',GOLDC='#d4af5a',BLU='#5aa2d4',MUT='#8891a5';
let inst='ES',view='overlay';
const wrap=document.getElementById('seas'),tip=document.getElementById('stip');
function tabs(id,items,cur,fn){return '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 10px">'+items.map(([k,l])=>
 '<button data-'+id+'="'+k+'" style="cursor:pointer;font-size:12px;padding:4px 12px;border-radius:16px;border:1px solid '+
 (k===cur?GOLDC:'#232a3a')+';background:'+(k===cur?'rgba(212,175,90,.12)':'transparent')+';color:'+
 (k===cur?GOLDC:'#8891a5')+'">'+l+'</button>').join('')+'</div>';}
function render(){
 const d=D[inst];if(!d){wrap.innerHTML='data unavailable';return}
 let h=tabs('i',Object.keys(D).map(k=>[k,k+' · '+D[k].name]),inst,0);
 h+='<div class="muted" style="font-size:12px;margin-bottom:6px">Latest '+d.last.toLocaleString()+
    ' · <span style="color:'+(d.chg>=0?GRN:RED)+'">'+(d.chg>=0?'+':'')+d.chg+'%</span> · '+
    d.bars.toLocaleString()+' sessions · history since '+d.since+'</div>';
 h+=tabs('v',[['overlay','Year-path overlay'],['monthly','Monthly bars'],['days','Day-of-month pattern'],['grid','Month × day grid']],view,0);
 h+='<div id="sviz"></div>';
 wrap.innerHTML=h;
 wrap.querySelectorAll('button').forEach(b=>b.onclick=()=>{if(b.dataset.i)inst=b.dataset.i;if(b.dataset.v)view=b.dataset.v;render();});
 const viz=document.getElementById('sviz');
 if(view==='overlay')overlay(viz,d);else if(view==='monthly')monthly(viz,d);
 else if(view==='days')days(viz,d);else grid(viz,d);
}
function overlay(el,d){
 const W=860,H=320,P=40,S=[['15-year avg',d.w15,GRN],['10-year avg',d.w10,BLU],['5-year avg',d.w5,MUT],['YTD',d.ytd,GOLDC]].filter(s=>s[1]);
 let vals=[];S.forEach(s=>s[1].forEach(v=>{if(v!=null)vals.push(v)}));
 const lo=Math.min(...vals),hi=Math.max(...vals),rg=(hi-lo)||1;
 const X=i=>P+(W-2*P)*(i-1)/365,Y=v=>P+(H-2*P)*(1-(v-lo)/rg);
 let g='<rect x="'+P+'" y="'+P+'" width="'+(W-2*P)+'" height="'+(H-2*P)+'" fill="none" stroke="#232a3a"/>';
 if(lo<0&&hi>0)g+='<line x1="'+P+'" x2="'+(W-P)+'" y1="'+Y(0)+'" y2="'+Y(0)+'" stroke="'+MUT+'" stroke-width="0.6" stroke-dasharray="3 4"/>';
 for(let m=0;m<12;m++){const x=X(m*30.4+1);g+='<text x="'+x+'" y="'+(H-14)+'" fill="'+MUT+'" font-size="10">'+MN[m]+'</text>';}
 [lo,lo+rg/2,hi].forEach(v=>{g+='<text x="4" y="'+(Y(v)+3)+'" fill="'+MUT+'" font-size="10">'+v.toFixed(0)+'%</text>';});
 const doy=Math.min(366,Math.floor((Date.now()-Date.UTC(new Date().getUTCFullYear(),0,0))/864e5));
 g+='<line x1="'+X(doy)+'" x2="'+X(doy)+'" y1="'+P+'" y2="'+(H-P)+'" stroke="'+GOLDC+'" stroke-width="0.6" stroke-dasharray="4 4"/>';
 S.forEach(([n,a,c])=>{let pts=[];for(let i=1;i<367;i++)if(a[i]!=null)pts.push(X(i).toFixed(1)+','+Y(a[i]).toFixed(1));
  g+='<polyline points="'+pts.join(' ')+'" fill="none" stroke="'+c+'" stroke-width="'+(n==='YTD'?2.2:1.4)+'"/>';});
 el.innerHTML='<svg id="ssvg" viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto">'+g+
  '<line id="cx" y1="'+P+'" y2="'+(H-P)+'" stroke="#d6dae3" stroke-width="0.5" visibility="hidden"/></svg>'+
  '<div class="legend">'+S.map(([n,,c])=>'<span style="color:'+c+'">▬</span> '+n).join(' · ')+
  ' · cumulative % from the first session of the year, aligned by calendar day. When the YTD line hugs the averages, the year is behaving seasonally; a hard split from them is information on its own.</div>';
 const svg=document.getElementById('ssvg'),cx=document.getElementById('cx');
 svg.addEventListener('mousemove',e=>{
  const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)*W/r.width;
  const i=Math.max(1,Math.min(366,Math.round((x-P)/(W-2*P)*365+1)));
  if(x<P||x>W-P){tip.style.display='none';cx.setAttribute('visibility','hidden');return}
  cx.setAttribute('x1',X(i));cx.setAttribute('x2',X(i));cx.setAttribute('visibility','visible');
  tip.innerHTML='<b>Day '+i+'</b><br>'+S.map(([n,a,c])=>'<span style="color:'+c+'">'+n+': '+
   (a[i]==null?'—':(a[i]>=0?'+':'')+a[i].toFixed(2)+'%')+'</span>').join('<br>');
  tip.style.display='block';tip.style.left=Math.min(e.clientX+14,innerWidth-170)+'px';tip.style.top=(e.clientY+14)+'px';});
 svg.addEventListener('mouseleave',()=>{tip.style.display='none';cx.setAttribute('visibility','hidden');});
}
function monthly(el,d){
 const W=860,H=260,P=36,vals=d.mo.map(m=>m[0]),lo=Math.min(0,...vals),hi=Math.max(0,...vals),rg=(hi-lo)||1;
 const Y=v=>P+(H-2*P)*(1-(v-lo)/rg),y0=Y(0),bw=(W-2*P)/12*0.6,cm=new Date().getUTCMonth();
 let g='<line x1="'+P+'" x2="'+(W-P)+'" y1="'+y0+'" y2="'+y0+'" stroke="'+MUT+'" stroke-width="0.7"/>';
 vals.forEach((v,i)=>{const x=P+(W-2*P)*(i+0.2)/12,yy=Y(v),c=i===cm?GOLDC:(v>=0?GRN:RED);
  g+='<rect x="'+x+'" y="'+Math.min(yy,y0)+'" width="'+bw+'" height="'+Math.max(Math.abs(y0-yy),1)+'" fill="'+c+'" opacity="0.85"><title>'+MN[i]+': '+(v>=0?'+':'')+v+'% avg, '+d.mo[i][1]+'% positive</title></rect>';
  g+='<text x="'+(x+bw/2)+'" y="'+(H-16)+'" fill="'+MUT+'" font-size="10" text-anchor="middle">'+MN[i]+'</text>';
  g+='<text x="'+(x+bw/2)+'" y="'+(H-4)+'" fill="'+MUT+'" font-size="8" text-anchor="middle">'+d.mo[i][1]+'%</text>';});
 el.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto">'+g+'</svg>'+
  '<div class="legend">Average calendar-month return over the full history (since '+d.since+') · bottom row = share of years the month closed positive · gold = current month. Hover a bar for exact numbers.</div>';
}
function days(el,d){
 const cm=new Date().getUTCMonth();
 let sel='<select id="msel" style="background:#0d1017;color:#d6dae3;border:1px solid #232a3a;border-radius:6px;padding:4px 8px;font-size:12px;margin-bottom:8px">'+
  MN.map((m,i)=>'<option value="'+i+'"'+(i===cm?' selected':'')+'>'+m+'</option>').join('')+'<option value="-1">All months</option></select>';
 el.innerHTML=sel+'<div id="dviz"></div>';
 const draw=mi=>{
  const row=mi<0?Array.from({length:23},(_,t)=>{const vs=d.grid.map(r=>r[t]).filter(v=>v!=null);
    return vs.length?vs.reduce((a,b)=>a+b,0)/vs.length:null}):d.grid[mi];
  const W=860,H=240,P=36,vals=row.filter(v=>v!=null),lo=Math.min(0,...vals),hi=Math.max(0,...vals),rg=(hi-lo)||1;
  const Y=v=>P+(H-2*P)*(1-(v-lo)/rg),y0=Y(0),bw=(W-2*P)/23*0.6;
  let g='<line x1="'+P+'" x2="'+(W-P)+'" y1="'+y0+'" y2="'+y0+'" stroke="'+MUT+'" stroke-width="0.7"/>';
  row.forEach((v,i)=>{if(v==null)return;const x=P+(W-2*P)*(i+0.2)/23,yy=Y(v);
   g+='<rect x="'+x+'" y="'+Math.min(yy,y0)+'" width="'+bw+'" height="'+Math.max(Math.abs(y0-yy),1)+'" fill="'+(v>=0?GRN:RED)+'" opacity="0.85"><title>Trading day '+(i+1)+': '+(v>=0?'+':'')+v.toFixed(3)+'%/day avg</title></rect>';
   if(i%2===0)g+='<text x="'+(x+bw/2)+'" y="'+(H-8)+'" fill="'+MUT+'" font-size="9" text-anchor="middle">'+(i+1)+'</text>';});
  document.getElementById('dviz').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto">'+g+'</svg>'+
   '<div class="legend">Average % return on each trading day of the month (day 1 = first session). Use it to time entries you already planned inside the month — the turn-of-month days usually carry the drift.</div>';};
 draw(cm);document.getElementById('msel').onchange=e=>draw(+e.target.value);
}
function grid(el,d){
 let mx=0;d.grid.forEach(r=>r.forEach(v=>{if(v!=null)mx=Math.max(mx,Math.abs(v))}));
 let h='<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:10px"><tr><th style="padding:3px 6px"></th>';
 for(let t=1;t<=23;t++)h+='<th style="padding:3px 4px;color:#8891a5">'+t+'</th>';h+='</tr>';
 d.grid.forEach((row,m)=>{h+='<tr><td style="padding:3px 6px;color:#8891a5;font-weight:600">'+MN[m]+'</td>';
  row.forEach((v,t)=>{if(v==null){h+='<td></td>';return}
   const a=Math.min(0.9,Math.abs(v)/mx),c=v>=0?'76,175,125':'224,85,85';
   h+='<td title="'+MN[m]+' · trading day '+(t+1)+': '+(v>=0?'+':'')+v.toFixed(3)+'%" style="padding:3px 4px;background:rgba('+c+','+a.toFixed(2)+');border:1px solid #0d1017;text-align:center;min-width:22px">'+(Math.abs(v)>=0.05?(v>0?'+':'−'):'')+'</td>';});
  h+='</tr>';});
 el.innerHTML=h+'</table></div><div class="legend">Every month × trading-day cell, colored by average daily return over the full history (green = positive drift, red = negative; intensity = size). Hover any cell for the exact number. The vertical green band at the month edges is the turn-of-month effect.</div>';
}
render();
})();
"""

def m_seasonality(gspc_m):
    data = {}
    for code, name, tk in SEAS_INSTRUMENTS:
        try:
            s = yf.download(tk, period="max", interval="1d", auto_adjust=True,
                            progress=False)["Close"].squeeze()
            pack = _seas_pack(s)
            pack["name"] = name
            data[code] = pack
        except Exception:
            continue
    if "ES" not in data:
        raise RuntimeError("seasonality: ES download failed")
    # headline/stance from long S&P history (1950+)
    m = gspc_m.pct_change().dropna()
    m = m[m.index.year >= 1950]
    avg = m.groupby(m.index.month).mean() * 100
    winr = m.groupby(m.index.month).apply(lambda g: (g > 0).mean() * 100)
    cur = NOW.month
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    stance = "bullish" if avg[cur] > 0.5 else ("bearish" if avg[cur] < 0 else "neutral")
    payload = json.dumps(data, separators=(",", ":"))
    body = card('<div id="seas">loading…</div>'
                '<div id="stip" style="display:none;position:fixed;z-index:9;background:#141926;'
                'border:1px solid #232a3a;border-radius:8px;padding:8px 11px;font-size:12px;'
                'pointer-events:none;line-height:1.5"></div>'
                "<script>" + SEAS_JS.replace("__DATA__", payload) + "</script>",
                "SEASONAL BEHAVIOR · PICK AN INSTRUMENT AND A VIEW") + card(
        f"<b>{labels[cur-1]}</b> has averaged <b style='color:{GREEN if avg[cur]>0 else RED}'>{avg[cur]:+.2f}%</b> "
        f"on the S&P with a {winr[cur]:.0f}% hit rate since 1950. Seasonality measures the recurring footprint "
        "of flows — tax dates, rebalancing, holiday liquidity, harvest and inventory cycles in commodities, "
        "futures roll dates. It is a probabilistic tilt, never a guarantee: use it to size and time risk you "
        "already wanted to take, not as a trade on its own. The classics: Nov–Apr carries most of the equity "
        "market's annual return, September is the only reliably negative month, and October is a bottom-maker, "
        "not a top-maker.", "THIS MONTH IN CONTEXT")
    return dict(slug="seasonality", title="Seasonality",
                sub="The calendar's recurring footprint — year-path overlays, monthly drift, and day-of-month patterns across four instruments.",
                body=body, stance=stance,
                headline=f"{labels[cur-1]} averages {avg[cur]:+.2f}% since 1950")

def m_calendar(gspc_d):
    r = gspc_d.pct_change().dropna()
    r = r[r.index.year >= 2000]
    dows = r.groupby(r.index.dayofweek).mean() * 100
    dlab = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    # turn of month: last trading day + first 3
    idx = r.index
    tom_mask = pd.Series(False, index=idx)
    months = pd.Series(idx.month, index=idx)
    starts = months.ne(months.shift(1))
    for i in range(len(idx)):
        if starts.iloc[i]:
            for j in range(max(0, i - 1), min(len(idx), i + 3)):
                tom_mask.iloc[j] = True
    tom, rest = r[tom_mask].mean() * 100, r[~tom_mask].mean() * 100
    body = card(bar_chart(dlab, [dows.get(i, 0) for i in range(5)]) +
                '<div class="legend">Average S&P daily return by weekday since 2000.</div>',
                "DAY-OF-WEEK DRIFT") + card(
        f"Turn-of-month window (last session + first three of each month) has averaged "
        f"<b style='color:{GREEN if tom > rest else RED}'>{tom:+.3f}%/day</b> vs {rest:+.3f}%/day on all other days "
        "since 2000 — the single most persistent calendar effect, driven by pension and payroll flows. "
        "These edges are thin and best used for timing entries you already wanted to make, not as trades "
        "in themselves.", "TURN-OF-MONTH EFFECT")
    return dict(slug="calendar", title="Calendar Effects",
                sub="The micro-seasonality inside the month and week — flow-driven drift patterns.",
                body=body, stance="info",
                headline=f"Turn-of-month drift {tom:+.2f}%/day vs {rest:+.2f}% baseline")

def m_election(gspc_m):
    m = gspc_m.pct_change().dropna()
    m = m[m.index.year >= 1950]
    cyc = (m.index.year % 4)  # 0=election yr, 1=post, 2=midterm, 3=pre
    names = {0: "Election year", 1: "Post-election", 2: "Midterm", 3: "Pre-election"}
    avg_yr = {c: m[cyc == c].groupby(m[cyc == c].index.year).apply(lambda g: (1 + g).prod() - 1).mean() * 100
              for c in range(4)}
    cur_c = NOW.year % 4
    stance = "bullish" if avg_yr[cur_c] > 8 else "neutral"
    body = card(bar_chart([names[c] for c in range(4)], [avg_yr[c] for c in range(4)],
                          highlight=cur_c) +
                '<div class="legend">Average S&P 500 total-year return by presidential-cycle year since 1950 · gold = current.</div>',
                "THE FOUR-YEAR CYCLE") + card(
        f"{NOW.year} is a <b>{names[cur_c].lower()}</b> year (averages {avg_yr[cur_c]:+.1f}%). The classic pattern: "
        "midterm years run weak and choppy into autumn, then launch the strongest 12-month window of the cycle; "
        "pre-election years are historically the best full year. The mechanism is policy — administrations "
        "stimulate into re-election. Treat it as context, not destiny: single cycles deviate wildly.",
        "WHERE WE ARE")
    return dict(slug="election-cycle", title="Election Cycle",
                sub="The four-year policy rhythm in equity returns — where this year sits in the pattern.",
                body=body, stance=stance,
                headline=f"{names[cur_c]} year — historical average {avg_yr[cur_c]:+.1f}%")

def m_yield_curve():
    t10y3m, t10y2y = fred("T10Y3M"), fred("T10Y2Y")
    v3m, v2y = t10y3m.iloc[-1], t10y2y.iloc[-1]
    inv = v3m < 0
    stance = "bearish" if inv else "neutral"
    steepening = v3m > t10y3m.iloc[-64]
    body = card(stat_grid([("10y − 3m", f"{v3m:+.2f} pts", col(v3m, lambda v: v > 0)),
                           ("10y − 2y", f"{v2y:+.2f} pts", col(v2y, lambda v: v > 0)),
                           ("3-month direction", "steepening" if steepening else "flattening",
                            GREEN if steepening and not inv else AMBER)]) +
                '<div class="muted" style="margin-top:10px">The inversion itself is the warning shot; the '
                'recession historically arrives after the curve <i>re-steepens</i> out of inversion — because '
                're-steepening means the market smells rate cuts coming. Steep and steepening from positive '
                'territory is the healthy expansion configuration.</div>', "CURVE SNAPSHOT") + card(
        line_chart([t10y3m.iloc[-1260:].tolist()], [BLUE], hlines=[(0, RED, "0")]) +
        '<div class="legend">10-year minus 3-month Treasury spread, last ~5 years (FRED T10Y3M). '
        'Below zero = inverted.</div>')
    return dict(slug="yield-curve", title="Yield Curve",
                sub="The bond market's growth forecast — the single best-documented recession signal.",
                body=body, stance=stance,
                headline=f"10y−3m {v3m:+.2f} — {'inverted' if inv else 'positive'}")

def m_credit():
    hy = fred("BAMLH0A0HYM2")
    lvl = hy.iloc[-1] * 100  # to bps
    p = pctile(hy, hy.iloc[-1])
    widening = hy.iloc[-1] > hy.iloc[-64] * 1.1
    stance = "bearish" if widening or lvl > 500 else "bullish" if lvl < 350 else "neutral"
    body = card(stat_grid([("HY spread (OAS)", f"{lvl:.0f} bps", col(lvl, lambda v: v < 400, lambda v: v > 500)),
                           ("5y percentile", pct(p, 0), col(p, lambda v: v < 50, lambda v: v > 80)),
                           ("3-month trend", "widening" if widening else "stable/tightening",
                            RED if widening else GREEN)]) +
                '<div class="muted" style="margin-top:10px">Credit is the canary: high-yield spreads widen '
                'BEFORE equity tops far more reliably than the reverse. Tight and stable spreads underwrite '
                'the equity uptrend; a 100+ bps widening while stocks hold their highs is one of the best '
                'sell signals in macro.</div>', "HIGH-YIELD CREDIT") + card(
        line_chart([(hy * 100).iloc[-1260:].tolist()], [BLUE], hlines=[(400, AMBER, "400"), (600, RED, "600")]) +
        '<div class="legend">ICE BofA US High Yield option-adjusted spread, bps, ~5 years (FRED).</div>')
    return dict(slug="credit-spreads", title="Credit Spreads",
                sub="What bond investors charge for default risk — equity's early-warning system.",
                body=body, stance=stance, headline=f"HY spread {lvl:.0f} bps ({pct(p,0)} 5y percentile)")

def m_liquidity():
    walcl = fred("WALCL") / 1000  # millions -> billions
    rrp = fred("RRPONTSYD")       # already billions
    tga = fred("WTREGEN") / 1000  # millions -> billions
    net = (walcl.resample("W").last() - rrp.resample("W").last().reindex(walcl.resample("W").last().index).ffill()
           - tga.resample("W").last().reindex(walcl.resample("W").last().index).ffill()).dropna()
    chg3m = (net.iloc[-1] - net.iloc[-13])
    stance = "bullish" if chg3m > 0 else "bearish"
    body = card(stat_grid([("Fed balance sheet", f"${walcl.iloc[-1]/1000:,.2f}T", MUT),
                           ("Reverse repo (drain)", f"${rrp.iloc[-1]:,.0f}B", MUT),
                           ("Treasury account (drain)", f"${tga.iloc[-1]:,.0f}B", MUT),
                           ("Net liquidity", f"${net.iloc[-1]/1000:,.2f}T", MUT),
                           ("3-month change", f"${chg3m:+,.0f}B", col(chg3m, lambda v: v > 0))]) +
                '<div class="muted" style="margin-top:10px">Net liquidity = Fed balance sheet − reverse repo − '
                'Treasury general account: the dollars actually available to the financial system. Risk assets '
                'have tracked its direction closely since 2020 — expanding liquidity is a tailwind for '
                'everything with duration, led by tech and crypto.</div>', "US NET LIQUIDITY") + card(
        line_chart([(net / 1000).iloc[-156:].tolist()], [GOLD]) +
        '<div class="legend">Net liquidity in $T, weekly, last ~3 years (FRED WALCL − RRPONTSYD − WTREGEN).</div>')
    return dict(slug="liquidity", title="Global Liquidity",
                sub="The money actually available to markets — the tide that lifts or strands all boats.",
                body=body, stance=stance, headline=f"Net liquidity {'expanding' if chg3m>0 else 'contracting'} (${chg3m:+,.0f}B / 3m)")

def m_finconditions():
    nfci = fred("NFCI")
    lvl = nfci.iloc[-1]
    easing = lvl < nfci.iloc[-13]
    stance = "bullish" if lvl < 0 and easing else ("bearish" if lvl > 0 else "neutral")
    body = card(stat_grid([("Chicago Fed NFCI", f"{lvl:+.2f}", col(lvl, lambda v: v < 0)),
                           ("3-month direction", "easing" if easing else "tightening",
                            GREEN if easing else RED)]) +
                '<div class="muted" style="margin-top:10px">Negative NFCI = conditions looser than average '
                '(cheap money, easy credit, calm vol) — the environment where drawdowns stay shallow. '
                'Crossings above zero have coincided with every major risk-off episode. Watch the direction '
                'more than the level.</div>', "FINANCIAL CONDITIONS") + card(
        line_chart([nfci.iloc[-260:].tolist()], [BLUE], hlines=[(0, RED, "0")]) +
        '<div class="legend">Chicago Fed National Financial Conditions Index, weekly, ~5 years. Above 0 = tight.</div>')
    return dict(slug="financial-conditions", title="Financial Conditions",
                sub="One number for how easy money is across credit, leverage, and risk markets.",
                body=body, stance=stance,
                headline=f"NFCI {lvl:+.2f} — {'loose' if lvl<0 else 'tight'} and {'easing' if easing else 'tightening'}")

def m_business_cycle():
    unrate = fred("UNRATE", 10)
    sahm = unrate.rolling(3).mean() - unrate.rolling(3).mean().rolling(12).min()
    sv = sahm.iloc[-1]
    indpro = fred("INDPRO", 10)
    ip_yoy = (indpro.iloc[-1] / indpro.iloc[-13] - 1) * 100
    t10y3m = fred("T10Y3M", 3).iloc[-1]
    score = sum([sv < 0.5, ip_yoy > 0, t10y3m > 0])
    phase = {3: ("Expansion", GREEN, "bullish"), 2: ("Late cycle", AMBER, "neutral"),
             1: ("Slowdown", AMBER, "bearish"), 0: ("Contraction risk", RED, "bearish")}[score]
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{phase[1]}">{phase[0]}</div>' +
        stat_grid([("Unemployment", pct(unrate.iloc[-1]), MUT),
                   ("Sahm rule gap", f"{sv:+.2f}", col(sv, lambda v: v < 0.5)),
                   ("Industrial prod. YoY", sgn(ip_yoy), col(ip_yoy, lambda v: v > 0)),
                   ("Curve (10y−3m)", f"{t10y3m:+.2f}", col(t10y3m, lambda v: v > 0))]) +
        '<div class="muted" style="margin-top:10px">Three lights: labor (Sahm rule — a 0.50pt rise in the '
        '3-month average unemployment rate off its low has called every post-war recession), production '
        '(industrial output growth), and the curve. Three green = expansion; each light that goes out '
        'moves the cycle clock forward.</div>', "CYCLE DASHBOARD") + card(
        line_chart([unrate.iloc[-120:].tolist()], [BLUE]) +
        '<div class="legend">US unemployment rate, last 10 years (FRED UNRATE). Cycle lows in unemployment '
        'are late-cycle by definition — the turn up, not the level, is the danger signal.</div>')
    return dict(slug="business-cycle", title="Business Cycle",
                sub="Where the real economy sits — the slow clock behind every market regime.",
                body=body, stance=phase[2], headline=f"{phase[0]} — {score}/3 lights green")

def m_fed_path(px):
    effr = fred("DFF", 1).iloc[-1]
    zq = px["ZQ=F"].dropna()
    implied = 100 - zq.iloc[-1]
    gap = implied - effr
    stance = "bullish" if gap < -0.05 else ("bearish" if gap > 0.05 else "neutral")
    exp_txt = ("cuts priced into the front contract" if gap < -0.05 else
               "hikes priced into the front contract" if gap > 0.05 else
               "no change priced in near term")
    body = card(stat_grid([("Effective Fed funds", pct(effr, 2), MUT),
                           ("Futures-implied (front)", pct(implied, 2), MUT),
                           ("Implied − actual", f"{gap:+.2f} pts", col(gap, lambda v: v < 0))]) +
                f'<div class="muted" style="margin-top:10px">Fed funds futures (ZQ) price the average funds '
                f'rate over the contract month — right now: <b>{exp_txt}</b>. This is a simplified read from '
                'the front contract; full meeting-by-meeting probabilities need the whole futures strip. The '
                'direction of travel is what matters for assets: easing cycles that happen WITHOUT a recession '
                'are historically the strongest equity environment there is.</div>', "WHAT'S PRICED IN")
    return dict(slug="fed-path", title="Fed Path",
                sub="What the rates market expects the Fed to do — read from Fed funds futures.",
                body=body, stance=stance, headline=f"EFFR {pct(effr,2)}, {exp_txt}")

def _fg_scale(series, invert=False, win=252):
    """Rolling percentile of the latest value -> 0..100 (optionally inverted)."""
    s = series.dropna().iloc[-win:]
    p = float((s < s.iloc[-1]).mean() * 100)
    return 100 - p if invert else p

def _fg_history(subs, weights=None):
    """Daily composite 0-100 for the last ~260 sessions from sub-series percentiles."""
    df = pd.concat(subs, axis=1).dropna()
    ranks = df.rolling(252, min_periods=120).apply(
        lambda w: float((w < w.iloc[-1]).mean() * 100), raw=False)
    return ranks.mean(axis=1).dropna()

def _mood(v):
    return ("Extreme fear" if v < 25 else "Fear" if v < 45 else
            "Neutral" if v <= 55 else "Greed" if v <= 75 else "Extreme greed")

def _mood_col(v):
    return RED if v < 25 else (AMBER if v < 45 else
           (MUT if v <= 55 else (GREEN if v <= 75 else GOLD)))

def _seasonal_line(score, month_avg, month_n, asset):
    m = NOW.strftime("%B")
    if score < 35 and month_avg > 0.5:
        return (f"Contrarian setup: fear into a seasonally strong {m} "
                f"(avg {month_avg:+.1f}%) — historically the highest-odds long window.", "bullish")
    if score > 70 and month_avg < 0:
        return (f"Crowd offside: greed into a seasonally weak {m} "
                f"(avg {month_avg:+.1f}%) — the calendar and the mood disagree with the longs.", "bearish")
    return (f"Neutral alignment: {m} averages {month_avg:+.1f}% and sentiment isn't extreme — "
            "no calendar edge either way.", "neutral")

def _fg_card(title, score, hist, month_avg, month_n, extra="", tag=""):
    def snap(days):
        if hist is None or len(hist) <= days:
            return None
        return float(hist.iloc[-1 - days])
    strip = "".join(
        f'<div><div class="slabel">{lab}</div><div class="sval" style="color:{_mood_col(v)}">{v:.0f}</div></div>'
        for lab, v in (("now", score), ("1w", snap(5)), ("1m", snap(21)), ("3m", snap(63))) if v is not None)
    line, _ = _seasonal_line(score, month_avg, month_n, title)
    return card(
        f'<div style="display:flex;gap:14px;align-items:baseline"><div style="font-size:30px;font-weight:700;'
        f'color:{_mood_col(score)}">{score:.0f}</div><div><b>{_mood(score)}</b>'
        + (f' <span class="pill" style="background:#232a3a;color:{MUT};font-size:10px">{tag}</span>' if tag else "")
        + f'</div></div><div class="stats" style="margin-top:8px">{strip}</div>'
        + extra +
        f'<div class="muted" style="margin-top:8px;font-size:12px"><b>Seasonal alignment</b> · {line} '
        f'<span style="font-size:10px">(n={month_n} {NOW.strftime("%B")}s)</span></div>', title.upper())

def m_sentiment(px):
    # --- US equities: five sub-gauges, CNN-style construction from raw data
    hist2 = yf.download(["^GSPC", "^VIX", "^VIX3M", "SPY", "TLT", "HYG", "IEF",
                         "GLD", "DX-Y.NYB"], period="3y", interval="1d",
                        auto_adjust=True, progress=False)["Close"].ffill(limit=3)
    spx = hist2["^GSPC"].dropna()
    subs = {
        "S&P momentum (vs 125d)": (spx / spx.rolling(125).mean() - 1),
        "VIX level": -hist2["^VIX"],
        "VIX term structure": hist2["^VIX3M"] / hist2["^VIX"],
        "Stocks vs bonds": (hist2["SPY"].pct_change(20) - hist2["TLT"].pct_change(20)),
        "Junk-bond demand": (hist2["HYG"] / hist2["IEF"]).pct_change(20),
    }
    sub_scores = {k: _fg_scale(v) for k, v in subs.items()}
    eq_hist = _fg_history(list(subs.values()))
    eq_score = float(sum(sub_scores.values()) / len(sub_scores))
    sub_html = ('<div style="margin-top:8px">' + "".join(
        f'<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;'
        f'border-bottom:1px solid var(--line)"><span class="muted">{k}</span>'
        f'<b style="color:{_mood_col(v)}">{v:.0f}</b></div>' for k, v in sub_scores.items()) + "</div>")
    # --- seasonal averages per asset
    def month_stats(sym):
        s = yf.download(sym, period="max", interval="1mo", auto_adjust=True,
                        progress=False)["Close"].squeeze().dropna().pct_change().dropna() * 100
        mm = s[s.index.month == NOW.month]
        return float(mm.mean()), len(mm)
    eq_avg, eq_n = month_stats("^GSPC")
    # --- crypto: alternative.me index
    fng_hist, fng_now = None, None
    try:
        with urllib.request.urlopen("https://api.alternative.me/fng/?limit=400", timeout=20) as r:
            fj = json.loads(r.read())["data"]
        vals = [int(d["value"]) for d in fj][::-1]
        fng_hist = pd.Series(vals)
        fng_now = float(vals[-1])
    except Exception:
        pass
    btc_avg, btc_n = month_stats("BTC-USD")
    # --- funding rates (positioning of the leveraged crowd)
    fund_html = ""
    try:
        rows = []
        for sym in ("BTCUSDT", "ETHUSDT"):
            with urllib.request.urlopen(
                    f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}", timeout=15) as r:
                fr = float(json.loads(r.read())["lastFundingRate"]) * 100
            rows.append((sym[:3], fr))
        fund_html = ('<div style="margin-top:8px;font-size:12px">' + " · ".join(
            f'{n} perp funding <b style="color:{GREEN if f < 0 else (RED if f > 0.03 else "var(--tx)")}">{f:+.4f}%</b>'
            for n, f in rows) +
            '<span class="muted"> — what leveraged traders PAY to hold their bias: heavily positive = '
            'crowded longs (squeeze fuel below), negative = crowded shorts.</span></div>')
    except Exception:
        pass
    # --- gold & dollar proxies (labelled as such)
    def proxy(sym):
        s = hist2[sym].dropna()
        rsi_p = _fg_scale(_rsi(s))
        mom_p = _fg_scale(s.pct_change(63))
        h = _fg_history([_rsi(s), s.pct_change(63)])
        return (rsi_p + mom_p) / 2, h
    gold_score, gold_hist = proxy("GLD")
    dxy_score, dxy_hist = proxy("DX-Y.NYB")
    gold_avg, gold_n = month_stats("GC=F")
    dxy_avg, dxy_n = month_stats("DX-Y.NYB")

    body = _fg_card("US Equities", eq_score, eq_hist, eq_avg, eq_n, extra=sub_html)
    if fng_now is not None:
        body += _fg_card("Crypto", fng_now, fng_hist, btc_avg, btc_n, extra=fund_html,
                         tag="alternative.me index")
    body += _fg_card("Gold", gold_score, gold_hist, gold_avg, gold_n, tag="proxy")
    body += _fg_card("US Dollar", dxy_score, dxy_hist, dxy_avg, dxy_n, tag="proxy")
    body += card(
        "<ul class='pb'>"
        "<li><b>Fade the extremes, not the middle</b> — sub-25 and 75+ are the actionable zones; a 55 is "
        "noise, a 15 into a seasonally strong month is a signal.</li>"
        "<li><b>Read the strip for the trend of mood</b> — 20 today from 60 a month ago is capitulation in "
        "progress; 20 that has sat at 20 for a quarter is a bear regime, not a bottom.</li>"
        "<li><b>Cross the markets</b> — equity greed against crypto fear is a rotation tell; synchronized "
        "extreme fear on all four cards is the washout signature that marks cycle lows.</li>"
        "<li><b>Confirm with funding</b> — crypto fear plus negative perp funding means the crowd is short "
        "AND scared: the highest-octane squeeze setup there is.</li></ul>"
        '<div class="muted" style="margin-top:8px;font-size:12px">Construction: the equities gauge rebuilds '
        'five classic fear/greed inputs from raw data (index momentum vs its 125-day average, VIX level, '
        'VIX term structure, 20-day stock-vs-bond demand, junk-bond demand) as rolling one-year percentiles, '
        'averaged. Crypto uses the alternative.me industry-standard index. Gold and the dollar have no '
        'credible survey, so those cards use an RSI + momentum-percentile proxy — labelled, not disguised.</div>',
        "HOW TO USE IT")
    stance = ("bullish" if eq_score < 25 else "bearish" if eq_score > 75 else "neutral")
    return dict(slug="sentiment", title="Sentiment",
                sub="Each market's mood on one 0–100 scale — equities, crypto, gold, dollar — with history and a seasonal cross-check.",
                body=body, stance=stance,
                headline=f"Equities {eq_score:.0f} ({_mood(eq_score)})" +
                         (f" · Crypto {fng_now:.0f} ({_mood(fng_now)})" if fng_now is not None else ""))

def m_crypto(px):
    btc = px["BTC-USD"].dropna(); eth = px["ETH-USD"].dropna()
    def stats(s):
        return dict(r3=(s.iloc[-1] / s.iloc[-91] - 1) * 100,
                    a200=s.iloc[-1] > s.rolling(200).mean().iloc[-1],
                    dd=(s.iloc[-1] / s.max() - 1) * 100)
    b, e = stats(btc), stats(eth)
    ratio = (eth / btc).dropna()
    r3m = (ratio.iloc[-1] / ratio.iloc[-64] - 1) * 100
    corr = px["BTC-USD"].pct_change().iloc[-63:].corr(px["QQQ"].pct_change().iloc[-63:])
    stance = "bullish" if b["a200"] else "bearish"
    body = card(stat_grid([("BTC vs 200-day", "above" if b["a200"] else "below", GREEN if b["a200"] else RED),
                           ("BTC 3-month", sgn(b["r3"]), col(b["r3"], lambda v: v > 0)),
                           ("BTC from 5y high", sgn(b["dd"]), MUT),
                           ("ETH 3-month", sgn(e["r3"]), col(e["r3"], lambda v: v > 0)),
                           ("ETH/BTC 3m", sgn(r3m), col(r3m, lambda v: v > 0)),
                           ("BTC–QQQ corr (3m)", f"{corr:+.2f}", MUT)]) +
                '<div class="muted" style="margin-top:10px">Two regime reads: Bitcoin above/below its 200-day '
                '(the crypto cycle in one line), and ETH/BTC direction — alts outperforming Bitcoin marks '
                'risk-seeking inside the asset class, alt-underperformance marks defensive crypto tape. The '
                'BTC–Nasdaq correlation shows how much crypto is currently just high-beta tech.</div>',
                "CRYPTO REGIME") + card(
        line_chart([(btc.iloc[-252:] / btc.iloc[-252] * 100).tolist(),
                    (eth.iloc[-252:] / eth.iloc[-252] * 100).tolist()], [GOLD, BLUE]) +
        f'<div class="legend"><span style="color:{GOLD}">▬</span> BTC · <span style="color:{BLUE}">▬</span> ETH, '
        'indexed to 100, last 12 months.</div>')
    return dict(slug="crypto", title="Crypto",
                sub="Bitcoin's trend regime, ETH/BTC risk appetite, and how coupled crypto is to tech.",
                body=body, stance=stance,
                headline=f"BTC {'above' if b['a200'] else 'below'} its 200-day, ETH/BTC {sgn(r3m)} over 3m")

COT_MKTS = [
    ("E-MINI S&P 500", "S&P 500", "ES=F", "indices"),
    ("NASDAQ MINI", "Nasdaq 100", "NQ=F", "indices"),
    ("DJIA", "Dow", "YM=F", "indices"),
    ("RUSSELL E-MINI", "Russell 2000", "RTY=F", "indices"),
    ("VIX FUTURES", "VIX Futures", "^VIX", "other"),
    ("EURO FX", "Euro FX", "EURUSD=X", "currencies"),
    ("JAPANESE YEN", "Japanese Yen", "JPY=X", "currencies"),
    ("BRITISH POUND", "British Pound", "GBPUSD=X", "currencies"),
    ("CANADIAN DOLLAR", "Canadian Dollar", "CADUSD=X", "currencies"),
    ("AUSTRALIAN DOLLAR", "Australian Dollar", "AUDUSD=X", "currencies"),
    ("SWISS FRANC", "Swiss Franc", "CHFUSD=X", "currencies"),
    ("MEXICAN PESO", "Mexican Peso", "MXNUSD=X", "currencies"),
    ("DOLLAR INDEX", "Dollar Index", "DX-Y.NYB", "currencies"),
    ("CRUDE OIL", "Crude Oil (WTI)", "CL=F", "energy"),
    ("NATURAL GAS", "Natural Gas", "NG=F", "energy"),
    ("GOLD", "Gold", "GC=F", "metals"),
    ("SILVER", "Silver", "SI=F", "metals"),
    ("PLATINUM", "Platinum", "PL=F", "metals"),
    ("PALLADIUM", "Palladium", "PA=F", "metals"),
    ("CORN", "Corn", "ZC=F", "grains"),
    ("WHEAT-SRW", "Wheat", "ZW=F", "grains"),
    ("SOYBEANS", "Soybeans", "ZS=F", "grains"),
    ("SOYBEAN OIL", "Soybean Oil", "ZL=F", "grains"),
    ("SOYBEAN MEAL", "Soybean Meal", "ZM=F", "grains"),
    ("SUGAR NO. 11", "Sugar", "SB=F", "softs"),
    ("COFFEE C", "Coffee", "KC=F", "softs"),
    ("COCOA", "Cocoa", "CC=F", "softs"),
    ("COTTON NO. 2", "Cotton", "CT=F", "softs"),
    ("ORANGE JUICE", "Orange Juice", "OJ=F", "softs"),
    ("LIVE CATTLE", "Live Cattle", "LE=F", "meats"),
    ("FEEDER CATTLE", "Feeder Cattle", "GF=F", "meats"),
    ("LEAN HOGS", "Lean Hogs", "HE=F", "meats"),
    ("BITCOIN", "Bitcoin", "BTC-USD", "crypto"),
    ("ETHER", "Ether", "ETH-USD", "crypto"),
]

def _cot_fetch(key):
    q = ("https://publicreporting.cftc.gov/resource/6dca-aqww.json?"
         f"$where=upper(market_and_exchange_names)%20like%20%27%25{urllib.request.quote(key)}%25%27"
         "&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=600"
         "&$select=market_and_exchange_names,report_date_as_yyyy_mm_dd,open_interest_all,"
         "comm_positions_long_all,comm_positions_short_all,noncomm_positions_long_all,"
         "noncomm_positions_short_all,nonrept_positions_long_all,nonrept_positions_short_all")
    with urllib.request.urlopen(q, timeout=40) as r:
        data = json.loads(r.read())
    if not data:
        return None
    latest = data[0]["report_date_as_yyyy_mm_dd"]
    fresh = [d for d in data if d["report_date_as_yyyy_mm_dd"] == latest]
    name = max(fresh, key=lambda d: int(d["open_interest_all"]))["market_and_exchange_names"]
    rows = [d for d in data if d["market_and_exchange_names"] == name][:27]
    if len(rows) < 10:
        return None
    rows.reverse()  # chronological
    def net(d, side):
        return int(d[f"{side}_positions_long_all"]) - int(d[f"{side}_positions_short_all"])
    comm = [net(d, "comm") for d in rows]
    spec = [net(d, "noncomm") for d in rows]
    small = [net(d, "nonrept") for d in rows]
    oi = int(rows[-1]["open_interest_all"])
    def idx(series):
        w = series[-26:]
        lo, hi = min(w), max(w)
        return None if hi == lo else round((w[-1] - lo) / (hi - lo) * 100)
    return dict(date=rows[-1]["report_date_as_yyyy_mm_dd"][:10], oi=oi,
                cn=comm[-1], cw=comm[-1] - comm[-2],
                cp=round(comm[-1] / oi * 100, 1) if oi else 0,
                sn=spec[-1], sp=round(spec[-1] / oi * 100, 1) if oi else 0,
                rn=small[-1], idx=idx(comm), sidx=idx(spec), spark=comm[-26:])

COT_JS = r"""
(function(){
const R=__ROWS__,GRN='#4caf7d',RED='#e05555',GOLDC='#d4af5a',MUT='#8891a5';
let cat='all',sortk='idx',sdesc=true;
const wrap=document.getElementById('cotw');
const CATS=['indices','currencies','energy','metals','grains','softs','meats','crypto','other'];
function fmt(v){return (v>=0?'+':'−')+Math.abs(v).toLocaleString();}
function spark(a){const w=78,h=20,lo=Math.min(...a),hi=Math.max(...a),rg=(hi-lo)||1;
 const pts=a.map((v,i)=>((i/(a.length-1))*w).toFixed(1)+','+(h-2-(v-lo)/rg*(h-4)).toFixed(1)).join(' ');
 const c=a[a.length-1]>=a[0]?GRN:RED;
 return '<svg width="'+w+'" height="'+h+'"><polyline points="'+pts+'" fill="none" stroke="'+c+'" stroke-width="1.2"/></svg>';}
function flagof(r){if(r.star)return '<span title="commercials and large specs at opposite extremes" style="color:'+GOLDC+'">★</span>';
 if(r.ext)return '<span title="COT index at an extreme (≥80 or ≤20)" style="color:'+GOLDC+'">⚡</span>';return '<span class="muted">—</span>';}
function render(){
 let rows=R.filter(r=>cat==='all'||(cat==='ext'?r.ext:cat==='star'?r.star:r.cat===cat));
 rows.sort((a,b)=>{let x=a[sortk],y=b[sortk];if(x==null)return 1;if(y==null)return -1;
  if(typeof x==='string')return sdesc?y.localeCompare(x):x.localeCompare(y);return sdesc?y-x:x-y;});
 const nc=k=>R.filter(r=>r.cat===k).length;
 let h='<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">'+
  [['all','All ('+R.length+')'],...CATS.map(c=>[c,c[0].toUpperCase()+c.slice(1)+' ('+nc(c)+')']),
   ['ext','⚡ Extremes ('+R.filter(r=>r.ext).length+')'],['star','★ Divergences ('+R.filter(r=>r.star).length+')']]
  .map(([k,l])=>'<button data-c="'+k+'" style="cursor:pointer;font-size:11px;padding:3px 10px;border-radius:14px;border:1px solid '+
   (k===cat?GOLDC:'#232a3a')+';background:'+(k===cat?'rgba(212,175,90,.12)':'transparent')+';color:'+(k===cat?GOLDC:MUT)+'">'+l+'</button>').join('')+'</div>';
 h+='<div style="overflow-x:auto"><table><tr>'+
  [['flag','Flag'],['n','Instrument'],['px','Price'],['ch','Δ 1w'],['oi','OI'],['cn','Comm net'],['cp','% of OI'],['cw','Δ WoW'],
   ['sn','Specs net'],['sp','% of OI'],['rn','Small net'],['idx','COT idx'],['spark','26w trend']]
  .map(([k,l])=>'<th style="cursor:pointer;white-space:nowrap" data-s="'+k+'">'+l+(k===sortk?(sdesc?' ↓':' ↑'):'')+'</th>').join('')+'</tr>';
 rows.forEach(r=>{
  h+='<tr><td>'+flagof(r)+'</td><td style="white-space:nowrap"><b>'+r.n+'</b> <span class="muted" style="font-size:10px">'+r.cat+'</span></td>'+
   '<td>'+(r.px!=null?r.px.toLocaleString():'—')+'</td>'+
   '<td style="color:'+(r.ch>=0?GRN:RED)+'">'+(r.ch!=null?(r.ch>=0?'+':'')+r.ch+'%':'—')+'</td>'+
   '<td>'+r.oi.toLocaleString()+'</td>'+
   '<td style="color:'+(r.cn>=0?GRN:RED)+'">'+fmt(r.cn)+'</td><td>'+r.cp+'%</td>'+
   '<td style="color:'+(r.cw>=0?GRN:RED)+'">'+fmt(r.cw)+'</td>'+
   '<td style="color:'+(r.sn>=0?GRN:RED)+'">'+fmt(r.sn)+'</td><td>'+r.sp+'%</td>'+
   '<td style="color:'+(r.rn>=0?GRN:RED)+'">'+fmt(r.rn)+'</td>'+
   '<td style="font-weight:600;color:'+(r.idx==null?MUT:(r.idx>=80||r.idx<=20?GOLDC:'#d6dae3'))+'">'+(r.idx==null?'—':r.idx)+'</td>'+
   '<td>'+spark(r.spark)+'</td></tr>';});
 h+='</table></div>';
 wrap.innerHTML=h;
 wrap.querySelectorAll('button').forEach(b=>b.onclick=()=>{cat=b.dataset.c;render();});
 wrap.querySelectorAll('th').forEach(t=>t.onclick=()=>{const k=t.dataset.s;
  if(k==='spark'||k==='flag')return;if(k===sortk)sdesc=!sdesc;else{sortk=k;sdesc=true;}render();});
}
render();
})();
"""

def m_cot():
    import concurrent.futures as cf
    packs = {}
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(_cot_fetch, key): key for key, *_ in COT_MKTS}
        for f in cf.as_completed(futs):
            try:
                p = f.result()
                if p:
                    packs[futs[f]] = p
            except Exception:
                continue
    if len(packs) < 10:
        raise RuntimeError(f"CFTC API returned only {len(packs)} markets")
    syms = sorted(set(y for k, n, y, c in COT_MKTS if k in packs))
    try:
        pxx = yf.download(syms, period="1mo", interval="1d",
                          auto_adjust=True, progress=False)["Close"].ffill()
    except Exception:
        pxx = pd.DataFrame()
    rows, missing = [], []
    for key, name, ysym, catg in COT_MKTS:
        if key not in packs:
            missing.append(name)
            continue
        p = packs[key]
        px_last = chg = None
        if ysym in getattr(pxx, "columns", []):
            s = pxx[ysym].dropna()
            if len(s) > 5:
                px_last = round(float(s.iloc[-1]), 2 if s.iloc[-1] < 100 else 1)
                chg = round(float((s.iloc[-1] / s.iloc[-6] - 1) * 100), 1)
        ext = p["idx"] is not None and (p["idx"] >= 80 or p["idx"] <= 20)
        star = (p["idx"] is not None and p["sidx"] is not None and
                ((p["idx"] >= 80 and p["sidx"] <= 20) or (p["idx"] <= 20 and p["sidx"] >= 80)))
        rows.append(dict(n=name, cat=catg, px=px_last, ch=chg, ext=ext, star=star, **{
            k: p[k] for k in ("oi", "cn", "cp", "cw", "sn", "sp", "rn", "idx", "spark")}))
    rep_date = max(p["date"] for p in packs.values())
    payload = json.dumps(rows, separators=(",", ":"))
    body = card(
        f'<div class="muted" style="font-size:12px;margin-bottom:8px">Latest CFTC report: <b>{rep_date}</b> '
        '— positions as of that Tuesday\'s close, published each Friday afternoon (US time). '
        f'{len(rows)} markets loaded.'
        + (f' <span style="color:{AMBER}">Unavailable this run: {", ".join(missing)}.</span>' if missing else "")
        + '</div><div id="cotw">loading…</div>'
        "<script>" + COT_JS.replace("__ROWS__", payload) + "</script>",
        "POSITIONING BY TRADER CLASS · CLICK HEADERS TO SORT, PILLS TO FILTER") + card(
        "<ul class='pb'>"
        "<li><b>Commercials</b> — producers and hedgers offsetting real-world exposure. They fade trends "
        "(sell strength, buy weakness) and tend to be early. Treat them as the informed side.</li>"
        "<li><b>Large speculators</b> — funds and managed money, trend-followers. Their extremes mark "
        "crowded trades where the fuel is already spent.</li>"
        "<li><b>Small traders</b> — below reporting size; historically most wrong at turning points.</li>"
        "<li><b>COT index</b> — where the commercials' net sits inside its 26-week range: ≥80 means they're "
        "as long as they've been in six months (⚡ contrarian-bullish zone), ≤20 the opposite. The ★ flag "
        "marks the strongest setup: commercials at one extreme while large specs sit at the other.</li>"
        "<li><b>26w trend</b> — sparkline of the commercials' net position; the slope matters more than "
        "the level.</li></ul>", "HOW TO READ IT")
    ext_names = [r["n"] for r in rows if r["star"]][:4] or [r["n"] for r in rows if r["ext"]][:4]
    return dict(slug="cot", title="COT Positioning",
                sub="Weekly CFTC positioning across the major futures markets, split by trader class — the market's positioning X-ray.",
                body=body, stance="info",
                headline=("Setups: " + ", ".join(ext_names)) if ext_names else "No positioning extremes")

def m_astrology():
    # moon phase from a known new-moon epoch; approximate but fine for display
    epoch = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    syn = 29.53058867
    age = ((NOW - epoch).total_seconds() / 86400) % syn
    illum = (1 - math.cos(2 * math.pi * age / syn)) / 2 * 100
    names = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
             "Full moon", "Waning gibbous", "Last quarter", "Waning crescent"]
    phase = names[int(((age / syn * 8) + 0.5) % 8)]
    next_new = NOW + timedelta(days=syn - age)
    next_full = NOW + timedelta(days=(syn / 2 - age) % syn)
    retro = [("2026-02-26", "2026-03-20"), ("2026-06-29", "2026-07-23"), ("2026-10-24", "2026-11-13")]
    today = NOW.strftime("%Y-%m-%d")
    in_retro = any(a <= today <= b for a, b in retro)
    body = card(stat_grid([("Moon phase", phase, GOLD),
                           ("Illumination", pct(illum, 0), MUT),
                           ("Next new moon", next_new.strftime("%d %b"), MUT),
                           ("Next full moon", next_full.strftime("%d %b"), MUT),
                           ("Mercury retrograde", "yes (approx.)" if in_retro else "no", RED if in_retro else GREEN)]) +
                '<div class="muted" style="margin-top:10px">Filed under entertainment. Academic studies have '
                'found at most a tiny lunar-cycle effect in equity returns (slightly better around new moons) '
                'that mostly disappears after costs; Mercury-retrograde effects have never survived a serious '
                'backtest. It\'s here because traders talk about it — not because it trades. Retrograde windows '
                'are approximate for 2026.</div>', "SKY DASHBOARD")
    return dict(slug="astrology", title="Market Astrology",
                sub="Lunar phases and retrogrades — the fun page. Statistically: noise with a good story.",
                body=body, stance="info", headline=f"{phase}, Mercury {'retrograde' if in_retro else 'direct'}")

def m_screener(px):
    panel_cols = [t for t in PANEL if t in px.columns and px[t].dropna().shape[0] > 260]
    rows = []
    for t in panel_cols:
        s = px[t].dropna()
        s50 = s.rolling(50).mean().iloc[-1]; s200 = s.rolling(200).mean().iloc[-1]
        r1, r3 = (s.iloc[-1] / s.iloc[-22] - 1) * 100, (s.iloc[-1] / s.iloc[-64] - 1) * 100
        rs = r3 - (px["SPY"].dropna().iloc[-1] / px["SPY"].dropna().iloc[-64] - 1) * 100
        rows.append((t, SECTORS[PANEL[t]], s.iloc[-1], (s.iloc[-1] / s50 - 1) * 100,
                     (s.iloc[-1] / s200 - 1) * 100, r1, r3, rs))
    rows.sort(key=lambda r: r[7], reverse=True)
    trs = "\n".join(
        f"<tr><td><b>{t}</b></td><td class='muted'>{sec}</td><td>{p:,.2f}</td>"
        f"<td style='color:{GREEN if a>0 else RED}'>{a:+.1f}%</td>"
        f"<td style='color:{GREEN if b>0 else RED}'>{b:+.1f}%</td>"
        f"<td style='color:{GREEN if c>0 else RED}'>{c:+.1f}%</td>"
        f"<td style='color:{GREEN if d>0 else RED}'>{d:+.1f}%</td>"
        f"<td style='color:{GREEN if e>0 else RED}'>{e:+.1f}%</td></tr>"
        for t, sec, p, a, b, c, d, e in rows)
    body = card(
        '<div class="muted" style="margin-bottom:8px">Mega/large-cap panel ranked by 3-month relative '
        'strength vs SPY. Click a header to re-sort.</div>'
        f"<div style='overflow-x:auto'><table id='scr'><tr>"
        "<th onclick='so(0,0)'>Ticker</th><th onclick='so(1,0)'>Sector</th><th onclick='so(2,1)'>Price</th>"
        "<th onclick='so(3,1)'>vs 50d</th><th onclick='so(4,1)'>vs 200d</th><th onclick='so(5,1)'>1m</th>"
        f"<th onclick='so(6,1)'>3m</th><th onclick='so(7,1)'>RS vs SPY (3m)</th></tr>{trs}</table></div>"
        "<script>function so(i,num){const t=document.getElementById('scr');"
        "const r=[...t.rows].slice(1);const d=t.dataset['s'+i]!=='1';t.dataset['s'+i]=d?'1':'0';"
        "r.sort((a,b)=>{let x=a.cells[i].innerText.replace(/[,%+]/g,''),y=b.cells[i].innerText.replace(/[,%+]/g,'');"
        "return num?(d?y-x:x-y):(d?x.localeCompare(y):y.localeCompare(x));});"
        "r.forEach(x=>t.appendChild(x));}</script>")
    return dict(slug="screener", title="Screener",
                sub="The whole panel, sortable — find the leaders and the broken names in one table.",
                body=body, stance="info",
                headline=f"Top RS: {', '.join(r[0] for r in rows[:3])}")

def m_calculators():
    body = card(
        '<div class="slabel">POSITION SIZE (RISK-FIRST)</div>'
        '<label class="cl">Account $<br><input class="calc" id="c_acct" value="100000"></label>'
        '<label class="cl">Risk %<br><input class="calc" id="c_risk" value="1"></label>'
        '<label class="cl">Entry<br><input class="calc" id="c_in" value="100"></label>'
        '<label class="cl">Stop<br><input class="calc" id="c_st" value="96"></label>'
        '<div id="c_out" style="margin-top:10px;font-weight:600"></div>'
        "<script>function cc(){const a=+c_acct.value,r=+c_risk.value/100,e=+c_in.value,s=+c_st.value;"
        "const rp=Math.abs(e-s);if(!a||!r||!rp){c_out.innerText='—';return}"
        "const sh=Math.floor(a*r/rp);c_out.innerHTML=`${sh.toLocaleString()} shares · $${(sh*e).toLocaleString(undefined,{maximumFractionDigits:0})} position · $${Math.round(a*r).toLocaleString()} at risk (1R = ${rp.toFixed(2)})`;}"
        "document.querySelectorAll('.calc').forEach(i=>i.addEventListener('input',cc));cc();</script>") + card(
        '<div class="slabel">R-MULTIPLE EXPECTANCY</div>'
        '<label class="cl">Win rate %<br><input class="calc" id="e_wr" value="45"></label>'
        '<label class="cl">Avg win (R)<br><input class="calc" id="e_w" value="2"></label>'
        '<label class="cl">Avg loss (R)<br><input class="calc" id="e_l" value="1"></label>'
        '<div id="e_out" style="margin-top:10px;font-weight:600"></div>'
        "<script>function ec(){const w=+e_wr.value/100,aw=+e_w.value,al=+e_l.value;"
        "const ex=w*aw-(1-w)*al;e_out.innerHTML=`Expectancy: <span style='color:${ex>0?'#4caf7d':'#e05555'}'>${ex.toFixed(2)}R per trade</span> · 100 trades ≈ ${(ex*100).toFixed(0)}R`;}"
        "['e_wr','e_w','e_l'].forEach(i=>document.getElementById(i).addEventListener('input',ec));ec();</script>") + card(
        '<div class="slabel">COMPOUNDING</div>'
        '<label class="cl">Start $<br><input class="calc" id="k_p" value="100000"></label>'
        '<label class="cl">Return %/yr<br><input class="calc" id="k_r" value="15"></label>'
        '<label class="cl">Years<br><input class="calc" id="k_y" value="10"></label>'
        '<div id="k_out" style="margin-top:10px;font-weight:600"></div>'
        "<script>function kc(){const p=+k_p.value,r=+k_r.value/100,y=+k_y.value;"
        "k_out.innerText=`$${(p*Math.pow(1+r,y)).toLocaleString(undefined,{maximumFractionDigits:0})}`;}"
        "['k_p','k_r','k_y'].forEach(i=>document.getElementById(i).addEventListener('input',kc));kc();</script>")
    return dict(slug="calculators", title="Calculators",
                sub="Position sizing, expectancy, and compounding — the arithmetic that decides survival.",
                body=body, stance="info", headline="Position size · expectancy · compounding")

def m_glossary():
    terms = [
        ("A/D line", "Cumulative advancers minus decliners. The breadth backbone: index highs without A/D highs are suspect."),
        ("Breadth thrust", "A violent expansion in participation off a low (e.g. Zweig ≥ 0.615 within days of ≤ 0.40) — historically one of the most reliable bull signals."),
        ("COT report", "Weekly CFTC breakdown of futures positioning by trader type. Speculator extremes are contrarian."),
        ("Drawdown", "Percent decline from the running high. The risk number that matters more than volatility."),
        ("Expectancy", "Average R won or lost per trade: win% × avg win − loss% × avg loss. Positive expectancy plus sizing discipline is the whole game."),
        ("McClellan oscillator", "EMA19 − EMA39 of ratio-adjusted net advances — breadth momentum. Extremes and thrusts, not the day-to-day wiggle, carry the signal."),
        ("Net liquidity", "Fed balance sheet minus reverse repo minus Treasury account — the system's spendable dollars. Risk assets track its direction."),
        ("NFCI", "Chicago Fed's weekly composite of financial conditions. Negative = looser than average."),
        ("R (risk unit)", "Your per-trade risk (entry to stop). Denominating results in R makes any two trades comparable."),
        ("Relative strength", "An asset's return versus a benchmark. Persistent — leaders tend to keep leading over 3–12 months."),
        ("Sahm rule", "Recession trigger: 3-month average unemployment rising 0.50pt off its 12-month low. Simple, and it has called every post-war US recession."),
        ("Term structure (vol)", "VIX3M vs VIX. Ratio above ~1.05 = normal contango; below 1.0 = stress backwardation."),
        ("Yield-curve inversion", "Short rates above long rates (10y−3m below zero). The warning fires on inversion; trouble usually lands after the re-steepening."),
        ("Zweig breadth thrust", "10-day EMA of advances/(advances+declines). Armed under 0.40, fires at ≥ 0.615 within 10 sessions."),
    ]
    body = card("".join(f'<div style="padding:8px 0;border-bottom:1px solid var(--line)">'
                        f'<b style="color:{GOLD}">{t}</b><div class="muted" style="margin-top:2px">{d}</div></div>'
                        for t, d in terms))
    return dict(slug="glossary", title="Glossary",
                sub="The terms used across this terminal, in plain language.",
                body=body, stance="info", headline=f"{len(terms)} terms")

# ---------------------------------------------------------------- confluence + overview
def build_confluence(mods):
    scored = [m for m in mods if m["stance"] in ("bullish", "bearish", "neutral")]
    score = sum(1 if m["stance"] == "bullish" else -1 if m["stance"] == "bearish" else 0 for m in scored)
    n = len(scored)
    if score >= n * 0.35: verdict, vc = "Risk-on alignment", GREEN
    elif score <= -n * 0.35: verdict, vc = "Risk-off alignment", RED
    else: verdict, vc = "Mixed signals", AMBER
    rows = [(f'<a href="/terminal/{m["slug"]}/"><b>{m["title"]}</b></a>',
             f'<span class="pill" style="background:{STANCE_COL[m["stance"]]}22;color:{STANCE_COL[m["stance"]]}">{m["stance"]}</span>',
             m["headline"]) for m in mods if m["stance"] != "info"]
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{vc}">{verdict}</div>'
        f'<div class="muted" style="margin-top:3px">{sum(m["stance"]=="bullish" for m in scored)} bullish · '
        f'{sum(m["stance"]=="bearish" for m in scored)} bearish · '
        f'{sum(m["stance"]=="neutral" for m in scored)} neutral, across {n} scored modules</div>',
        "SIGNAL CONFLUENCE") + card(table(["Module", "Stance", "Current read"], rows)) + card(
        "Confluence is the whole point of a terminal: any single indicator is noisy, but when trend, breadth, "
        "credit, liquidity, and the macro clock agree, the signal quality compounds. The table above is a "
        "simple equal-weight tally — read disagreements as information too (e.g. breadth bullish while credit "
        "deteriorates = late-stage rally profile).", "WHY CONFLUENCE")
    return dict(slug="confluence", title="Confluence",
                sub="All module signals in one place — alignment is the edge, disagreement is the warning.",
                body=body, stance="info", headline=verdict)

def build_overview(mods, confl):
    cards = []
    for m in [confl] + mods:
        c = STANCE_COL[m["stance"]]
        cards.append(f'<a href="/terminal/{m["slug"]}/" class="card"><div class="slabel">{m["title"].upper()}</div>'
                     f'<div style="margin-top:4px;font-size:13px">{m["headline"]}</div>'
                     f'<div style="margin-top:6px"><span class="pill" style="background:{c}22;color:{c}">'
                     f'{m["stance"] if m["stance"] != "info" else "reference"}</span></div></a>')
    body = f'<div class="ovgrid">{"".join(cards)}</div>'
    return dict(slug="", title="Terminal Overview",
                sub="Every module's current read at a glance — click through for the full analysis.",
                body=body)

# ---------------------------------------------------------------- main
def main():
    px, gspc_m, gspc_d = load_data()
    builders = [
        lambda: m_breadth(px), lambda: m_key_levels(px), lambda: m_valuation(px, gspc_m),
        lambda: m_relative_strength(px), lambda: m_volatility(px), lambda: m_correlation(px),
        lambda: m_momentum(px), lambda: m_cot(), lambda: m_seasonality(gspc_m),
        lambda: m_sentiment(px), lambda: m_crypto(px), lambda: m_calendar(gspc_d),
        lambda: m_fed_path(px), lambda: m_business_cycle(), lambda: m_yield_curve(),
        lambda: m_credit(), lambda: m_liquidity(), lambda: m_finconditions(),
        lambda: m_election(gspc_m), lambda: m_astrology(), lambda: m_screener(px),
        lambda: m_calculators(), lambda: m_glossary(),
    ]
    mods, failed = [], []
    for b in builders:
        try:
            mods.append(b())
        except Exception as e:
            import traceback
            name = traceback.extract_tb(e.__traceback__)[-1].name
            failed.append(f"{name}: {e}")
    slug_order = [s for _, items in GROUPS for s, _ in items]
    mods.sort(key=lambda m: slug_order.index(m["slug"]) if m["slug"] in slug_order else 99)
    confl = build_confluence(mods)
    ov = build_overview(mods, confl)
    for m in mods + [confl]:
        write_page(m["slug"], m["title"], m["sub"], m["body"])
    write_page("", ov["title"], ov["sub"], ov["body"])
    print(f"built {len(mods)+2} pages -> {ROOT}")
    if failed:
        print("FAILED modules:")
        for f in failed:
            print("  -", f)

if __name__ == "__main__":
    main()
