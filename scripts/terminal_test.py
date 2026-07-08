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
GREEN, RED, AMBER, GOLD, BLUE, MUT = "#4caf7d", "#e05555", "#e0a94c", "#d4af37", "#5aa2d4", "#606060"
GOLD_DIM, TXT, STRONG = "#8b7020", "#a0a0a0", "#ffffff"
MINUS = "\u2212"  # U+2212 true minus, never a hyphen (finance typography)

def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def mn(txt): return str(txt).replace("-", MINUS)   # hyphen -> true minus, display only
def pct(v, d=1): return mn(f"{v:.{d}f}%")
def sgn(v, d=1): return ("+" if v >= 0 else MINUS) + f"{abs(v):.{d}f}%"
def col(v, good, bad=None):
    bad = bad if bad else (lambda x: not good(x))
    return GREEN if good(v) else (RED if bad(v) else AMBER)
def cnum(v, d=1):
    return f'<b style="color:{GREEN if v > 0 else RED}">{sgn(v, d)}</b>'
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

FONT_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
             '&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">')

CSS = """
:root { --background:#0b0b0b; --surface:#141414; --surface-raised:#1c1c1c; --border:#2a2a2a;
        --text-primary:#ffffff; --text-secondary:#a0a0a0; --text-muted:#606060;
        --gold:#d4af37; --gold-dim:#8b7020; --positive:#4caf7d; --negative:#e05555;
        --neutral:#a0a0a0;
        --font-sans:'Inter',system-ui,-apple-system,sans-serif;
        --font-mono:'JetBrains Mono',ui-monospace,'SF Mono',monospace;
        /* legacy aliases used inline */
        --bg:var(--background); --card:var(--surface); --line:var(--border);
        --tx:var(--text-secondary); --muted:var(--text-muted);
        --green:var(--positive); --red:var(--negative); }
* { box-sizing:border-box; margin:0; }
body { background:var(--background); color:var(--text-secondary);
       font:14px/1.6 var(--font-sans); -webkit-font-smoothing:antialiased; }
a { color:inherit; text-decoration:none; }
b, strong { color:var(--text-primary); font-weight:600; }
.layout { display:flex; min-height:100vh; }
nav { width:216px; flex:none; border-right:1px solid var(--border); padding:22px 0 40px; }
nav .brand { padding:0 16px 16px; font-weight:700; color:var(--text-primary); letter-spacing:-.02em; font-size:15px; }
nav .brand small { display:block; color:var(--text-muted); font-weight:400; font-size:9.5px;
                   letter-spacing:.18em; text-transform:uppercase; margin-top:3px; }
nav .g { padding:16px 16px 5px; font-size:9.5px; text-transform:uppercase; letter-spacing:.4em;
         color:var(--text-muted); font-weight:500; }
nav a { display:block; padding:5px 16px; font-size:13px; color:var(--text-secondary);
        border-left:2px solid transparent; transition:color .12s; }
nav a:hover { color:var(--text-primary); }
nav a.on { color:var(--gold); border-left-color:var(--gold); background:rgba(212,175,55,.06); }
main { flex:1; min-width:0; padding:28px 28px 72px; max-width:980px; }
h1 { font-size:2.25rem; color:var(--text-primary); font-weight:700; letter-spacing:-.035em; line-height:1.15; }
h1 .tag { font-size:12px; color:var(--text-muted); font-weight:400; letter-spacing:0; }
h2 { font-size:10.5px; margin:32px 0 4px; color:var(--text-muted); text-transform:uppercase;
     letter-spacing:.22em; font-weight:600; }
.sub { color:var(--text-secondary); font-size:13px; margin:8px 0 6px; max-width:70ch; }
.stamp { display:inline-flex; align-items:center; gap:8px; margin:12px 0 4px; padding:5px 12px;
         border:1px solid var(--border); border-radius:9999px; background:var(--surface);
         font-family:var(--font-mono); font-size:10.5px; color:var(--text-muted); letter-spacing:.02em; }
.stamp .dot { width:6px; height:6px; border-radius:9999px; background:var(--positive);
              box-shadow:0 0 6px var(--positive); }
.card { background:var(--surface); border:1px solid var(--border); border-radius:8px;
        padding:16px 18px; margin-top:10px; }
.card:hover { background:var(--surface-raised); }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:14px; margin-top:12px; }
.slabel { font-size:9.5px; color:var(--text-muted); text-transform:uppercase;
          letter-spacing:.16em; font-weight:500; }
.sval { font-size:1.5rem; font-weight:600; color:var(--text-primary);
        font-family:var(--font-mono); font-variant-numeric:tabular-nums; letter-spacing:-.02em; }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
th,td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--border); font-size:12.5px; }
td { font-family:var(--font-mono); color:var(--text-secondary); }
td b, td strong { font-family:var(--font-sans); }
th { color:var(--text-muted); font-weight:500; font-size:9.5px; text-transform:uppercase;
     letter-spacing:.14em; font-family:var(--font-sans); }
.muted { color:var(--text-muted); }
ul.pb { margin:8px 0 0 0; padding:0; list-style:none; }
ul.pb li { margin:7px 0; padding-left:18px; position:relative; }
ul.pb li:before { content:"\\25B8"; position:absolute; left:0; color:var(--gold); }
.legend { font-size:11px; color:var(--text-muted); margin-top:8px; line-height:1.55; }
.pill { display:inline-block; padding:2px 10px; border-radius:9999px; font-size:10.5px;
        font-weight:600; letter-spacing:.04em; text-transform:uppercase; }
.ovgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; }
.ovgrid .card { margin:0; } .ovgrid .card:hover { border-color:var(--gold); }
.foot { margin-top:48px; font-size:10.5px; color:var(--text-muted); border-top:1px solid var(--border);
        padding-top:16px; line-height:1.6; }
input.calc, select { background:var(--background); border:1px solid var(--border); border-radius:4px;
             color:var(--text-primary); padding:7px 9px; width:110px; font-size:13px;
             font-family:var(--font-mono); }
input.calc:focus, select:focus { outline:none; border-color:var(--gold-dim); }
label.cl { display:inline-block; font-size:9.5px; color:var(--text-muted); margin:6px 14px 2px 0;
           text-transform:uppercase; letter-spacing:.14em; }
button { font-family:var(--font-sans); }
@media (max-width:760px){ .layout{display:block} nav{width:auto;border-right:0;border-bottom:1px solid var(--border);
  white-space:nowrap;overflow-x:auto;display:flex;align-items:center;padding:10px}
  nav .brand{padding:0 12px} nav .g{display:none} nav a{display:inline-block;border-left:0;padding:5px 9px}
  main{padding:20px 16px 60px} h1{font-size:1.875rem} }
"""

def nav_html(active):
    out = ['<div class="brand">TraderGK <small>research terminal</small></div>']
    for gname, items in GROUPS:
        out.append(f'<div class="g">{gname}</div>')
        for slug, name in items:
            on = ' class="on"' if slug == active else ""
            out.append(f'<a href="/terminal/{slug + "/" if slug else ""}"{on}>{name}</a>')
    return "".join(out)

def true_minus(html):
    """Hyphen -> U+2212 in visible text nodes only.

    Skips <script>/<style> bodies and every tag's attributes, so SVG point lists,
    ISO dates (preceded by a digit) and words like 'risk-off' are left alone.
    """
    import re as _re
    stash = []
    def _hide(m):
        stash.append(m.group(0))
        return f"\x00{len(stash)-1}\x00"
    html = _re.sub(r"<(script|style)\b.*?</\1>", _hide, html, flags=_re.S | _re.I)
    def _fix(m):
        return ">" + _re.sub(r"(?<!\w)-(?=[\d.])", MINUS, m.group(1)) + "<"
    html = _re.sub(r">([^<]*)<", _fix, html)
    return _re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], html)

def write_page(slug, title, subtitle, body, sources="Yahoo Finance · FRED · CFTC"):
    path = os.path.join(ROOT, slug, "index.html") if slug else os.path.join(ROOT, "index.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = true_minus(body)
    crumb = ('<div class="muted" style="font-size:11px;letter-spacing:.06em">TraderGK '
             f'<span style="color:var(--gold)">›</span> {title}</div>') if slug else ""
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{title} — TraderGK terminal</title>{FONT_LINK}<style>{CSS}</style></head>
<body><div class="layout"><nav>{nav_html(slug)}</nav><main>
{crumb}
<h1>{title} <span class="tag">· private</span></h1>
<div class="sub">{subtitle}</div>
<div class="stamp"><span class="dot"></span>LIVE DATA · {STAMP.upper()} · {sources.upper()} · HOURLY REBUILD</div>
{body}
<div class="foot">TraderGK research · private page — reachable by direct link only · education only, not financial advice.
Data may be delayed or approximate; nothing here is a recommendation.</div>
</main></div>
<script>
// Interactive tables re-render on click, so sweep text nodes for hyphen-minus each time.
(function(){{
  var RE = /(^|[^A-Za-z0-9])-(?=[0-9.])/g;
  function sweep(root){{
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var n;
    while ((n = w.nextNode())) {{
      var p = n.parentNode && n.parentNode.nodeName;
      if (p === 'SCRIPT' || p === 'STYLE') continue;
      if (n.nodeValue.indexOf('-') < 0) continue;
      var r = n.nodeValue.replace(RE, '$1\\u2212');
      if (r !== n.nodeValue) n.nodeValue = r;
    }}
  }}
  sweep(document.body);
  document.addEventListener('click', function(){{ setTimeout(function(){{ sweep(document.body); }}, 0); }}, true);
  document.addEventListener('input', function(){{ setTimeout(function(){{ sweep(document.body); }}, 0); }}, true);
}})();
</script>
</body></html>"""
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
        now_tag = ' <span class="pill" style="background:rgba(212,175,90,.15);color:#d4af37">now</span>' if i == cur_b else ""
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
const D=__DATA__,GRN='#4caf7d',RED='#e05555',GOLDC='#d4af37',BLU='#5aa2d4',MUT='#606060';
const QC={LEADING:GRN,WEAKENING:GOLDC,LAGGING:RED,IMPROVING:BLU};
let uni=Object.keys(D)[0];
const wrap=document.getElementById('rrgw');
function render(){
 const u=D[uni];
 let h='<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">'+Object.keys(D).map(k=>
  '<button data-u="'+k+'" style="cursor:pointer;font-size:11px;padding:3px 12px;border-radius:14px;border:1px solid '+
  (k===uni?GOLDC:'#2a2a2a')+';background:'+(k===uni?'rgba(212,175,90,.12)':'transparent')+';color:'+(k===uni?GOLDC:MUT)+'">'+D[k].name+'</button>').join('')+'</div>';
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
        f'border-radius:16px;border:1px solid #2a2a2a;background:transparent;color:#606060;margin:0 6px 8px 0">{t.replace("-USD","")}</button>'
        for t in KL_TICKERS)
    divs = "".join(f'<div id="kl-{t}" style="display:none">{body}</div>' for t, body in sections.items())
    js = ("<script>function klshow(t){%s.forEach(x=>{document.getElementById('kl-'+x).style.display=x===t?'block':'none';"
          "const b=document.getElementById('klb-'+x);b.style.color=x===t?'#d4af37':'#606060';"
          "b.style.borderColor=x===t?'#d4af37':'#2a2a2a';});}klshow('SPY');</script>"
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

def _multpl(page, fallback=None, lo=3.0, hi=100.0):
    """Scrape a single ratio from multpl.com.

    The page reads 'Current S&P 500 PE Ratio is 32.28' — a naive "first number
    after Current" grabs the 500 out of 'S&P 500'. Anchor on the literal
    ' is <number>' instead, then bounds-check: a P/E of 500 silently wrecks
    every earnings-based fair-value model downstream.
    """
    try:
        req = urllib.request.Request(f"https://www.multpl.com/{page}",
                                     headers={"User-Agent": "Mozilla/5.0"})
        import re as _re
        html = urllib.request.urlopen(req, timeout=20).read().decode()
        m = _re.search(r"Current\s+[^<>\"]{0,70}?\bis\s+(\d+\.?\d*)", html)
        if not m:
            return fallback
        v = float(m.group(1))
        return v if lo <= v <= hi else fallback
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
const D=__DATA__,GRN='#4caf7d',RED='#e05555',GOLDC='#d4af37',MUT='#606060';
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
   (k===asset?GOLDC:'#2a2a2a')+';background:'+(k===asset?'rgba(212,175,90,.12)':'transparent')+';color:'+(k===asset?GOLDC:MUT)+'">'+
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
   '<button data-m="'+m.name+'" style="cursor:pointer;min-width:34px;height:18px;border-radius:9px;border:0;background:'+(on?GRN:'#2a2a2a')+'"></button>'+
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
        f'<div style="flex:1;background:#2a2a2a;border-radius:3px;height:8px">'
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
const R=__ROWS__,PLAYS=__PLAYS__,GRN='#4caf7d',RED='#e05555',GOLDC='#d4af37',MUT='#606060';
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
   (k===cat?GOLDC:'#2a2a2a')+';background:'+(k===cat?'rgba(212,175,90,.12)':'transparent')+';color:'+(k===cat?GOLDC:MUT)+'">'+l+'</button>').join('')+'</div>';
 h+='<div style="overflow-x:auto"><table><tr><th>Asset (ranked)</th><th>Score</th><th>Today</th><th>1W</th><th>1M</th><th>3M</th><th>RSI</th><th>TF align</th><th>52w</th><th>Flags</th><th>Regime</th></tr>';
 rows.forEach((r,i)=>{
  const rc=r.regime==='Trending up'?GRN:(r.regime==='Trending down'?RED:(r.regime==='Chop'?MUT:GOLDC));
  h+='<tr data-i="'+i+'" style="cursor:pointer"><td style="white-space:nowrap"><b>'+r.n+'</b> <span class="muted" style="font-size:10px">'+r.cat+'</span></td>'+
   '<td><b style="color:'+(r.score>=65?GRN:(r.score<=35?RED:'#ffffff'))+'">'+r.score+'</b></td>'+
   '<td>'+pc(r.t,2)+'</td><td>'+pc(r.w)+'</td><td>'+pc(r.m)+'</td><td>'+pc(r.q)+'</td>'+
   '<td style="color:'+(r.rsi>70?RED:(r.rsi<30?GRN:'#ffffff'))+'">'+r.rsi.toFixed(1)+'</td>'+
   '<td style="letter-spacing:1px">'+blocks(r)+'</td>'+
   '<td><div style="width:56px;background:#2a2a2a;height:6px;border-radius:3px"><div style="width:'+(r.p52*100).toFixed(0)+'%;background:'+GOLDC+';height:6px;border-radius:3px"></div></div></td>'+
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
const GRN='#4caf7d',RED='#e05555',GOLDC='#d4af37',BLU='#5aa2d4',MUT='#606060';
let inst='ES',view='overlay';
const wrap=document.getElementById('seas'),tip=document.getElementById('stip');
function tabs(id,items,cur,fn){return '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 10px">'+items.map(([k,l])=>
 '<button data-'+id+'="'+k+'" style="cursor:pointer;font-size:12px;padding:4px 12px;border-radius:16px;border:1px solid '+
 (k===cur?GOLDC:'#2a2a2a')+';background:'+(k===cur?'rgba(212,175,90,.12)':'transparent')+';color:'+
 (k===cur?GOLDC:'#606060')+'">'+l+'</button>').join('')+'</div>';}
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
 let g='<rect x="'+P+'" y="'+P+'" width="'+(W-2*P)+'" height="'+(H-2*P)+'" fill="none" stroke="#2a2a2a"/>';
 if(lo<0&&hi>0)g+='<line x1="'+P+'" x2="'+(W-P)+'" y1="'+Y(0)+'" y2="'+Y(0)+'" stroke="'+MUT+'" stroke-width="0.6" stroke-dasharray="3 4"/>';
 for(let m=0;m<12;m++){const x=X(m*30.4+1);g+='<text x="'+x+'" y="'+(H-14)+'" fill="'+MUT+'" font-size="10">'+MN[m]+'</text>';}
 [lo,lo+rg/2,hi].forEach(v=>{g+='<text x="4" y="'+(Y(v)+3)+'" fill="'+MUT+'" font-size="10">'+v.toFixed(0)+'%</text>';});
 const doy=Math.min(366,Math.floor((Date.now()-Date.UTC(new Date().getUTCFullYear(),0,0))/864e5));
 g+='<line x1="'+X(doy)+'" x2="'+X(doy)+'" y1="'+P+'" y2="'+(H-P)+'" stroke="'+GOLDC+'" stroke-width="0.6" stroke-dasharray="4 4"/>';
 S.forEach(([n,a,c])=>{let pts=[];for(let i=1;i<367;i++)if(a[i]!=null)pts.push(X(i).toFixed(1)+','+Y(a[i]).toFixed(1));
  g+='<polyline points="'+pts.join(' ')+'" fill="none" stroke="'+c+'" stroke-width="'+(n==='YTD'?2.2:1.4)+'"/>';});
 el.innerHTML='<svg id="ssvg" viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto">'+g+
  '<line id="cx" y1="'+P+'" y2="'+(H-P)+'" stroke="#ffffff" stroke-width="0.5" visibility="hidden"/></svg>'+
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
 let sel='<select id="msel" style="background:#0b0b0b;color:#ffffff;border:1px solid #2a2a2a;border-radius:6px;padding:4px 8px;font-size:12px;margin-bottom:8px">'+
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
 for(let t=1;t<=23;t++)h+='<th style="padding:3px 4px;color:#606060">'+t+'</th>';h+='</tr>';
 d.grid.forEach((row,m)=>{h+='<tr><td style="padding:3px 6px;color:#606060;font-weight:600">'+MN[m]+'</td>';
  row.forEach((v,t)=>{if(v==null){h+='<td></td>';return}
   const a=Math.min(0.9,Math.abs(v)/mx),c=v>=0?'76,175,125':'224,85,85';
   h+='<td title="'+MN[m]+' · trading day '+(t+1)+': '+(v>=0?'+':'')+v.toFixed(3)+'%" style="padding:3px 4px;background:rgba('+c+','+a.toFixed(2)+');border:1px solid #0b0b0b;text-align:center;min-width:22px">'+(Math.abs(v)>=0.05?(v>0?'+':'−'):'')+'</td>';});
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
                '<div id="stip" style="display:none;position:fixed;z-index:9;background:#141414;'
                'border:1px solid #2a2a2a;border-radius:8px;padding:8px 11px;font-size:12px;'
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

CAL_ASSETS = [("^GSPC", "S&P 500"), ("^NDX", "NASDAQ 100"), ("^RUT", "Russell 2000"),
              ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("GC=F", "Gold"),
              ("TLT", "Long bonds"), ("DX-Y.NYB", "US Dollar")]

def _cal_asset(name, s):
    r = s.pct_change().dropna() * 100
    r = r[r.index >= r.index[-1] - pd.Timedelta(days=3700)]
    crypto = len(set(r.index.dayofweek)) > 5
    # day of week
    dlab = ["Mon", "Tue", "Wed", "Thu", "Fri"] + (["Sat", "Sun"] if crypto else [])
    dow_avg = [float(r[r.index.dayofweek == i].mean()) for i in range(len(dlab))]
    dow_win = [float((r[r.index.dayofweek == i] > 0).mean() * 100) for i in range(len(dlab))]
    # trading day of month
    tdi = r.groupby([r.index.year, r.index.month]).cumcount() + 1
    td_avg = [float(r[tdi == d].mean()) if (tdi == d).sum() >= 5 else 0 for d in range(1, 24)]
    # monthly grid
    mr = s.resample("ME").last().pct_change().dropna() * 100
    cur_m = s[s.index >= s.index[-1].replace(day=1)]
    mtd = float((cur_m.iloc[-1] / cur_m.iloc[0] - 1) * 100) if len(cur_m) > 1 else None
    years = sorted(set(mr.index.year), reverse=True)[:11]
    grid = {}
    for y in years:
        grid[y] = {m: None for m in range(1, 13)}
        for i, v in mr[mr.index.year == y].items():
            grid[y][i.month] = float(v)
    if mtd is not None:
        grid.setdefault(NOW.year, {m: None for m in range(1, 13)})[NOW.month] = mtd
    full = mr[~((mr.index.year == NOW.year) & (mr.index.month == NOW.month))]
    win = {m: float((full[full.index.month == m] > 0).mean() * 100) for m in range(1, 13)}
    # windows
    idx = r.index
    months_s = pd.Series(idx.month, index=idx)
    starts = months_s.ne(months_s.shift(1))
    tom = pd.Series(False, index=idx)
    for i in range(len(idx)):
        if starts.iloc[i]:
            for j in range(max(0, i - 2), min(len(idx), i + 3)):
                tom.iloc[j] = True
    third_fri = idx.to_series().apply(
        lambda d: d.weekday() <= 4 and 15 <= d.day - (d.weekday() - 4) % 7 <= 21 and
        abs((d.day - 1) // 7 - 2) <= 0 if False else False)
    # OPEX week = the Mon-Fri containing the 3rd Friday
    def is_opex(d):
        fri = d + pd.Timedelta(days=(4 - d.weekday()) % 7)
        return fri.month == d.month and 15 <= fri.day <= 21
    opex = idx.to_series().apply(is_opex)
    lull = (tdi >= 10) & (tdi <= 15)
    def window_stats(mask):
        grp = r[mask.values if hasattr(mask, "values") else mask]
        # per-instance: sum returns per (year, month)
        inst = grp.groupby([grp.index.year, grp.index.month]).sum()
        return float(inst.mean()), float((inst > 0).mean() * 100), len(inst)
    win_rows = [("Turn of month", "Last 2 + first 3 sessions — the documented institutional-flow bid",
                 *window_stats(tom), bool(tom.iloc[-1])),
                ("OPEX week", "The week of the 3rd Friday — expiry pinning and hedge flows",
                 *window_stats(opex), bool(opex.iloc[-1])),
                ("Mid-month lull", "Trading days 10–15 — historically the flattest stretch",
                 *window_stats(lull), bool(lull.iloc[-1]))]
    # today's edge
    dw = NOW.weekday() if NOW.weekday() < len(dlab) else 0
    td_now = int(tdi.iloc[-1])
    active = [w for w in win_rows if w[5]]
    edge = (f"For {name}: {dlab[dw]}s average {dow_avg[dw]:+.3f}% ({dow_win[dw]:.0f}% up); "
            f"trading day {td_now} averages {td_avg[min(td_now, 23) - 1]:+.3f}%")
    if active:
        w = active[0]
        edge += f"; currently inside the {w[0]} window (avg {w[2]:+.2f}%/instance, {w[3]:.0f}% positive)"
    edge += ". A historical tendency, not a promise — size accordingly."
    # html
    hh = card(edge, f"TODAY'S EDGE · {name.upper()} ({(r.index[-1] - r.index[0]).days // 365}Y OF DATA)")
    hh += card(bar_chart(dlab, dow_avg) +
               '<div class="legend">Average return by day of week' +
               (" (crypto trades all seven)" if crypto else "") + ".</div>", "DAY OF WEEK")
    hh += card(bar_chart([str(d) if d % 2 else "" for d in range(1, 24)], td_avg) +
               '<div class="legend">Average return by trading day of the month — where in the month the '
               'asset historically finds its bid.</div>', "TRADING DAY OF MONTH")
    mn = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    trs = "<tr><th>Year</th>" + "".join(
        f'<th style="{"color:#d4af37" if m == NOW.month else ""}">{mn[m-1]}</th>' for m in range(1, 13)) + "</tr>"
    trs += "<tr><td class='muted'>Win rate</td>" + "".join(
        f'<td style="color:{GREEN if win[m] >= 60 else (RED if win[m] < 45 else "var(--tx)")}">{win[m]:.0f}%</td>'
        for m in range(1, 13)) + "</tr>"
    for y in sorted(grid, reverse=True):
        trs += f"<tr><td><b>{y}</b></td>" + "".join(
            (f'<td style="color:{GREEN if grid[y][m] > 0 else RED}">{grid[y][m]:+.1f}</td>'
             if grid[y].get(m) is not None else '<td class="muted">–</td>') for m in range(1, 13)) + "</tr>"
    hh += card(f'<div style="overflow-x:auto"><table style="font-size:11px">{trs}</table></div>'
               '<div class="legend">Monthly returns, %. Win rate excludes the current partial month; the '
               'year rows include it as month-to-date. Current month highlighted.</div>',
               "MONTHLY GRID · 11 YEARS")
    hh += card(table(["Window", "Avg / instance", "% positive", "n", "Status"],
                     [(f"<b>{w[0]}</b><div class='muted' style='font-size:11px'>{w[1]}</div>",
                       cnum(w[2], 2), f"{w[3]:.0f}%", str(w[4]),
                       f'<span style="color:{GOLD}">active now</span>' if w[5] else "—")
                      for w in win_rows]), "THE DOCUMENTED WINDOWS")
    return hh

def m_calendar(gspc_d):
    hist = yf.download([s for s, _ in CAL_ASSETS], period="10y", interval="1d",
                       auto_adjust=True, progress=False)["Close"]
    sections = {}
    for sym, name in CAL_ASSETS:
        try:
            sections[sym] = _cal_asset(name, hist[sym].dropna())
        except Exception as e:
            sections[sym] = card(f'<span class="muted">Unavailable this run ({e}).</span>')
    tabs = "".join(
        f'<button onclick="calshow(\'{s}\')" id="calb-{s}" style="cursor:pointer;font-size:12px;padding:4px 12px;'
        f'border-radius:16px;border:1px solid #2a2a2a;background:transparent;color:#606060;margin:0 6px 8px 0">{n}</button>'
        for s, n in CAL_ASSETS)
    divs = "".join(f'<div id="cal-{s}" style="display:none">{b}</div>' for s, b in sections.items())
    js = ("<script>function calshow(t){%s.forEach(x=>{document.getElementById('cal-'+x).style.display=x===t?'block':'none';"
          "const b=document.getElementById('calb-'+x);b.style.color=x===t?'#d4af37':'#606060';"
          "b.style.borderColor=x===t?'#d4af37':'#2a2a2a';});}calshow('^GSPC');</script>"
          ) % json.dumps([s for s, _ in CAL_ASSETS])
    body = f"<div>{tabs}</div>{divs}{js}" + card(
        "The Seasonality tab answers \"which months favor this asset\"; this one answers the day-trader's "
        "version: which DAYS. Markets carry documented micro-rhythms — the turn-of-month institutional bid, "
        "the mid-month lull, expiry-week pinning, persistent weekday tilts (crypto trades all seven days). "
        "Each is measured from ~10 years of daily bars per asset, with sample sizes shown. These edges are "
        "small per instance but persistent across hundreds of observations: they're tie-breakers for WHEN "
        "to execute a decision already made, never the reason for the decision.", "THE 60-SECOND VERSION")
    return dict(slug="calendar", title="Calendar Effects",
                sub="Day-of-week, day-of-month and named-window rhythms, measured per asset over ~10 years.",
                body=body, stance="info",
                headline="Turn-of-month, OPEX week and weekday tilts across 8 assets")

CYCLE_NAMES = {1: "Post-election", 2: "Midterm", 3: "Pre-election", 0: "Election"}
CYCLE_NOTES = {
    "Post-election": ("The hangover year — new administrations spend their political capital on the painful "
                      "things early, so the market absorbs the bad news while expectations reset.",
                      ["Expect policy noise; let it pass rather than trading each headline",
                       "Positioning matters more than the calendar in year one",
                       "The cycle's tailwind builds from here, not immediately"],
                      "Treating early-term volatility as a regime change. It usually isn't."),
    "Midterm": ("The weakest average year of the cycle and the deepest average drawdown — and, because of "
                "exactly that, the entry window the cycle is famous for.",
                ["Budget for chop: expect an outsized intra-year drawdown, historically bottoming in the "
                 "August–October window",
                 "Build the shopping list now — the 12 months after midterm-year lows have been the cycle's "
                 "strongest stretch",
                 "The Q4-midterm through Q2-pre-election run is the window worth being fully invested for"],
                "Don't front-run the low with full size. The pattern pays those who keep powder dry into "
                "autumn, not those who buy every spring dip."),
    "Pre-election": ("Historically the strongest year of the four by a wide margin — the mechanism is policy: "
                     "administrations stimulate into re-election.",
                     ["Trend-following gets paid; fading strength has been the losing trade",
                      "Stay invested through minor drawdowns — the cycle's wind is at your back",
                      "Begin trimming into the year's second half as the election year's uncertainty approaches"],
                     "Assuming the pattern is a law. Pre-election years have had losses; they are just rarer."),
    "Election": ("A middling year with a volatility hump into November, then relief once the outcome is known "
                 "regardless of who wins.",
                 ["Expect vol to build into the vote and collapse after it — that asymmetry is the trade",
                  "Sector dispersion widens on policy expectations; the index often goes nowhere",
                  "The post-election relief rally is the reliable part, not the pre-election positioning"],
                 "Trading your politics. The market's reaction to elections has consistently defied partisan "
                 "predictions."),
}

def m_election(gspc_m):
    gd = yf.download("^GSPC", period="max", interval="1d", auto_adjust=True,
                     progress=False)["Close"].squeeze().dropna()
    m = gspc_m.pct_change().dropna()
    m = m[m.index.year >= 1950]
    def cyc_of(y):  # 2026 % 4 == 2 -> midterm
        return y % 4
    yearly = m.groupby(m.index.year).apply(lambda g: ((1 + g).prod() - 1) * 100)
    cur_y = NOW.year
    cur_c = cyc_of(cur_y)
    cname = CYCLE_NAMES[cur_c]
    stats = {}
    for c in range(4):
        ys = [y for y in yearly.index if cyc_of(y) == c and y < cur_y]
        vals = [yearly[y] for y in ys]
        stats[c] = (sum(vals) / len(vals), sum(v > 0 for v in vals) / len(vals) * 100, len(vals))
    # intra-year drawdown per cycle year
    dds = {c: [] for c in range(4)}
    for y in sorted(set(gd.index.year)):
        if y < 1950 or y >= cur_y:
            continue
        yr = gd[gd.index.year == y]
        if len(yr) < 100:
            continue
        dds[cyc_of(y)].append(float((yr / yr.cummax() - 1).min() * 100))
    dd_avg = {c: (sum(v) / len(v) if v else 0) for c, v in dds.items()}
    # average shape of the current cycle-year vs this year
    paths = []
    for y in sorted(set(gd.index.year)):
        if y < 1990 or y >= cur_y or cyc_of(y) != cur_c:
            continue
        yr = gd[gd.index.year == y]
        if len(yr) < 200:
            continue
        norm = (yr / yr.iloc[0] * 100).values
        paths.append([float(norm[min(int(i * (len(norm) - 1) / 251), len(norm) - 1)]) for i in range(252)])
    avg_path = [sum(p[i] for p in paths) / len(paths) for i in range(252)] if paths else []
    this_yr = gd[gd.index.year == cur_y]
    this_path = (this_yr / this_yr.iloc[0] * 100).tolist() if len(this_yr) else []
    shape = ""
    if avg_path and this_path:
        shape = line_chart([avg_path, this_path], [GOLD, BLUE]) + (
            f'<div class="legend"><span style="color:{GOLD}">▬</span> average shape of a {cname.lower()} year '
            f'(n={len(paths)}, since 1990) · <span style="color:{BLUE}">▬</span> {cur_y} so far, both indexed '
            'to 100 on 1 January. The classic pattern for a midterm year: choppy first half, weakness into late '
            'summer, then the year-end recovery that launches the cycle\'s strongest stretch.</div>')
    # quarter x cycle-year table
    qm = gspc_m.pct_change().dropna()
    qm = qm[qm.index.year >= 1950]
    qrows = []
    for c in (1, 2, 3, 0):
        cells = []
        for q in range(1, 5):
            sel = qm[(qm.index.year % 4 == c) & (qm.index.quarter == q)]
            byq = sel.groupby([sel.index.year, sel.index.quarter]).apply(lambda g: ((1 + g).prod() - 1) * 100)
            cells.append(float(byq.mean()) if len(byq) else 0.0)
        tag = ' <span class="pill" style="background:rgba(212,175,90,.15);color:#d4af37;font-size:10px">now</span>' if c == cur_c else ""
        qrows.append((f"<b>{CYCLE_NAMES[c]}</b>{tag}", *[cnum(v, 1) for v in cells]))
    desc, actions, caution = CYCLE_NOTES[cname]
    avg, winr, n = stats[cur_c]
    elec_day = pd.Timestamp(f"{cur_y}-11-03") if cur_c in (0, 2) else None
    days_to = (elec_day - pd.Timestamp(NOW.date())).days if elec_day is not None and elec_day > pd.Timestamp(NOW.date()) else None
    yr_frac = (NOW.timetuple().tm_yday / 365 + {1: 0, 2: 1, 3: 2, 0: 3}[cur_c]) / 4 * 100
    yr_no = {1: 1, 2: 2, 3: 3, 0: 4}[cur_c]
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{GOLD}">Year {yr_no} · {cname}</div>' +
        stat_grid([("Through the term", f"{yr_frac:.0f}%", MUT),
                   ("This cycle-year average", sgn(avg), col(avg, lambda v: v > 5)),
                   ("Positive years", f"{winr:.0f}% (n={n})", col(winr, lambda v: v > 60)),
                   ("Avg intra-year drawdown", f"{dd_avg[cur_c]:.1f}%", RED)] +
                  ([("Days to the midterms", f"{days_to}d", GOLD)] if days_to else [])),
        "YOU ARE HERE")
    body += card(f'<div class="muted">{desc}</div>' +
                 "".join(f'<div style="font-size:13px;margin-top:5px">▸ {a}</div>' for a in actions) +
                 f'<div class="muted" style="margin-top:10px;font-size:12px"><b>Caution:</b> {caution}</div>',
                 f"PLAYBOOK · {cname.upper()} YEAR")
    body += "<h2>S&P 500 by cycle year</h2>" + card(
        bar_chart([CYCLE_NAMES[c] for c in (1, 2, 3, 0)], [stats[c][0] for c in (1, 2, 3, 0)],
                  highlight=[1, 2, 3, 0].index(cur_c)) +
        '<div class="legend">Average calendar-year S&P return by presidential-cycle year since 1950 · gold = '
        'current. Below each: the deepest average intra-year drawdown of that cycle year.</div>' +
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:6px">' +
        "".join(f'<div style="text-align:center"><div class="slabel">{CYCLE_NAMES[c]}</div>'
                f'<div style="font-size:12px">{stats[c][1]:.0f}% positive · avg DD '
                f'<span style="color:{RED}">{dd_avg[c]:.0f}%</span></div></div>' for c in (1, 2, 3, 0)) + "</div>")
    if shape:
        body += f"<h2>The average {cname.lower()} year vs {cur_y}</h2>" + card(shape)
    body += "<h2>Average return by quarter × cycle year</h2>" + card(
        table(["Cycle year", "Q1", "Q2", "Q3", "Q4"], qrows) +
        '<div class="legend">The Q4-midterm → Q2-pre-election stretch is visible here as the cycle\'s sweet '
        'spot. The mechanism is policy: fiscal and monetary support gets front-loaded into re-election years.</div>')
    body += card(
        "The four-year rhythm is real in the averages and unreliable in any single instance. Use it the way you "
        "use seasonality: to set expectations about the SHAPE of a year — where the drawdown usually lands, "
        "where the recovery usually starts — never as the reason for a trade. Sample sizes here are small "
        "(under 20 observations per cycle year since 1950), which is exactly why the drawdown column matters "
        "more than the average-return column.", "HONEST LIMITATIONS")
    stance = "bullish" if avg > 8 else ("neutral" if avg > 0 else "bearish")
    return dict(slug="election-cycle", title="Election Cycle",
                sub="The four-year policy rhythm — cycle-year returns, drawdowns, the year's average shape, and the quarterly map.",
                body=body, stance=stance,
                headline=f"{cname} year — averages {avg:+.1f}%, avg drawdown {dd_avg[cur_c]:.0f}%")

TENORS = [("DGS1MO", "1M", 1 / 12), ("DGS3MO", "3M", 0.25), ("DGS6MO", "6M", 0.5),
          ("DGS1", "1Y", 1), ("DGS2", "2Y", 2), ("DGS3", "3Y", 3), ("DGS5", "5Y", 5),
          ("DGS7", "7Y", 7), ("DGS10", "10Y", 10), ("DGS20", "20Y", 20), ("DGS30", "30Y", 30)]

RATE_SENS = [("SPY", "S&P 500"), ("QQQ", "NASDAQ 100"), ("IWM", "Small caps"),
             ("KRE", "Banks"), ("GLD", "Gold"), ("TLT", "Long bonds"), ("BTC-USD", "Bitcoin")]

CURVE_PLAYS = {
    "Bear flattener": (
        "Front-end yields rising faster than the long end — the market prices more tightening than the long "
        "end believes the economy can absorb.",
        ["The dollar", "Front-end carry (bills)", "Quality over beta"],
        ["Gold (real-rate headwind)", "Small caps and unprofitable growth", "Emerging markets"],
        "Persistent bear flattening is how curves invert — the late-cycle regime. Each hike priced brings the inversion trigger closer."),
    "Bull flattener": (
        "Long-end yields falling faster than the front — the classic growth-scare configuration; the long end "
        "is pricing a slowdown the Fed hasn't acknowledged.",
        ["Long duration Treasuries", "Defensives and staples", "Gold"],
        ["Banks (margin compression)", "Cyclicals", "Value over growth"],
        "Bull flattening into an inversion is the bond market disagreeing with the Fed. It usually wins."),
    "Bull steepener": (
        "Front-end yields falling faster than the long end — cuts are being priced, whether from easing "
        "inflation or a cracking economy. Which one decides everything.",
        ["Long duration growth", "Gold and Bitcoin", "Small caps (if cuts are pre-emptive)"],
        ["The dollar", "Cash (carry disappears)"],
        "The re-steepening out of inversion is the historical recession trigger window — check the Business Cycle tab before treating it as bullish."),
    "Bear steepener": (
        "Long-end yields rising faster than the front — the market prices growth, inflation, or a term premium "
        "for fiscal supply. The reflation configuration.",
        ["Banks and financials", "Cyclicals and value", "Commodities"],
        ["Long bonds", "Unprofitable growth", "Utilities and bond proxies"],
        "Bear steepening from an inverted curve is normalization; from an already-steep curve it can signal a supply or credibility problem."),
}

INVERSIONS = [("Aug 1978", "Jan 1980", "17 mo"), ("Dec 1988", "Jul 1990", "19 mo"),
              ("Feb 2000", "Mar 2001", "13 mo"), ("Feb 2006", "Dec 2007", "22 mo"),
              ("Aug 2019", "Feb 2020", "6 mo"), ("Jul 2022", "— (no NBER recession followed)", "n/a")]

def m_yield_curve():
    import numpy as np
    cur = {}
    for sid, lab, yrs in TENORS:
        try:
            cur[lab] = fred(sid, 2)
        except Exception:
            pass
    if len(cur) < 6:
        raise RuntimeError("FRED curve unavailable")
    df = pd.DataFrame(cur).ffill().dropna(how="all")
    last = df.iloc[-1]
    def chg(n):
        return (df.iloc[-1] - df.iloc[-1 - n]) * 100  # bps
    d1, d5, d21 = chg(1), chg(5), chg(21)
    t10y2y = float(last["10Y"] - last["2Y"]) * 100
    t10y3m = float(last["10Y"] - last["3M"]) * 100
    # shape
    if t10y2y < 0 and t10y3m < 0:
        shape, sc = "Inverted", RED
        shape_txt = ("Short rates above long rates across the curve — the bond market is pricing policy as "
                     "restrictive enough to force cuts. The best-documented recession signal there is, with "
                     "a long and variable lag.")
    elif abs(t10y2y) < 40 and abs(t10y3m) < 60:
        shape, sc = "Flat", AMBER
        shape_txt = ("Barely any compensation for holding duration — a late-cycle signature. The next 50bps "
                     "of movement usually declares which regime follows.")
    elif t10y2y > 120:
        shape, sc = "Steep", GREEN
        shape_txt = ("Healthy term premium: lenders are paid to hold duration. Steep and steepening from "
                     "positive territory is the expansion configuration.")
    else:
        shape, sc = "Normal", GREEN
        shape_txt = ("An upward slope with moderate term premium — the ordinary state of the world, and the "
                     "one that maps to nothing dramatic.")
    # curve regime quadrant
    d2, d10 = float(d21["2Y"]), float(d21["10Y"])
    if d2 > 0 and d10 < d2:
        regime = "Bear flattener"
    elif d2 < 0 and d10 < d2:
        regime = "Bull flattener"
    elif d2 < 0:
        regime = "Bull steepener"
    else:
        regime = "Bear steepener"
    desc, favours, pressures, watch = CURVE_PLAYS[regime]
    # curve chart: today vs 1m vs 1y
    labs = [l for _, l, _ in TENORS if l in df.columns]
    def snap(n):
        return [float(df[l].iloc[-1 - n]) for l in labs]
    curve_now, curve_1m = snap(0), snap(21)
    curve_1y = snap(min(252, len(df) - 1))
    W2, H2, P2 = 820, 240, 40
    allv = curve_now + curve_1m + curve_1y
    lo, hi = min(allv), max(allv)
    rg = (hi - lo) or 1
    X = lambda i: P2 + (W2 - 2 * P2) * i / (len(labs) - 1)
    Y = lambda v: P2 + (H2 - 2 * P2) * (1 - (v - lo) / rg)
    g = f'<rect x="{P2}" y="{P2}" width="{W2-2*P2}" height="{H2-2*P2}" fill="none" stroke="#2a2a2a"/>'
    for series, color, wdt in ((curve_1y, MUT, 1.2), (curve_1m, BLUE, 1.4), (curve_now, GOLD, 2.2)):
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(series))
        g += f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{wdt}"/>'
        for i, v in enumerate(series):
            if color == GOLD:
                g += f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.6" fill="{GOLD}"/>'
    for i, l in enumerate(labs):
        g += f'<text x="{X(i):.1f}" y="{H2-14}" fill="{MUT}" font-size="10" text-anchor="middle">{l}</text>'
    for v in (lo, (lo + hi) / 2, hi):
        g += f'<text x="6" y="{Y(v)+3:.1f}" fill="{MUT}" font-size="10">{v:.2f}%</text>'
    curve_svg = (f'<svg viewBox="0 0 {W2} {H2}" xmlns="http://www.w3.org/2000/svg" '
                 f'style="width:100%;height:auto;display:block">{g}</svg>')
    # rate sensitivity regression
    hist = yf.download([s for s, _ in RATE_SENS] + ["^TNX"], period="6mo", interval="1d",
                       auto_adjust=True, progress=False)["Close"].ffill(limit=2)
    dy = hist["^TNX"].diff() * 100  # bps
    sens = []
    for sym, name in RATE_SENS:
        if sym not in hist.columns:
            continue
        r = hist[sym].pct_change() * 100
        both = pd.concat([dy, r], axis=1).dropna().iloc[-90:]
        if len(both) < 30:
            continue
        x, y = both.iloc[:, 0].values, both.iloc[:, 1].values
        b, a = np.polyfit(x, y, 1)
        pred = a + b * x
        ss_res = float(((y - pred) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot else 0
        sens.append((name, b * 10, r2))
    # real yield
    real = fred("DFII10", 2)
    be = fred("T10YIE", 2)
    real_now = float(real.iloc[-1])
    real_1m = (real_now - float(real.iloc[-22])) * 100
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{sc}">{shape}</div>'
        f'<div class="muted" style="margin-top:3px">{shape_txt}</div>' +
        stat_grid([("10y − 2y", f"{t10y2y:+.0f} bps", col(t10y2y, lambda v: v > 0)),
                   ("10y − 3m", f"{t10y3m:+.0f} bps", col(t10y3m, lambda v: v > 0)),
                   ("Curve regime (21d)", regime, GOLD),
                   ("10y real (TIPS)", pct(real_now, 2), MUT),
                   ("10y breakeven", pct(float(be.iloc[-1]), 2), MUT)]), "CURVE SHAPE") + \
        "<h2>The curve · today vs 1 month vs 1 year ago</h2>" + card(
        curve_svg + f'<div class="legend"><span style="color:{GOLD}">▬</span> today · '
        f'<span style="color:{BLUE}">▬</span> one month ago · <span style="color:{MUT}">▬</span> one year ago. '
        'Each point is what the market charges to lend for that term. The SHAPE carries the signal; the drift '
        'between lines shows where the repricing is happening.</div>')
    body += "<h2>Tenor moves</h2>" + card(table(
        ["Tenor", "Yield", "1d", "1w", "1m"],
        [(f"<b>{l}</b>", pct(float(last[l]), 2),
          f'<span style="color:{RED if d1[l] > 0 else GREEN}">{d1[l]:+.0f}</span>',
          f'<span style="color:{RED if d5[l] > 0 else GREEN}">{d5[l]:+.0f}</span>',
          f'<span style="color:{RED if d21[l] > 0 else GREEN}">{d21[l]:+.0f}</span>') for l in labs]) +
        '<div class="legend">Change in basis points. Red = yields up (bonds down), green = yields down.</div>')
    if sens:
        body += "<h2>If the 10-year rises +10bps tomorrow…</h2>" + card(table(
            ["Asset", "Implied move", "R²"],
            [(f"<b>{n}</b>", cnum(b, 2), f'<span style="color:{GREEN if r2 > 0.3 else MUT}">{r2:.2f}</span>')
             for n, b, r2 in sens]) +
            '<div class="legend">Each asset\'s average response to a +10bp day in the 10-year over the last '
            '~90 sessions (OLS on daily changes). A low R² means a loose relationship — treat it as a lean, '
            'not a rule. Flip the signs for a yields-down day.</div>')
    body += f"<h2>Curve regime · {regime}</h2>" + card(
        f'<div class="muted">{desc}</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:10px">'
        f'<div><div class="slabel">FAVOURS</div>' +
        "".join(f'<div style="font-size:13px;color:{GREEN}">▸ {x}</div>' for x in favours) + "</div>"
        f'<div><div class="slabel">PRESSURES</div>' +
        "".join(f'<div style="font-size:13px;color:{RED}">▸ {x}</div>' for x in pressures) + "</div></div>"
        f'<div class="muted" style="margin-top:10px;font-size:12px"><b>Watch:</b> {watch}</div>',
        "PLAYBOOK")
    body += "<h2>Real yield</h2>" + card(
        stat_grid([("10y real (TIPS)", pct(real_now, 2), col(real_now, lambda v: v < 1.5, lambda v: v > 2.2)),
                   ("1-month change", f"{real_1m:+.0f} bps", col(real_1m, lambda v: v < 0)),
                   ("10y breakeven inflation", pct(float(be.iloc[-1]), 2), MUT)]) +
        '<div class="muted" style="margin-top:8px">The real yield is the after-inflation cost of money — the '
        'single most important driver for gold, long-duration growth and Bitcoin. Rising real yields pressure '
        'all three; falling real yields are their tailwind.</div>')
    body += "<h2>Inversions → recessions: the honest record</h2>" + card(table(
        ["Inversion began", "Recession began", "Lag"],
        [(f"<b>{a}</b>", b, c) for a, b, c in INVERSIONS]) +
        '<div class="legend">Two things this record actually shows: the lag is long and variable (6–22 months), '
        'and the danger window historically opens when the curve RE-STEEPENS out of inversion, not during it. '
        'The 2022 inversion resolving without an NBER recession is the standing counter-example — treat this '
        'as a base rate, not a law.</div>')
    stance = "bearish" if shape == "Inverted" else ("neutral" if shape == "Flat" else "neutral")
    return dict(slug="yield-curve", title="Yield Curve",
                sub="The full Treasury curve — shape, tenor moves, rate sensitivity, regime quadrant, and the real yield.",
                body=body, stance=stance,
                headline=f"{shape} curve · {regime} · 10y−2y {t10y2y:+.0f}bps")

CREDIT_ZONES = [("Complacent", 0, 300,
                 "Credit is priced for perfection. Carry works until it doesn't — this zone funds the best "
                 "entries elsewhere but offers no cushion when the regime turns.",
                 ["A full risk budget is defensible — but keep stops honest, because repricing from here is fast",
                  "Cheap insurance: puts on HYG/JNK cost least exactly when this zone says you may need them",
                  "Watch the velocity and CCC panels — they turn before the headline number does"],
                 "Adding leverage merely because nothing has broken yet. This zone is where that habit gets built and later punished."),
                ("Normal", 300, 400,
                 "Credit is charging a fair price for risk. The ordinary regime — nothing here argues for or "
                 "against equity exposure on its own.",
                 ["Standard risk budget; let the other tabs pick the direction",
                  "Spread direction matters more than the level — track the 20-day change",
                  "Rallies with spreads tightening alongside are the durable kind"],
                 "Over-reading a mid-range number. The signal in credit lives at the extremes and in the velocity."),
                ("Elevated", 400, 550,
                 "Lenders are demanding real compensation. Historically this zone has produced the best "
                 "forward equity returns — and the worst individual outcomes.",
                 ["Scale in, don't jump in — the widest zones reward patience over conviction",
                  "Quality over junk: IG and BBB recover first, CCC last",
                  "Falling spreads from here confirm the turn better than any equity signal"],
                 "Treating the average forward return as the expected one. The distribution here is brutally wide."),
                ("Distressed", 550, 10000,
                 "The market is pricing a default cycle. Panic prices bottoms — eventually — but the path "
                 "through this zone is where portfolios die.",
                 ["Survival first: size for the worst case, not the average case",
                  "The first sustained tightening off the highs is the highest-conviction risk-on signal in macro",
                  "Investment-grade credit usually offers equity-like returns with far less pain from here"],
                 "Catching the falling knife with leverage. Spreads can double from levels that already look extreme."),
                ]

def m_credit():
    series = {}
    for sid, name in (("BAMLC0A0CM", "Investment grade"), ("BAMLC0A4CBBB", "BBB (lowest IG)"),
                      ("BAMLH0A0HYM2", "High yield"), ("BAMLH0A3HYC", "CCC & below")):
        try:
            series[name] = fred(sid, 10) * 100  # bps
        except Exception:
            pass
    if "High yield" not in series:
        raise RuntimeError("FRED credit series unavailable")
    hy = series["High yield"]
    lvl = float(hy.iloc[-1])
    p3y = pctile(hy.iloc[-756:], lvl)
    # velocity
    vel = float(hy.iloc[-1] - hy.iloc[-21])
    vel_hist = (hy - hy.shift(21)).dropna()
    vel_p = pctile(vel_hist, vel)
    vel_txt = (f"Spread velocity is quiet ({vel:+.0f}bps/20d) — no urgency signal from credit regardless of the level."
               if abs(vel) < 30 else
               f"Spreads are widening fast ({vel:+.0f}bps/20d, {vel_p:.0f}th percentile of all 20-day windows) — "
               "velocity leads the level. This is the panel that fires before the headline number does."
               if vel > 0 else
               f"Spreads are compressing fast ({vel:+.0f}bps/20d) — credit is actively re-risking, which has "
               "historically confirmed equity rallies rather than preceded reversals.")
    # zone
    zone = next(z for z in CREDIT_ZONES if z[1] <= lvl < z[2])
    zname, _, _, zdesc, zactions, zavoid = zone
    zcol = {"Complacent": GREEN, "Normal": GREEN, "Elevated": AMBER, "Distressed": RED}[zname]
    light = {"Complacent": "GREEN — risk on", "Normal": "GREEN — risk on",
             "Elevated": "AMBER — reduce", "Distressed": "RED — defense"}[zname]
    # CCC gap
    gap_html = ""
    if "CCC & below" in series:
        ccc = series["CCC & below"]
        gap = float(ccc.iloc[-1] - hy.iloc[-1])
        gap_1m = gap - float(ccc.iloc[-22] - hy.iloc[-22])
        gap_txt = ("The bottom of the quality ladder is moving in line with broad high yield — no early-warning "
                   "signal from the junkiest cohort right now." if abs(gap_1m) < 40 else
                   "The CCC cohort is widening faster than broad high yield — stress is entering at the bottom "
                   "of the ladder, which is where it always enters first." if gap_1m > 0 else
                   "CCC is tightening faster than broad HY — aggressive risk appetite returning to the lowest "
                   "quality tier, historically a late-stage rally characteristic.")
        gap_html = card(
            stat_grid([("CCC minus HY", f"{gap:.0f} bps", MUT),
                       ("1-month change", f"{gap_1m:+.0f} bps", col(gap_1m, lambda v: v < 0))]) +
            f'<div class="muted" style="margin-top:8px">{gap_txt}</div>', "EARLY-WARNING WIRE · CCC MINUS HY")
    # quality ladder
    ladder = table(["Cohort", "OAS", "1w", "1m", "3y percentile"],
                   [(f"<b>{n}</b>", f"{float(s.iloc[-1]):.0f} bps",
                     f'<span style="color:{RED if s.iloc[-1] > s.iloc[-6] else GREEN}">{float(s.iloc[-1]-s.iloc[-6]):+.0f}</span>',
                     f'<span style="color:{RED if s.iloc[-1] > s.iloc[-22] else GREEN}">{float(s.iloc[-1]-s.iloc[-22]):+.0f}</span>',
                     f"{pctile(s.iloc[-756:], float(s.iloc[-1])):.0f}%")
                    for n, s in series.items()])
    # credit vs equities
    spy = yf.download("SPY", period="2y", interval="1d", auto_adjust=True,
                      progress=False)["Close"].squeeze().dropna()
    spy_21 = float((spy.iloc[-1] / spy.iloc[-22] - 1) * 100)
    if spy_21 > 0 and vel <= 5:
        cvd, cvc = "Confirming rally", GREEN
        cv_txt = ("Equities are rising and credit agrees — spreads flat to tighter. Rallies with credit "
                  "confirmation have historically been the durable ones.")
    elif spy_21 > 0 and vel > 5:
        cvd, cvc = "Bearish divergence", RED
        cv_txt = ("Equities up while spreads widen — the people paid to worry about default are worrying while "
                  "stockholders aren't. This divergence has front-run most major equity tops.")
    elif spy_21 <= 0 and vel > 5:
        cvd, cvc = "Confirming selloff", RED
        cv_txt = ("Both markets are de-risking together — a genuine risk-off episode rather than an equity-only "
                  "wobble. Wait for spreads to stop widening before buying the dip.")
    else:
        cvd, cvc = "Bullish divergence", GREEN
        cv_txt = ("Equities are falling while credit tightens — credit is refusing to confirm the selloff. "
                  "Historically this resolves in equities' favour.")
    hy_al, spy_al = hy.align(spy, join="inner")
    n = min(len(hy_al), 252)
    spy_n = (spy_al.iloc[-n:] / spy_al.iloc[-n] * 100).tolist()
    hy_inv = (-hy_al.iloc[-n:]).tolist()
    lo_h, hi_h = min(hy_inv), max(hy_inv)
    hy_scaled = [(v - lo_h) / ((hi_h - lo_h) or 1) * (max(spy_n) - min(spy_n)) + min(spy_n) for v in hy_inv]
    cv_chart = line_chart([spy_n, hy_scaled], [GOLD, BLUE])
    # forward returns by zone
    hy_d, spy_d = hy.align(spy, join="inner")
    fwd = (spy_d.shift(-63) / spy_d - 1) * 100
    zrows = []
    for zn, zlo, zhi, *_ in CREDIT_ZONES:
        mask = (hy_d >= zlo) & (hy_d < zhi)
        f = fwd[mask].dropna()
        if len(f) < 10:
            continue
        tag = ' <span class="pill" style="background:rgba(212,175,90,.15);color:#d4af37;font-size:10px">now</span>' if zn == zname else ""
        rng = f"< {zhi}" if zlo == 0 else (f"≥ {zlo}" if zhi > 1000 else f"{zlo}–{zhi}")
        zrows.append((f"<b>{zn}</b>{tag}", rng, cnum(float(f.mean()), 1),
                      f"{(f > 0).mean() * 100:.0f}%", f'<span style="color:{RED}">{float(f.min()):.1f}%</span>',
                      f"{len(f):,}"))
    body = card(
        f'<div style="font-size:30px;font-weight:700;color:{zcol}">{lvl:.0f} <span style="font-size:15px">bps</span></div>'
        f'<div style="margin-top:2px"><b style="color:{zcol}">{zname}</b> · {light} · '
        f'{p3y:.0f}th percentile of 3 years</div>'
        f'<div class="muted" style="margin-top:6px">High-yield spreads at {lvl:.0f}bps sit in the '
        f'{"tightest" if p3y < 50 else "widest"} {min(p3y, 100-p3y):.0f}% of recent history — '
        + ("credit sees almost no default risk. Excellent for carry, zero cushion for surprises."
           if p3y < 20 else
           "lenders are pricing genuine default risk; the cushion is there but so is the reason for it."
           if p3y > 70 else "credit is charging an ordinary price for risk.") + "</div>",
        "HIGH-YIELD OAS · THE RISK TRAFFIC LIGHT")
    body += card(stat_grid([("20-session change", f"{vel:+.0f} bps", col(vel, lambda v: v < 0)),
                            ("Percentile of all 20d windows", f"{vel_p:.0f}th", MUT)]) +
                 f'<div class="muted" style="margin-top:8px">{vel_txt}</div>', "VELOCITY ALARM")
    body += gap_html
    body += "<h2>The quality ladder</h2>" + card(
        ladder + '<div class="legend">Stress climbs the ladder from the bottom — CCC cracks first, investment '
        'grade last. A CCC widening that IG ignores is early; both widening together is late.</div>')
    body += f"<h2>Credit vs equities · {cvd}</h2>" + card(
        f'<div><b style="color:{cvc}">{cvd}</b> — 21 days: S&P {spy_21:+.1f}%, HY OAS {vel:+.0f}bps</div>'
        f'<div class="muted" style="margin-top:6px">{cv_txt}</div>' + cv_chart +
        f'<div class="legend"><span style="color:{GOLD}">▬</span> SPY · <span style="color:{BLUE}">▬</span> '
        'HY OAS plotted INVERTED, so the lines should move together when credit confirms equities. The lines '
        'peeling apart is the divergence.</div>')
    if zrows:
        body += "<h2>What the S&P did next, by spread zone</h2>" + card(table(
            ["Zone", "HY OAS", "Avg fwd 3m", "% positive", "Worst", "n"], zrows) +
            '<div class="legend">Forward 3-month S&P returns grouped by the HY spread on entry day, over the '
            'history this feed serves. Read your current row, then read the Worst column. The pattern worth '
            'internalising: average forward returns are HIGHEST from the widest zones — panic prices the bottom '
            'in — but so are the worst cases. The zone doesn\'t time entries; it sets how much risk one '
            'entry deserves.</div>')
    body += f"<h2>Playbook · {zname} zone</h2>" + card(
        f'<div class="muted">{zdesc}</div>' +
        "".join(f'<div style="font-size:13px;margin-top:5px">▸ {a}</div>' for a in zactions) +
        f'<div class="muted" style="margin-top:10px;font-size:12px"><b>Avoid:</b> {zavoid}</div>')
    body += card(
        "A credit spread is the extra yield lenders demand to hold a company's bond instead of a Treasury — "
        "literally the market's price of \"will this borrower survive?\". Because credit investors face ruin "
        "rather than missed upside, they turn cautious BEFORE equity investors do. That asymmetry is what makes "
        "this page an early-warning system you can use without ever touching a bond.", "THE 60-SECOND VERSION")
    stance = "bearish" if (vel > 30 or zname in ("Elevated", "Distressed")) else \
             ("bullish" if lvl < 350 else "neutral")
    return dict(slug="credit-spreads", title="Credit Spreads",
                sub="The price of default risk across the quality ladder — equity's earliest warning system.",
                body=body, stance=stance,
                headline=f"HY {lvl:.0f}bps ({zname}, {p3y:.0f}th pctile) · {cvd.lower()}")

LIQ_ASSETS = [("BTC-USD", "Bitcoin"), ("^GSPC", "S&P 500"), ("^NDX", "NASDAQ 100"), ("GC=F", "Gold")]

def _stablecoins():
    req = urllib.request.Request("https://stablecoins.llama.fi/stablecoincharts/all",
                                 headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=25).read())
    s = pd.Series({pd.to_datetime(int(d["date"]), unit="s"): float(d["totalCirculating"]["peggedUSD"])
                   for d in data if d.get("totalCirculating", {}).get("peggedUSD")})
    return s.sort_index() / 1e9  # $bn

def _liq_state(yoy, imp):
    if yoy > 0 and imp > 0: return "Expanding & accelerating", GREEN
    if yoy > 0: return "Expanding, decelerating", AMBER
    if imp > 0: return "Contracting, improving", AMBER
    return "Contracting & worsening", RED

def m_liquidity():
    walcl = fred("WALCL", 8) / 1000          # $bn
    rrp = fred("RRPONTSYD", 8)               # $bn
    tga = fred("WTREGEN", 8) / 1000          # $bn
    m2 = fred("M2SL", 8)                     # $bn
    ecb = fred("ECBASSETSW", 8)              # € mn
    boj = fred("JPNASSETS", 8)               # ¥ 100mn
    fx = yf.download(["EURUSD=X", "JPY=X"], period="8y", interval="1d",
                     auto_adjust=True, progress=False)["Close"].ffill()
    wk = lambda s: s.resample("W-FRI").last().ffill()
    fed_w, rrp_w, tga_w, m2_w = wk(walcl), wk(rrp), wk(tga), wk(m2)
    idx = fed_w.index
    us_net = (fed_w - rrp_w.reindex(idx).ffill() - tga_w.reindex(idx).ffill()).dropna()
    eur = wk(fx["EURUSD=X"]).reindex(wk(ecb).index).ffill()
    jpy = wk(fx["JPY=X"]).reindex(wk(boj).index).ffill()
    ecb_usd = wk(ecb) * eur / 1000             # € mn -> $bn
    boj_usd = wk(boj) / (10 * jpy)             # ¥100mn -> $bn (×1e8 yen ÷ USDJPY ÷ 1e9)
    g3 = (fed_w + ecb_usd.reindex(idx).ffill() + boj_usd.reindex(idx).ffill()).dropna()
    try:
        stab = wk(_stablecoins())
    except Exception:
        stab = None
    legs = [("G3 central banks", g3, "T"), ("US net liquidity", us_net, "T"),
            ("US M2", m2_w, "T")] + ([("Stablecoins", stab, "B")] if stab is not None else [])
    cards, states = "", {}
    for name, s, unit in legs:
        s = s.dropna()
        yoy = float((s.iloc[-1] / s.iloc[-53] - 1) * 100)
        imp13 = float(((s.iloc[-1] / s.iloc[-14]) ** 4 - 1) * 100)
        prev_yoy = float((s.iloc[-14] / s.iloc[-66] - 1) * 100)
        state, sc = _liq_state(yoy, yoy - prev_yoy)
        states[name] = (yoy, imp13, state, sc)
        val = f"${s.iloc[-1]/1000:,.2f}T" if unit == "T" else f"${s.iloc[-1]:,.1f}B"
        cards += (f'<div><div class="slabel">{name}</div>'
                  f'<div class="sval">{val}</div>'
                  f'<div style="font-size:12px">YoY <b style="color:{GREEN if yoy>0 else RED}">{yoy:+.1f}%</b>'
                  f' · 13w ann. <b style="color:{GREEN if imp13>0 else RED}">{imp13:+.1f}%</b></div>'
                  f'<div style="font-size:11px;color:{sc}">{state}</div></div>')
    g3_yoy, _, g3_state, g3c = states["G3 central banks"]
    if g3_yoy > 3:
        regime, rc, stance = "Tailwind", GREEN, "bullish"
        rtxt = (f"Global liquidity is expanding {g3_yoy:+.1f}% year over year — the configuration risk assets "
                "like most, and the liquidity-sensitive ones (crypto, long-duration growth) like most of all.")
    elif g3_yoy > -2:
        regime, rc, stance = "Neutral", AMBER, "neutral"
        rtxt = (f"Liquidity is roughly flat year over year ({g3_yoy:+.1f}%) — no tide either way. Assets have to "
                "earn their moves on fundamentals and positioning rather than being carried.")
    else:
        regime, rc, stance = "Headwind", RED, "bearish"
        rtxt = (f"Liquidity is contracting {g3_yoy:+.1f}% year over year — the toughest configuration for risk, "
                "and the one that punishes the liquidity-sensitive assets first and hardest.")
    # lead/lag matrix
    px_l = yf.download([s for s, _ in LIQ_ASSETS], period="8y", interval="1d",
                       auto_adjust=True, progress=False)["Close"].ffill()
    matrix, best_lead = [], None
    for sym, aname in LIQ_ASSETS:
        a13 = wk(px_l[sym].dropna()).pct_change(13).dropna() * 100
        row = []
        for lname, s, _u in legs:
            l13 = s.dropna().pct_change(13).dropna() * 100
            best = (0, 0.0)
            for lead in range(0, 19):
                shifted = l13.shift(lead)
                both = pd.concat([shifted, a13], axis=1).dropna().iloc[-260:]
                if len(both) < 60:
                    continue
                r = float(both.iloc[:, 0].corr(both.iloc[:, 1]))
                if abs(r) > abs(best[1]):
                    best = (lead, r)
            row.append((lname, best[0], best[1]))
            if aname == "Bitcoin" and lname == "G3 central banks":
                best_lead = best
        matrix.append((aname, row))
    def rcell(r):
        c = GREEN if r >= 0.35 else (RED if r <= -0.35 else "var(--tx)")
        return c
    mhdr = "".join(f"<th>{l}</th>" for l, _, _ in legs)
    mrows = "".join(
        f"<tr><td><b>{an}</b></td>" + "".join(
            f'<td style="color:{rcell(r)};white-space:nowrap">{ld}w · r={r:+.2f}</td>' for _, ld, r in row)
        + "</tr>" for an, row in matrix)
    # liquidity cycle chart (YoY rates)
    def yoy_series(s, n=156):
        return (s.dropna().pct_change(52) * 100).dropna().iloc[-n:]
    g3y, usy, m2y = yoy_series(g3), yoy_series(us_net), yoy_series(m2_w)
    cyc = line_chart([g3y.tolist(), usy.tolist(), m2y.tolist()], [GOLD, BLUE, MUT],
                     hlines=[(0, RED, "0")])
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{rc}">{regime}</div>'
        f'<div class="muted" style="margin-top:3px">{rtxt}</div>'
        f'<div class="stats" style="margin-top:12px">{cards}</div>', "LIQUIDITY REGIME")
    body += "<h2>The liquidity cycle · year-over-year rate of change</h2>" + card(
        cyc + f'<div class="legend"><span style="color:{GOLD}">▬</span> G3 central banks · '
        f'<span style="color:{BLUE}">▬</span> US net liquidity · <span style="color:{MUT}">▬</span> US M2, '
        'last 3 years. This is the FLOW, not the level. Assets respond to TURNS in these lines: a line hooking '
        'up from below zero has historically been the earliest "tide is turning" signal, arriving before the '
        'level itself recovers. Zero-line crossings mark expansion ↔ contraction regime changes per leg.</div>')
    body += "<h2>Lead/lag matrix</h2>" + card(
        f'<div style="overflow-x:auto"><table><tr><th>Asset</th>{mhdr}</tr>{mrows}</table></div>'
        '<div class="legend">Each cell scans 0–18 week leads on 13-week rates of change and reports the '
        'best-fit lead and its correlation: "when this liquidity measure moves, how many weeks later does the '
        'asset respond, and how tightly?" Green = strong positive coupling, red = strong inverse. A weak |r| '
        'means the asset is currently running on something other than liquidity.</div>')
    if best_lead:
        body += card(
            f"Bitcoin's best fit against G3 liquidity right now is a <b>{best_lead[0]}-week lead</b> with "
            f"correlation <b style='color:{rcell(best_lead[1])}'>r = {best_lead[1]:+.2f}</b>. Read that as: "
            "liquidity turns first, Bitcoin follows about " + (f"{best_lead[0]} weeks later" if best_lead[0] else
            "immediately") + ". When the coupling is tight the liquidity signal is live; when it decouples, "
            "the crypto narrative is running on something else entirely.", "THE HEADLINE COUPLING")
    body += card(
        "Liquidity is the tide. US net liquidity = the Fed's balance sheet minus the reverse-repo facility "
        "minus the Treasury's cash account — the dollars actually available to the financial system. G3 adds "
        "the ECB and Bank of Japan converted to dollars, because capital doesn't respect borders. Stablecoins "
        "are the crypto-native leg and run far hotter than the fiat ones. Levels tell you where you are; the "
        "rate-of-change chart tells you where you're going, and that's the one assets respond to.",
        "WHAT THIS MEASURES")
    return dict(slug="liquidity", title="Global Liquidity",
                sub="The tide — G3 central banks, US net liquidity, M2 and stablecoins, with measured lead/lag against risk assets.",
                body=body, stance=stance,
                headline=f"{regime} — G3 liquidity {g3_yoy:+.1f}% YoY")

FCI_INPUTS = [("real10", "Real 10y yield", "TIPS — the true cost of money", 1),
              ("dollar", "Broad dollar", "global funding pressure", 1),
              ("vix", "Equity vol (VIX)", "risk-appetite thermometer", 1),
              ("move", "Bond vol (MOVE)", "rates-market stress", 1),
              ("hy", "HY credit spread", "the price of default risk", 1),
              ("mort", "30y mortgage rate", "household credit cost", 1),
              ("dd", "S&P drawdown", "wealth-effect channel (deeper = tighter)", -1)]

FCI_BETA_ASSETS = [("^GSPC", "S&P 500"), ("^NDX", "NASDAQ 100"), ("IWM", "Small caps"),
                   ("GC=F", "Gold"), ("BTC-USD", "Bitcoin"), ("TLT", "Long bonds")]

def m_finconditions():
    import numpy as np
    nfci = fred("NFCI", 60)
    stlfsi = fred("STLFSI4", 30)
    kcfsi = fred("KCFSI", 30)
    # live daily composite
    real10 = fred("DFII10", 4)
    dollar = fred("DTWEXBGS", 4)
    hy = fred("BAMLH0A0HYM2", 4)
    mort = fred("MORTGAGE30US", 4)
    mkt = yf.download(["^VIX", "^MOVE", "^GSPC"], period="4y", interval="1d",
                      auto_adjust=True, progress=False)["Close"].ffill(limit=3)
    spx = mkt["^GSPC"].dropna()
    dd = (spx / spx.cummax() - 1) * 100
    raw = dict(real10=real10, dollar=dollar, hy=hy, mort=mort,
               vix=mkt["^VIX"].dropna(), move=mkt["^MOVE"].dropna(), dd=dd)
    df = pd.DataFrame({k: v for k, v in raw.items()}).ffill().dropna()
    z = (df - df.rolling(756, min_periods=250).mean()) / df.rolling(756, min_periods=250).std()
    for key, _, _, sign in FCI_INPUTS:
        z[key] = z[key] * sign
    comp = z.mean(axis=1).dropna()
    lvl = float(comp.iloc[-1])
    imp = float(lvl - comp.iloc[-21])
    state = ("Tight" if lvl > 0.5 else "Loose" if lvl < -0.5 else "Neutral")
    scol = RED if lvl > 0.5 else (GREEN if lvl < -0.5 else AMBER)
    direction = "loosening" if imp < -0.05 else ("tightening" if imp > 0.05 else "stable")
    dtxt = ("A loosening impulse is the classic risk-asset tailwind — the cross-asset table shows who "
            "historically benefits most." if imp < -0.05 else
            "A tightening impulse drains the fuel from risk assets, hitting the highest-duration ones first."
            if imp > 0.05 else "Conditions are drifting sideways; no impulse to trade off right now.")
    # official indices
    off_rows = []
    for name, s, freq, note in (("Chicago Fed NFCI", nfci, "weekly", "broadest (100+ inputs)"),
                                ("St. Louis Fed FSI", stlfsi, "weekly", "financial stress"),
                                ("Kansas City Fed FSI", kcfsi, "monthly", "financial stress")):
        try:
            v = float(s.iloc[-1])
            p = pctile(s, v)
            chg = v - float(s.iloc[-13])
            off_rows.append((name, v, p, chg, freq, note))
        except Exception:
            continue
    off_html = "".join(
        f'<div style="padding:7px 0;border-bottom:1px solid var(--line)">'
        f'<div style="display:flex;justify-content:space-between"><span><b>{n}</b> '
        f'<span class="pill" style="background:{(GREEN if v<0 else RED)}22;color:{GREEN if v<0 else RED};font-size:10px">'
        f'{"Loose" if v < 0 else "Tight"}</span></span><b>{v:+.3f}</b></div>'
        f'<div class="muted" style="font-size:11px">{p:.0f}th percentile of its history · '
        f'{"loosening" if c < 0 else "tightening"} ({c:+.3f} / 3m) · {f2} · {nt}</div></div>'
        for n, v, p, c, f2, nt in off_rows)
    # component drivers
    zl = z.iloc[-1]
    z1m = z.iloc[-22]
    comp_rows = []
    for key, name, note, sign in FCI_INPUTS:
        now_v = float(df[key].iloc[-1])
        push = float(zl[key] - z1m[key]) / len(FCI_INPUTS)
        unit = "%" if key in ("real10", "hy", "mort", "dd") else ("idx" if key == "dollar" else "")
        comp_rows.append((f"<b>{name}</b><div class='muted' style='font-size:11px'>{note}</div>",
                          f"{now_v:,.2f}{unit}",
                          f'<span style="color:{RED if zl[key] > 0 else GREEN}">{float(zl[key]):+.2f}</span>',
                          f"{float(z1m[key]):+.2f}",
                          f'<span style="color:{RED if push > 0 else GREEN}">{"↑" if push > 0 else "↓"} {push:+.2f}</span>'))
    # cross-asset betas
    beta_px = yf.download([s for s, _ in FCI_BETA_ASSETS], period="2y", interval="1d",
                          auto_adjust=True, progress=False)["Close"].ffill(limit=3)
    comp_w = comp.resample("W-FRI").last()
    dcomp = comp_w.diff().dropna()
    brows = []
    for sym, name in FCI_BETA_ASSETS:
        if sym not in beta_px.columns:
            continue
        aw = beta_px[sym].dropna().resample("W-FRI").last().pct_change() * 100
        both = pd.concat([dcomp, aw], axis=1).dropna()
        if len(both) < 40:
            continue
        x, y = both.iloc[:, 0].values, both.iloc[:, 1].values
        b, a = np.polyfit(x, y, 1)
        pred = a + b * x
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - float(((y - pred) ** 2).sum()) / ss_tot if ss_tot else 0
        beta01 = b * 0.1                     # response to +0.1σ tightening
        lean = -beta01 * (imp / 0.1) if imp else 0
        sig = "tailwind" if lean > 0.3 else ("headwind" if lean < -0.3 else "neutral")
        brows.append((f"<b>{name}</b>", f"{beta01:+.2f}%/wk",
                      f'<span style="color:{GREEN if r2 > 0.3 else MUT}">{r2:.2f}</span>',
                      cnum(lean, 1),
                      f'<span style="color:{GREEN if sig=="tailwind" else (RED if sig=="headwind" else MUT)}">{sig}</span>'))
    body = card(
        f'<div style="font-size:30px;font-weight:700;color:{scol}">{lvl:+.2f}<span style="font-size:15px">σ</span></div>'
        f'<div><b style="color:{scol}">{state}</b> → {direction}</div>'
        f'<div class="muted" style="margin-top:6px">Conditions are {state.lower()} ({lvl:+.2f}σ versus the '
        f'3-year average) and {direction} ({imp:+.2f}σ over the last month). {dtxt}</div>',
        "LIVE DAILY COMPOSITE · σ vs 3-YEAR AVERAGE")
    body += "<h2>The official indices</h2>" + card(off_html)
    body += "<h2>What's driving conditions</h2>" + card(
        table(["Input", "Now", "z-score", "1m ago", "Push"], comp_rows) +
        '<div class="legend">z-scores versus each input\'s trailing 3 years; red = tightening pressure. '
        '"Push" is how much each input moved the composite over the last month — the red rows are WHERE the '
        'tightening is coming from, and rates, the dollar, vol, credit and housing each transmit to different '
        'assets.</div>')
    if brows:
        body += f"<h2>Cross-asset response · current 4-week impulse {imp:+.2f}σ</h2>" + card(
            table(["Asset", "β per +0.1σ tightening", "R²", "Implied lean now", "Signal"], brows) +
            '<div class="legend">β is each asset\'s measured weekly response to a 0.1σ TIGHTENING of the live '
            'composite (OLS on weekly changes, trailing 2 years). "Implied lean" applies the current impulse '
            'to that β. Low R² = a loose relationship; treat it as a lean, not a forecast.</div>')
    body += card(
        "Financial conditions are the transmission channel between the Fed and everything you trade. The three "
        "official indices are authoritative but lag — weekly or monthly, published with a delay. So this page "
        "also builds a daily composite from the live inputs that actually move: the real cost of money (TIPS), "
        "the dollar (global funding), equity and bond vol, the price of default risk, mortgage rates, and the "
        "wealth-effect channel. Watch the DIRECTION more than the level: the impulse is what assets respond to.",
        "WHY BOTH A LIVE COMPOSITE AND THE OFFICIAL ONES")
    stance = "bullish" if (lvl < 0 and imp < 0) else ("bearish" if (lvl > 0.5 or imp > 0.15) else "neutral")
    return dict(slug="financial-conditions", title="Financial Conditions",
                sub="A live daily conditions composite with its drivers, the three official Fed indices, and measured cross-asset betas.",
                body=body, stance=stance,
                headline=f"{state} ({lvl:+.2f}σ) and {direction}")

PHASE_TILTS = {
    "Early": ("Growth is re-accelerating off a low base while policy is still easy — the highest-beta phase.",
              ["Consumer Discretionary", "Financials", "Real Estate", "Industrials"],
              ["Consumer Staples", "Utilities", "Health Care"]),
    "Mid": ("Growth is steady, inflation contained, policy neutral. Trends persist and drawdowns stay shallow.",
            ["Information Technology", "Industrials", "Communication Services"],
            ["Utilities", "Energy", "Materials"]),
    "Late": ("Inflation pressure peaks and policy tightens. Hard-asset cyclicals and defensives beat "
             "high-multiple growth.",
             ["Energy", "Materials", "Consumer Staples", "Health Care"],
             ["Consumer Discretionary", "Information Technology", "Real Estate"]),
    "Recession": ("Growth is contracting and policy is turning. Capital protection first; the turn pays "
                  "those still solvent.",
                  ["Consumer Staples", "Utilities", "Health Care", "Long bonds"],
                  ["Financials", "Industrials", "Energy", "Small caps"]),
}
QUADRANTS = {
    ("up", "up"): ("Overheat", "growth ↑ · inflation ↑", ["Commodities", "Energy", "Value"], AMBER),
    ("up", "dn"): ("Goldilocks", "growth ↑ · inflation ↓", ["Equities broadly", "Tech", "Small caps"], GREEN),
    ("dn", "up"): ("Stagflation", "growth ↓ · inflation ↑", ["Cash", "Gold", "Energy"], RED),
    ("dn", "dn"): ("Disinflation", "growth ↓ · inflation ↓", ["Long bonds", "Quality", "Staples"], BLUE),
}

def _trend_arrow(s, n=3):
    if len(s) < n + 1:
        return "→"
    d = float(s.iloc[-1] - s.iloc[-1 - n])
    sd = float(s.diff().std()) or 1
    return "↗" if d > sd * 0.5 else ("↘" if d < -sd * 0.5 else "→")

def m_business_cycle():
    ind = {}
    specs = [("GDPC1", "Real GDP (q/q ann.)", "Quarterly", "yoy", "%"),
             ("CPIAUCSL", "CPI (YoY)", "Monthly", "yoy", "%"),
             ("UNRATE", "Unemployment rate", "Monthly", "level", "%"),
             ("INDPRO", "Industrial production (YoY)", "Monthly", "yoy", "%"),
             ("DFF", "Fed funds rate", "Daily", "level", "%"),
             ("T10Y2Y", "10y−2y spread", "Daily", "bps", "bps"),
             ("ICSA", "Initial claims (4w, YoY)", "Weekly", "yoy4", "%"),
             ("T10YIE", "10y breakeven inflation", "Daily", "level", "%"),
             ("NFCI", "Financial conditions (NFCI)", "Weekly", "level", "idx"),
             ("RSAFS", "Retail sales (YoY)", "Monthly", "yoy", "%"),
             ("HOUST", "Housing starts (YoY)", "Monthly", "yoy", "%")]
    for sid, name, freq, kind, unit in specs:
        try:
            s = fred(sid, 12).dropna()
            if kind == "yoy":
                per = {"Quarterly": 4, "Monthly": 12}.get(freq, 12)
                v = float((s.iloc[-1] / s.iloc[-1 - per] - 1) * 100)
                hist = (s / s.shift(per) - 1).dropna() * 100
            elif kind == "yoy4":
                sm = s.rolling(4).mean().dropna()
                v = float((sm.iloc[-1] / sm.iloc[-53] - 1) * 100)
                hist = (sm / sm.shift(52) - 1).dropna() * 100
            elif kind == "bps":
                v = float(s.iloc[-1] * 100)
                hist = s * 100
            else:
                v = float(s.iloc[-1])
                hist = s
            ind[name] = dict(v=v, arrow=_trend_arrow(hist), freq=freq, unit=unit,
                             asof=s.index[-1].strftime("%Y-%m"),
                             age=(pd.Timestamp(NOW.date()) - s.index[-1]).days)
        except Exception:
            continue
    spx = yf.download("^GSPC", period="3y", interval="1d", auto_adjust=True,
                      progress=False)["Close"].squeeze().dropna()
    eq_yoy = float((spx.iloc[-1] / spx.iloc[-253] - 1) * 100)
    ind["Equity momentum (S&P)"] = dict(v=eq_yoy, arrow=_trend_arrow((spx / spx.shift(252) - 1).dropna() * 100),
                                        freq="Daily", unit="%", asof=NOW.strftime("%Y-%m"), age=0)
    # phase scoring
    growth = ind.get("Real GDP (q/q ann.)", {}).get("v", 0)
    infl = ind.get("CPI (YoY)", {}).get("v", 2)
    un = ind.get("Unemployment rate", {}).get("v", 4)
    curve = ind.get("10y−2y spread", {}).get("v", 0)
    unrate_s = fred("UNRATE", 5)
    sahm = float((unrate_s.rolling(3).mean() - unrate_s.rolling(3).mean().rolling(12).min()).iloc[-1])
    if sahm >= 0.5 or growth < 0:
        phase = "Recession"
    elif infl > 3 and growth > 0:
        phase = "Late"
    elif growth > 2 and infl <= 3:
        phase = "Mid"
    else:
        phase = "Early"
    pcol = {"Early": GREEN, "Mid": GREEN, "Late": AMBER, "Recession": RED}[phase]
    score = int(min(95, max(5, 50 + growth * 5 + (infl - 2) * 4 - sahm * 30)))
    # quadrant
    cpi_s = fred("CPIAUCSL", 4)
    cpi_yoy = (cpi_s / cpi_s.shift(12) - 1).dropna() * 100
    ip_s = fred("INDPRO", 4)
    ip_yoy = (ip_s / ip_s.shift(12) - 1).dropna() * 100
    g_dir = "up" if float(ip_yoy.iloc[-1] - ip_yoy.iloc[-4]) > 0 else "dn"
    i_dir = "up" if float(cpi_yoy.iloc[-1] - cpi_yoy.iloc[-4]) > 0 else "dn"
    qname, qdesc, qfav, qcol = QUADRANTS[(g_dir, i_dir)]
    # quadrant svg with 4-quarter trail
    S = 420
    trail = []
    for k in range(4, -1, -1):
        gi = float(ip_yoy.iloc[-1 - k * 3]) if len(ip_yoy) > k * 3 else 0
        ii = float(cpi_yoy.iloc[-1 - k * 3]) if len(cpi_yoy) > k * 3 else 0
        trail.append((gi, ii))
    gs = [t[0] for t in trail]; iss = [t[1] for t in trail]
    gspan = max(2.0, max(abs(min(gs)), abs(max(gs))) * 1.4)
    ispan_lo, ispan_hi = min(iss) - 1, max(iss) + 1
    X = lambda g: 40 + (S - 80) * (g + gspan) / (2 * gspan)
    Y = lambda i: S - 40 - (S - 80) * (i - ispan_lo) / ((ispan_hi - ispan_lo) or 1)
    cx, cy = X(0), Y(2.0)
    g = (f'<rect x="40" y="40" width="{S-80}" height="{S-80}" fill="none" stroke="#2a2a2a"/>'
         f'<line x1="{cx}" x2="{cx}" y1="40" y2="{S-40}" stroke="{MUT}" stroke-width="0.6"/>'
         f'<line x1="40" x2="{S-40}" y1="{cy}" y2="{cy}" stroke="{MUT}" stroke-width="0.6"/>'
         f'<text x="46" y="56" fill="{RED}" font-size="10" font-weight="600">STAGFLATION</text>'
         f'<text x="{S-46}" y="56" text-anchor="end" fill="{AMBER}" font-size="10" font-weight="600">OVERHEAT</text>'
         f'<text x="46" y="{S-46}" fill="{BLUE}" font-size="10" font-weight="600">DISINFLATION</text>'
         f'<text x="{S-46}" y="{S-46}" text-anchor="end" fill="{GREEN}" font-size="10" font-weight="600">GOLDILOCKS</text>'
         f'<text x="{S/2}" y="{S-8}" text-anchor="middle" fill="{MUT}" font-size="10">growth (industrial production YoY) →</text>')
    pts = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in trail)
    g += f'<polyline points="{pts}" fill="none" stroke="{GOLD}" stroke-width="1.2" stroke-dasharray="4 3" opacity="0.7"/>'
    for j, (a, b) in enumerate(trail):
        r = 5 if j == len(trail) - 1 else 2.4
        g += f'<circle cx="{X(a):.1f}" cy="{Y(b):.1f}" r="{r}" fill="{qcol if j == len(trail)-1 else GOLD}" opacity="{1 if j==len(trail)-1 else 0.5}"/>'
    quad_svg = f'<svg viewBox="0 0 {S} {S}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:460px;height:auto;display:block;margin:0 auto">{g}</svg>'
    desc, over, under = PHASE_TILTS[phase]
    ind_rows = [(f"<b>{n}</b>", f'<span class="muted">{d["freq"]} · {d["asof"]} · {d["age"]}d ago</span>',
                 f'{d["v"]:+.2f}{d["unit"]}' if d["unit"] != "bps" else f'{d["v"]:+.0f}',
                 f'<span style="color:{GOLD}">{d["arrow"]}</span>') for n, d in ind.items()]
    body = card(
        f'<div style="display:flex;gap:14px;align-items:baseline"><div style="font-size:30px;font-weight:700;'
        f'color:{pcol}">{score}<span style="font-size:14px">/100</span></div>'
        f'<div><b style="color:{pcol}">{phase} cycle</b> · macro regime '
        f'<b style="color:{qcol}">{qname}</b></div></div>'
        f'<div class="muted" style="margin-top:6px">Growth (industrial production) {ip_yoy.iloc[-1]:+.1f}% YoY, '
        f'inflation {infl:+.1f}% YoY, unemployment {un:.1f}%, curve {curve:+.0f}bps, Sahm gap {sahm:+.2f}. '
        f'{desc}</div>' +
        stat_grid([("Sahm rule gap", f"{sahm:+.2f}", col(sahm, lambda v: v < 0.5)),
                   ("Growth direction", "rising" if g_dir == "up" else "falling", GREEN if g_dir == "up" else RED),
                   ("Inflation direction", "rising" if i_dir == "up" else "falling", RED if i_dir == "up" else GREEN),
                   ("Curve (10y−2y)", f"{curve:+.0f} bps", col(curve, lambda v: v > 0))]),
        "CYCLE PHASE & MACRO REGIME")
    body += f"<h2>Macro regime quadrant · {qname}</h2>" + card(
        quad_svg + f'<div class="muted" style="margin-top:6px"><b style="color:{qcol}">{qname}</b> — {qdesc}. '
        f'Historically favours: {", ".join(qfav)}.</div>'
        '<div class="legend">Each quadrant is a growth × inflation regime, independent of cycle phase — a '
        'mid-phase economy can sit in a stagflation regime without being in recession. The gold dashed trail '
        'is the last four quarter-ends; the large dot is now. Vertical axis crosses at 2% inflation (the target).</div>')
    body += "<h2>The indicator board</h2>" + card(
        table(["Indicator", "Source & vintage", "Latest", "Trend"], ind_rows) +
        '<div class="legend">Every input with its release frequency and how stale it is. Macro data is '
        'backward-looking by construction — the vintage column is there so you know how much of the present '
        'each number can actually see.</div>')
    body += f"<h2>Sector tilts · {phase} cycle</h2>" + card(
        f'<div class="muted">{desc}</div>'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:10px">'
        f'<div><div class="slabel">OVERWEIGHT</div>' +
        "".join(f'<div style="font-size:13px;color:{GREEN}">▸ {x}</div>' for x in over) + "</div>"
        f'<div><div class="slabel">UNDERWEIGHT</div>' +
        "".join(f'<div style="font-size:13px;color:{RED}">▸ {x}</div>' for x in under) + "</div></div>"
        '<div class="legend">Phase-based tilts are a starting hypothesis, not a mandate — cross-check against '
        'the Relative Strength tab, which measures what is actually leading right now.</div>')
    body += card(
        "The business cycle is the slow clock behind every other regime on this terminal. The phase read "
        "combines the Sahm rule (a 0.50pt rise in the three-month average unemployment rate off its low has "
        "called every post-war US recession), growth, inflation and the curve. The quadrant is a separate, "
        "faster read: which way growth and inflation are MOVING, which is what maps to asset leadership. "
        "Phase tells you where you are in the cycle; the quadrant tells you what to own this quarter.",
        "HOW THE TWO READS DIFFER")
    stance = {"Early": "bullish", "Mid": "bullish", "Late": "neutral", "Recession": "bearish"}[phase]
    return dict(slug="business-cycle", title="Business Cycle",
                sub="Cycle phase, the growth × inflation regime quadrant, and the full indicator board with data vintages.",
                body=body, stance=stance,
                headline=f"{phase} cycle · {qname} regime · Sahm gap {sahm:+.2f}")

MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M", 7: "N", 8: "Q",
              9: "U", 10: "V", 11: "X", 12: "Z"}
# FOMC decision days (second day of each meeting)
FOMC = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
        "2026-09-16", "2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17"]

def _last_close(df):
    """Last close as a float, whatever shape yfinance hands back.

    Single-ticker downloads return MultiIndex columns on newer yfinance, so
    df["Close"] can be a DataFrame rather than a Series.
    """
    if df is None or not len(df):
        return None
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c = c.dropna()
    return float(c.iloc[-1]) if len(c) else None

def _zq_implied(year, month):
    t = f"ZQ{MONTH_CODE[month]}{str(year)[-2:]}.CBT"
    last = _last_close(yf.download(t, period="10d", progress=False, auto_adjust=False))
    return None if last is None else 100 - last

def _meeting_probs(effr):
    """CME-style: back out post-meeting rates from ZQ, propagate a 25bp distribution."""
    meetings = [pd.Timestamp(d) for d in FOMC if pd.Timestamp(d) > pd.Timestamp(NOW.date())]
    rows, r_start = [], effr
    dist = {round(effr, 4): 1.0}
    for mt in meetings[:6]:
        imp = _zq_implied(mt.year, mt.month)
        if imp is None:
            continue
        n = mt.days_in_month
        d = mt.day
        # month average = (d-1)/n * r_start + (n-d+1)/n * r_end
        r_end = (n * imp - (d - 1) * r_start) / (n - d + 1)
        em = (r_end - r_start) * 100  # bps expected change at this meeting
        # per-meeting move distribution in 25bp steps
        moves = {}
        k = abs(em) / 25.0
        full = int(k)
        frac = k - full
        sign = 1 if em >= 0 else -1
        moves[sign * full * 25] = 1 - frac
        moves[sign * (full + 1) * 25] = frac
        moves = {m: p for m, p in moves.items() if p > 1e-6}
        nd = {}
        for lvl, p in dist.items():
            for mv, pm in moves.items():
                k2 = round(lvl + mv / 100, 4)
                nd[k2] = nd.get(k2, 0) + p * pm
        dist = nd
        # collapse to 25bp target ranges
        buckets = {}
        for lvl, p in dist.items():
            lo = math.floor(lvl * 4) / 4
            buckets[lo] = buckets.get(lo, 0) + p
        tot = sum(buckets.values())
        buckets = {k2: v / tot for k2, v in buckets.items() if v / tot > 0.008}
        modal = max(buckets, key=buckets.get)
        rows.append(dict(date=mt.strftime("%Y-%m-%d"),
                         label=mt.strftime("%b %Y"),
                         days=(mt - pd.Timestamp(NOW.date())).days,
                         buckets=sorted(buckets.items()),
                         modal=modal, modal_p=buckets[modal] * 100,
                         edelta=(sum(k2 * v for k2, v in buckets.items()) + 0.125 - effr) * 100))
        r_start = r_end
    return rows

def _polymarket_fed():
    """Pull the 'how many Fed cuts this year' event; each market is a Yes/No leg."""
    q = ("https://gamma-api.polymarket.com/events?closed=false&limit=100"
         "&order=volume&ascending=false")
    req = urllib.request.Request(q, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=25).read())
    ev = next((e for e in data
               if "fed" in (e.get("title", "") + e.get("slug", "")).lower()
               and "cut" in (e.get("title", "") + e.get("slug", "")).lower()), None)
    if not ev:
        return None
    rows = []
    for m in ev.get("markets", []):
        try:
            outs = json.loads(m["outcomes"]) if isinstance(m["outcomes"], str) else m["outcomes"]
            prices = json.loads(m["outcomePrices"]) if isinstance(m["outcomePrices"], str) else m["outcomePrices"]
            yes = float(dict(zip(outs, prices)).get("Yes", 0)) * 100
            label = m.get("groupItemTitle") or m.get("question", "")
            rows.append((label, yes))
        except Exception:
            continue
    if not rows:
        return None
    rows.sort(key=lambda r: -r[1])
    return dict(q=ev.get("title", "Fed rate cuts"), rows=rows)

def m_fed_path(px):
    effr = float(fred("DFF", 1).iloc[-1])
    lo_band = math.floor(effr * 4) / 4
    rows = _meeting_probs(effr)
    if not rows:
        raise RuntimeError("ZQ futures strip unavailable")
    # Taylor rule
    cpi_idx = fred("CPIAUCSL", 3)
    cpi = float((cpi_idx.iloc[-1] / cpi_idx.iloc[-13] - 1) * 100)
    un = float(fred("UNRATE", 3).iloc[-1])
    u_star, pi_star, r_star = 4.2, 2.0, 0.5
    taylor = r_star + cpi + 0.5 * (cpi - pi_star) + 1.0 * (u_star - un)
    tgap = (taylor - effr) * 100
    t_bias = "hiking bias" if tgap > 25 else ("cutting bias" if tgap < -25 else "neutral")
    # Leg 1 summary at the final covered meeting
    last = rows[-1]
    p_cut = sum(p for k, p in last["buckets"] if k < lo_band - 1e-9) * 100
    p_hold = sum(p for k, p in last["buckets"] if abs(k - lo_band) < 1e-9) * 100
    p_hike = sum(p for k, p in last["buckets"] if k > lo_band + 1e-9) * 100
    poly = None
    try:
        poly = _polymarket_fed()
    except Exception:
        pass
    # meeting cards
    def bucket_bar(rows_):
        out = ""
        for mt in rows_:
            segs = ""
            for k, p in mt["buckets"]:
                c = RED if k < lo_band - 1e-9 else (GREEN if k > lo_band + 1e-9 else MUT)
                segs += (f'<div title="{k:.2f}–{k+0.25:.2f}%: {p*100:.1f}%" '
                         f'style="width:{p*100:.1f}%;background:{c};height:14px"></div>')
            legend = " · ".join(f'{k:.2f}–{k+0.25:.2f} <b>{p*100:.1f}%</b>' for k, p in mt["buckets"])
            out += (f'<div style="padding:8px 0;border-bottom:1px solid var(--line)">'
                    f'<div style="display:flex;justify-content:space-between;font-size:13px;flex-wrap:wrap;gap:6px">'
                    f'<span><b>{mt["label"]}</b> <span class="muted">{mt["date"]} · {mt["days"]}d</span></span>'
                    f'<span class="muted">modal {mt["modal"]:.2f}–{mt["modal"]+0.25:.2f}% @ '
                    f'<b style="color:var(--tx)">{mt["modal_p"]:.0f}%</b> · E[Δ] '
                    f'<b style="color:{GREEN if mt["edelta"]>0 else RED}">{mt["edelta"]:+.0f}bps</b></span></div>'
                    f'<div style="display:flex;border-radius:3px;overflow:hidden;margin:5px 0 3px">{segs}</div>'
                    f'<div class="muted" style="font-size:11px">{legend}</div></div>')
        return out
    body = card(
        stat_grid([("Current target range", f"{lo_band:.2f}–{lo_band+0.25:.2f}%", MUT),
                   ("Effective Fed funds", pct(effr, 2), MUT),
                   ("Next FOMC", f"{rows[0]['label']} ({rows[0]['days']}d)", GOLD),
                   ("Taylor-rule rate", pct(taylor, 2), col(tgap, lambda v: v < 0, lambda v: v > 25))]),
        "WHERE POLICY STANDS")
    # divergence callouts
    calls = []
    if poly:
        nocut = next((p for o, p in poly["rows"] if "no" in o.lower()), None)
        if nocut is not None:
            fut_nocut = 100 - p_cut
            if abs(fut_nocut - nocut) > 15:
                calls.append((AMBER, f"⚠ Futures vs Polymarket disagree by {abs(fut_nocut-nocut):.0f}pp on "
                              f'"no cuts": futures imply {fut_nocut:.0f}%, real-money prediction markets '
                              f"{nocut:.0f}%. Wide disagreements usually resolve toward the futures market — "
                              "but when they don't, the repricing is violent."))
    fut_dir = 1 if last["edelta"] > 10 else (-1 if last["edelta"] < -10 else 0)
    tay_dir = 1 if tgap > 25 else (-1 if tgap < -25 else 0)
    if fut_dir == tay_dir and fut_dir != 0:
        calls.append((GREEN, f"✓ The data and the market agree: the Taylor gap ({tgap:+.0f}bps) and the futures "
                      f"path ({last['edelta']:+.0f}bps by {last['label']}) point the same way — there is "
                      "data-backed conviction behind the priced path."))
    elif fut_dir != tay_dir:
        calls.append((AMBER, f"⚠ The data and the market disagree: the Taylor rule implies a {t_bias} "
                      f"({tgap:+.0f}bps vs the actual rate) while futures price {last['edelta']:+.0f}bps by "
                      f"{last['label']}. One of them reprices."))
    if calls:
        body += card("".join(f'<div style="color:{c};font-size:13px;padding:4px 0">{t}</div>' for c, t in calls),
                     "DIVERGENCE CHECK")
    body += "<h2>Meeting-by-meeting probabilities</h2>" + card(
        bucket_bar(rows) +
        f'<div class="legend">Computed independently from the Fed funds futures strip (ZQ contracts) using the '
        f'standard methodology: the month-average implied rate is decomposed into pre- and post-meeting rates, '
        f'then a 25bp move distribution is propagated forward across meetings. '
        f'<span style="color:{RED}">red</span> = below the current range · '
        f'<span style="color:{MUT}">grey</span> = hold · <span style="color:{GREEN}">green</span> = above.</div>')
    body += "<h2>Three independent reads on the path</h2>" + card(
        f'<div class="slabel">LEG 1 · FED FUNDS FUTURES</div>'
        f'<div style="margin:4px 0 12px">By the <b>{last["label"]}</b> meeting, futures imply: '
        f'<b style="color:{RED}">net cut {p_cut:.0f}%</b> · <b style="color:{MUT}">hold {p_hold:.0f}%</b> · '
        f'<b style="color:{GREEN}">net hike {p_hike:.0f}%</b></div>' +
        (f'<div class="slabel">LEG 2 · PREDICTION MARKETS (REAL MONEY)</div>'
         f'<div class="muted" style="font-size:12px">{poly["q"]}</div>' +
         "".join(f'<div style="display:flex;justify-content:space-between;font-size:13px;padding:2px 0">'
                 f'<span>{o}</span><b>{p:.1f}%</b></div>' for o, p in poly["rows"][:5]) + '<div style="height:12px"></div>'
         if poly else '<div class="slabel">LEG 2 · PREDICTION MARKETS</div>'
         '<div class="muted" style="font-size:12px;margin-bottom:12px">Polymarket feed unavailable this run.</div>') +
        f'<div class="slabel">LEG 3 · THE DATA (TAYLOR RULE)</div>'
        f'<div style="font-size:19px;font-weight:700;color:{col(tgap, lambda v: v < 0, lambda v: v > 25)}">'
        f'{taylor:.2f}% <span style="font-size:13px">{t_bias}</span></div>'
        f'<div class="muted" style="font-size:12px">With CPI at {cpi:.1f}% and unemployment at {un:.1f}%, a '
        f'standard Taylor rule puts the policy rate at {taylor:.2f}% versus the actual {effr:.2f}% '
        f'({tgap:+.0f}bps). ' +
        ("The data says policy is meaningfully too loose — the reaction function argues for hikes, not cuts."
         if tgap > 25 else
         "The data says policy is meaningfully too tight — the reaction function argues for cuts."
         if tgap < -25 else "The data says policy is roughly where the reaction function wants it.") + "</div>")
    body += card(
        "Most rate-path tools re-plot the CME's numbers. This one computes the probabilities independently from "
        "the futures strip, then puts that read on trial against two other crowds: prediction markets (real "
        "dollars staked on explicit outcomes) and the data itself (a Taylor-rule reaction function fed by live "
        "CPI and unemployment). When all three agree, the path is priced with conviction. When they diverge, "
        "someone is wrong — and the callouts above tell you who is likely to blink. What matters for assets is "
        "the direction of travel: easing cycles that happen WITHOUT a recession are historically the strongest "
        "equity environment there is.", "WHY THREE LEGS")
    stance = "bullish" if last["edelta"] < -15 else ("bearish" if last["edelta"] > 15 else "neutral")
    exp_txt = (f"{abs(last['edelta']):.0f}bps of {'cuts' if last['edelta'] < 0 else 'hikes'} priced by "
               f"{last['label']}" if abs(last["edelta"]) > 8 else f"no net change priced by {last['label']}")
    return dict(slug="fed-path", title="Fed Path",
                sub="Meeting-by-meeting probabilities from the futures strip, cross-examined against prediction markets and the Taylor rule.",
                body=body, stance=stance,
                headline=f"Target {lo_band:.2f}–{lo_band+0.25:.2f}% · {exp_txt}")

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
        + (f' <span class="pill" style="background:#2a2a2a;color:{MUT};font-size:10px">{tag}</span>' if tag else "")
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

def _okx(path):
    req = urllib.request.Request("https://www.okx.com" + path,
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read())
    if j.get("code") not in ("0", 0):
        raise RuntimeError(j.get("msg", "okx error"))
    return j["data"]

def _crypto_coin(ccy, spot_series):
    spot = float(spot_series.iloc[-1])
    chg7 = float((spot_series.iloc[-1] / spot_series.iloc[-8] - 1) * 100)
    out = dict(spot=spot, chg7=chg7)
    # open interest history (USD), daily
    oi = _okx(f"/api/v5/rubik/stat/contracts/open-interest-volume?ccy={ccy}&period=1D")
    oi_ser = pd.Series({pd.to_datetime(int(d[0]), unit="ms"): float(d[1]) for d in oi}).sort_index()
    out["oi_now"] = float(oi_ser.iloc[-1])
    out["oi_chg7"] = float((oi_ser.iloc[-1] / oi_ser.iloc[-8] - 1) * 100) if len(oi_ser) > 8 else 0.0
    out["oi_hist"] = oi_ser.iloc[-90:]
    # funding
    fr = _okx(f"/api/v5/public/funding-rate?instId={ccy}-USDT-SWAP")
    out["funding"] = float(fr[0]["fundingRate"]) * 100
    frh = _okx(f"/api/v5/public/funding-rate-history?instId={ccy}-USDT-SWAP&limit=100")
    out["fund_hist"] = [float(d["fundingRate"]) * 100 for d in frh][::-1]
    # long/short account ratio
    ls = _okx(f"/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={ccy}&period=1D")
    ls_ser = pd.Series({pd.to_datetime(int(d[0]), unit="ms"): float(d[1]) for d in ls}).sort_index()
    out["ls_now"] = float(ls_ser.iloc[-1])
    out["ls_hist"] = ls_ser.iloc[-90:]
    return out

def _crypto_card(name, ccy, d, px_hist):
    spot, fmtn = d["spot"], (lambda v: f"${v:,.0f}" if v > 100 else f"${v:,.2f}")
    ann = d["funding"] * 3 * 365
    # OI/price matrix verdict
    p7, o7 = d["chg7"], d["oi_chg7"]
    if abs(p7) < 1.5 and abs(o7) < 3:
        v1 = "OI and price are drifting without a decisive flow signature this week."
    elif p7 > 0 and o7 > 0:
        v1 = "Price up + OI up: new longs are funding the move — trend-supported, but crowding builds with it."
    elif p7 > 0:
        v1 = "Price up + OI down: a short-covering rally — fades unless open interest turns higher."
    elif o7 > 0:
        v1 = "Price down + OI up: new shorts pressing — trend fuel now, squeeze fuel later."
    else:
        v1 = "Price down + OI down: longs liquidating — exhaustion behavior, historically closer to lows than tops."
    v2 = (f"Funding near flat (~{ann:.1f}% ann.): the perp crowd isn't leaning hard either way."
          if abs(ann) < 15 else
          f"Funding heavily positive (~{ann:.0f}% ann.): longs crowded — squeeze risk sits below." if ann > 0 else
          f"Funding negative (~{ann:.0f}% ann.): shorts are paying to stay — squeeze risk sits above.")
    v3 = (f"Long/short accounts at {d['ls_now']:.2f}: retail positioning unremarkable."
          if 0.8 < d["ls_now"] < 2.5 else
          f"Long/short accounts at {d['ls_now']:.2f}: retail piled long — contrarian caution." if d["ls_now"] >= 2.5 else
          f"Long/short accounts at {d['ls_now']:.2f}: the crowd is net short — squeeze fuel above.")
    # charts — normalize both indexes to naive dates before aligning
    def _bydate(s):
        s = s.copy()
        idx = pd.DatetimeIndex(s.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        s.index = idx.normalize()
        return s[~s.index.duplicated(keep="last")]
    pxn = _bydate(px_hist.iloc[-120:])
    oin = _bydate(d["oi_hist"])
    oi_al, px_al = oin.align(pxn, join="inner")
    if len(px_al) < 5:
        n = min(len(oin), len(pxn))
        oi_al, px_al = oin.iloc[-n:], pxn.iloc[-n:]
    ch_oi = line_chart([(px_al / px_al.iloc[0] * 100).tolist(),
                        (oi_al / oi_al.iloc[0] * 100).tolist()], [GOLD, BLUE])
    fh = d["fund_hist"]
    ch_f = bar_chart(["" for _ in fh], fh)
    ch_ls = line_chart([d["ls_hist"].tolist()], [GOLD], hlines=[(1.0, MUT, "1.0")])
    # liquidation ladder
    tiers = [(5, 0.9), (10, 0.9), (25, 0.9), (50, 0.9), (100, 0.9)]
    shorts = [(spot * (1 + m / L), L) for L, m in tiers][::-1]
    longs = [(spot * (1 - m / L), L) for L, m in tiers]
    fmtk = lambda v: f"${v/1000:,.1f}k" if v > 2000 else f"${v:,.0f}"
    ladder = "".join(
        f'<div style="display:flex;gap:10px;font-size:12px;padding:2px 0"><span style="min-width:70px">{fmtk(p)}</span>'
        f'<span style="color:{RED}">{L}× shorts liquidate</span></div>' for p, L in shorts) + \
        f'<div style="display:flex;gap:10px;font-size:13px;padding:4px 0;border-top:1px solid var(--line);' \
        f'border-bottom:1px solid var(--line)"><b style="min-width:70px;color:{GOLD}">{fmtk(spot)}</b><b>spot</b></div>' + \
        "".join(
        f'<div style="display:flex;gap:10px;font-size:12px;padding:2px 0"><span style="min-width:70px">{fmtk(p)}</span>'
        f'<span style="color:{GREEN}">{L}× longs liquidate</span></div>' for p, L in longs)
    return card(
        f'<div style="display:flex;gap:18px;flex-wrap:wrap;align-items:baseline">'
        f'<div style="font-size:22px;font-weight:700">{fmtn(spot)} <span style="font-size:13px;color:{GREEN if d["chg7"]>=0 else RED}">{d["chg7"]:+.1f}% 7d</span></div>'
        f'<div>OI (OKX) <b>${d["oi_now"]/1e9:,.2f}B</b> <span style="color:{GREEN if o7>=0 else RED}">{o7:+.1f}% 7d</span></div>'
        f'<div>Funding <b>{d["funding"]:+.4f}%/8h</b> <span class="muted">(~{ann:.1f}% ann.)</span></div>'
        f'<div>Long/short accounts <b>{d["ls_now"]:.2f}</b></div></div>'
        + "".join(f'<div style="margin-top:6px;font-size:13px">▸ {v}</div>' for v in (v1, v2, v3))
        + f'<div class="slabel" style="margin-top:12px">OPEN INTEREST vs PRICE · 90D</div>{ch_oi}'
        f'<div class="legend"><span style="color:{GOLD}">▬</span> price · <span style="color:{BLUE}">▬</span> OI, both indexed</div>'
        f'<div class="slabel" style="margin-top:12px">FUNDING RATE HISTORY · 8H PRINTS</div>{ch_f}'
        f'<div class="slabel" style="margin-top:12px">LONG/SHORT ACCOUNT RATIO · 90D</div>{ch_ls}'
        '<div class="legend">Accounts long per account short. Spikes = retail piling long (contrarian '
        'caution); below 1 = the crowd is net short.</div>'
        f'<div class="slabel" style="margin-top:12px">ESTIMATED LIQUIDATION LADDER</div>{ladder}'
        '<div class="legend">Where leverage opened at the current price would be forced out, by tier. An '
        'estimate of the magnet zones: price gravitates to dense liquidation clusters because forced closes '
        'provide the liquidity for the next move.</div>', name.upper())

def m_crypto(px):
    btc = px["BTC-USD"].dropna(); eth = px["ETH-USD"].dropna()
    body = ""
    ok = 0
    for name, ccy, ser in (("Bitcoin", "BTC", btc), ("Ethereum", "ETH", eth)):
        try:
            body += _crypto_card(name, ccy, _crypto_coin(ccy, ser), ser)
            ok += 1
        except Exception as e:
            body += card(f'<span class="muted">{name} derivatives data unavailable this run ({e}).</span>',
                         name.upper())
    corr = px["BTC-USD"].pct_change().iloc[-63:].corr(px["QQQ"].pct_change().iloc[-63:])
    ratio = (eth / btc).dropna()
    r3m = float((ratio.iloc[-1] / ratio.iloc[-64] - 1) * 100)
    a200 = bool(btc.iloc[-1] > btc.rolling(200).mean().iloc[-1])
    body += card(
        "<ul class='pb'>"
        "<li><b>The OI/price matrix is the core read</b> — price and open interest rising together is a "
        "supported trend; price down with OI up is shorts pressing (and future squeeze fuel); price down "
        "with OI down is long liquidation, the exhaustion signature that clusters near lows; price up with "
        "OI down is short-covering, suspect until OI turns.</li>"
        "<li><b>Funding is the crowd's temperature</b> — what leveraged traders pay to keep their bias. "
        "Persistently positive = crowded longs, squeezes hit below; negative = crowded shorts, squeezes hit "
        "above. The history bars separate a regime from a blip.</li>"
        "<li><b>The ladder is the map of forced flow</b> — the nearest dense band below spot is the magnet "
        "in a flush; the nearest above is the target in a squeeze.</li></ul>"
        f"<div style='margin-top:8px'>Context: BTC is <b style='color:{GREEN if a200 else RED}'>"
        f"{'above' if a200 else 'below'}</b> its 200-day (the cycle line), ETH/BTC {r3m:+.1f}% over 3 months "
        f"(alt risk appetite), BTC–Nasdaq correlation {corr:+.2f} (how much crypto is just high-beta tech "
        "right now). Spot price says what happened; these flows say who is positioned for what happens next.</div>",
        "HOW TO READ THE FLOWS")
    return dict(slug="crypto", title="Crypto Flows",
                sub="Derivatives positioning for the majors — open interest, funding, the retail ratio, and the liquidation map.",
                body=body, stance="bullish" if a200 else "bearish",
                headline=f"BTC {'above' if a200 else 'below'} its 200-day" +
                         (" · OKX flows loaded" if ok else " · derivatives feed down"))

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
const R=__ROWS__,GRN='#4caf7d',RED='#e05555',GOLDC='#d4af37',MUT='#606060';
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
   (k===cat?GOLDC:'#2a2a2a')+';background:'+(k===cat?'rgba(212,175,90,.12)':'transparent')+';color:'+(k===cat?GOLDC:MUT)+'">'+l+'</button>').join('')+'</div>';
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
   '<td style="font-weight:600;color:'+(r.idx==null?MUT:(r.idx>=80||r.idx<=20?GOLDC:'#ffffff'))+'">'+(r.idx==null?'—':r.idx)+'</td>'+
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

# JPL approximate orbital elements (Standish), valid ~1800–2050.
# a(AU), e, I(deg), L(deg), longPeri(deg), longNode(deg) at J2000 + per-century rates
PLANETS = {
    "Mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081), "☿", 2),
    "Venus":   ((0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
                (0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418), "♀", 2),
    "Mars":    ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
                (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343), "♂", 3),
    "Jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106), "♃", 4),
    "Saturn":  ((9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
                (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794), "♄", 4),
    "Uranus":  ((19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503),
                (-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589), "♅", 5),
    "Neptune": ((30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574),
                (0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664), "♆", 5),
    "Pluto":   ((39.48211675, 0.24882730, 17.14001206, 238.92903833, 224.06891629, 110.30393684),
                (-0.00031596, 0.00005170, 0.00004818, 145.20780515, -0.04062942, -0.01183482), "♇", 5),
}
EARTH = ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
         (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0))
ASPECTS = [("conjunction", 0, 8), ("sextile", 60, 4), ("square", 90, 6),
           ("trine", 120, 6), ("opposition", 180, 8)]

def _jd(dt):
    return dt.toordinal() + 1721424.5 + (dt.hour * 3600 + dt.minute * 60) / 86400

def _helio_xyz(el, rates, T):
    a, e, I, L, wbar, Om = (el[i] + rates[i] * T for i in range(6))
    w = wbar - Om
    M = math.radians((L - wbar + 180) % 360 - 180)
    E = M
    for _ in range(8):
        E -= (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
    xp = a * (math.cos(E) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(E)
    w, I, Om = map(math.radians, (w, I, Om))
    x = (math.cos(w) * math.cos(Om) - math.sin(w) * math.sin(Om) * math.cos(I)) * xp + \
        (-math.sin(w) * math.cos(Om) - math.cos(w) * math.sin(Om) * math.cos(I)) * yp
    y = (math.cos(w) * math.sin(Om) + math.sin(w) * math.cos(Om) * math.cos(I)) * xp + \
        (-math.sin(w) * math.sin(Om) + math.cos(w) * math.cos(Om) * math.cos(I)) * yp
    z = (math.sin(w) * math.sin(I)) * xp + (math.cos(w) * math.sin(I)) * yp
    return x, y, z

def _geo_lons(dt):
    """Geocentric ecliptic longitudes (deg) for Sun, Moon and the planets."""
    T = (_jd(dt) - 2451545.0) / 36525
    ex, ey, ez = _helio_xyz(*EARTH, T)
    out = {"Sun": math.degrees(math.atan2(-ey, -ex)) % 360}
    for name, (el, rates, _sym, _w) in PLANETS.items():
        x, y, z = _helio_xyz(el, rates, T)
        out[name] = math.degrees(math.atan2(y - ey, x - ex)) % 360
    # Moon: abridged lunar theory (main periodic terms), ~0.3 deg accuracy
    d = _jd(dt) - 2451545.0
    Lm = (218.316 + 13.176396 * d) % 360
    Mm = math.radians((134.963 + 13.064993 * d) % 360)
    Ms = math.radians((357.529 + 0.98560028 * d) % 360)
    D = math.radians((297.850 + 12.190749 * d) % 360)
    F = math.radians((93.272 + 13.229350 * d) % 360)
    lon = (Lm + 6.289 * math.sin(Mm) - 1.274 * math.sin(Mm - 2 * D) - 0.658 * math.sin(2 * D)
           - 0.214 * math.sin(2 * Mm) - 0.186 * math.sin(Ms) - 0.114 * math.sin(2 * F))
    out["Moon"] = lon % 360
    return out

def _sep(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)

def _astro_events(start, days=372):
    """Scan the sky day by day: aspects, retrogrades, moon phases."""
    lons = {}
    for k in range(-2, days + 2):
        dt = start + timedelta(days=k)
        lons[k] = _geo_lons(dt)
    names = list(PLANETS)
    weight = {n: PLANETS[n][3] for n in names}
    weight.update({"Sun": 3, "Moon": 1})
    events = []
    # --- aspects (planet-planet and Sun-planet)
    pairs = [(a, b) for i, a in enumerate(["Sun"] + names) for b in (["Sun"] + names)[i + 1:]]
    for a, b in pairs:
        for aname, angle, orb in ASPECTS:
            active, best, bestk = None, 999, None
            for k in range(0, days):
                dev = abs(_sep(lons[k][a], lons[k][b]) - angle)
                if dev <= orb:
                    if active is None:
                        active, best, bestk = k, dev, k
                    elif dev < best:
                        best, bestk = dev, k
                elif active is not None:
                    sig = min(5, round((weight[a] + weight[b]) / 2))
                    events.append(dict(kind="aspect", a=a, b=b, asp=aname,
                                       start=active, end=k - 1, peak=bestk, sig=sig))
                    active = None
            if active is not None:
                sig = min(5, round((weight[a] + weight[b]) / 2))
                events.append(dict(kind="aspect", a=a, b=b, asp=aname,
                                   start=active, end=days - 1, peak=bestk, sig=sig))
    # --- retrogrades
    for n in names:
        active = None
        for k in range(0, days):
            dlon = ((lons[k][n] - lons[k - 1][n] + 180) % 360) - 180
            retro = dlon < 0
            if retro and active is None:
                active = k
            elif not retro and active is not None:
                events.append(dict(kind="retro", a=n, b=None, asp="retrograde",
                                   start=active, end=k - 1, peak=(active + k - 1) // 2,
                                   sig=min(5, weight[n])))
                active = None
        if active is not None:
            events.append(dict(kind="retro", a=n, b=None, asp="retrograde",
                               start=active, end=days - 1, peak=(active + days - 1) // 2,
                               sig=min(5, weight[n])))
    # --- moon phases
    phase_names = {0: ("New moon", 2), 90: ("First-quarter moon", 1),
                   180: ("Full moon", 2), 270: ("Last-quarter moon", 1)}
    for target, (pname, sig) in phase_names.items():
        for k in range(1, days):
            e0 = (lons[k - 1]["Moon"] - lons[k - 1]["Sun"]) % 360
            e1 = (lons[k]["Moon"] - lons[k]["Sun"]) % 360
            crossed = (e0 < target <= e1) or (target == 0 and e1 < e0)
            if crossed:
                events.append(dict(kind="phase", a="Moon", b="Sun", asp=pname,
                                   start=k - 2, end=k + 2, peak=k, sig=sig))
    return events

def _moon_backtest(gspc_d):
    """Measure whether the lunar cycle actually shows up in returns."""
    r = gspc_d.pct_change().dropna() * 100
    r = r[r.index.year >= 1990]
    rows = []
    ages = pd.Series([(_geo_lons(d.to_pydatetime().replace(tzinfo=timezone.utc))["Moon"] -
                       _geo_lons(d.to_pydatetime().replace(tzinfo=timezone.utc))["Sun"]) % 360
                      for d in r.index], index=r.index)
    for lab, mask in (("Around the new moon (±3d)", (ages < 37) | (ages > 323)),
                      ("Around the full moon (±3d)", (ages > 143) & (ages < 217)),
                      ("Everything else", ~(((ages < 37) | (ages > 323)) |
                                            ((ages > 143) & (ages < 217))))):
        g = r[mask]
        rows.append((lab, float(g.mean()), float((g > 0).mean() * 100), len(g)))
    return rows

def m_astrology():
    start = datetime(NOW.year, NOW.month, NOW.day, 12, tzinfo=timezone.utc)
    events = _astro_events(start)
    now_l = _geo_lons(NOW)
    elong = (now_l["Moon"] - now_l["Sun"]) % 360
    illum = (1 - math.cos(math.radians(elong))) / 2 * 100
    pnames = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
              "Full moon", "Waning gibbous", "Last quarter", "Waning crescent"]
    phase = pnames[int((elong / 45 + 0.5) % 8)]
    retro_now = [e["a"] for e in events if e["kind"] == "retro" and e["start"] <= 0 <= e["end"]]
    def dstr(k):
        return (start + timedelta(days=k)).strftime("%Y-%m-%d")
    def sym(n):
        return {"Sun": "☉", "Moon": "☽"}.get(n) or PLANETS[n][2]
    events.sort(key=lambda e: (e["start"], -e["sig"]))
    upcoming = [e for e in events if e["end"] >= 0][:60]
    live_now = sum(1 for e in events if e["start"] <= 0 <= e["end"])
    rows = []
    for e in upcoming:
        if e["kind"] == "retro":
            title = f"{e['a']} retrograde"
            syms = sym(e["a"])
        elif e["kind"] == "phase":
            title = e["asp"]
            syms = "☽ ☉"
        else:
            title = f"{e['a']} {e['asp']} {e['b']}"
            syms = f"{sym(e['a'])} {sym(e['b'])}"
        if e["start"] <= 0 <= e["end"]:
            status, scol = "Happening now", GOLD
        elif 0 < e["start"] <= 14:
            status, scol = "Starting soon", BLUE
        elif e["end"] <= 10:
            status, scol = "Ending soon", MUT
        else:
            status, scol = "Upcoming", MUT
        stars = "★" * e["sig"] + "☆" * (5 - e["sig"])
        rows.append(
            f'<tr data-sig="{e["sig"]}"><td><span style="color:{scol};font-size:11px">{status}</span></td>'
            f'<td><span style="color:{GOLD};letter-spacing:1px">{stars}</span></td>'
            f'<td style="font-size:15px">{syms}</td>'
            f'<td><b>{title}</b></td>'
            f'<td class="muted" style="font-size:11px;white-space:nowrap">{dstr(max(e["start"],0))} → '
            f'{dstr(e["end"])}<br>peak {dstr(e["peak"])}</td></tr>')
    filt = ("<div style='margin-bottom:8px'>Minimum significance: " + "".join(
        f'<button onclick="afilt({s})" id="ab{s}" style="cursor:pointer;font-size:11px;padding:3px 9px;'
        f'border-radius:12px;border:1px solid #2a2a2a;background:transparent;color:#606060;margin-right:4px">'
        + "★" * s + "</button>" for s in range(1, 6)) + "</div>")
    js = ("<script>function afilt(s){document.querySelectorAll('#astbl tr[data-sig]').forEach(r=>"
          "{r.style.display=(+r.dataset.sig>=s)?'':'none'});"
          "[1,2,3,4,5].forEach(i=>{const b=document.getElementById('ab'+i);"
          "b.style.color=i===s?'#d4af37':'#606060';b.style.borderColor=i===s?'#d4af37':'#2a2a2a';});}"
          "afilt(1);</script>")
    body = card(stat_grid([("Moon phase", phase, GOLD),
                           ("Illumination", pct(illum, 0), MUT),
                           ("Retrograde now", ", ".join(retro_now) if retro_now else "none",
                            RED if retro_now else GREEN),
                           ("Live events", f"{live_now}", GOLD),
                           ("Events in window", f"{len(events)}", MUT)]) +
                f'<div class="muted" style="margin-top:8px;font-size:12px">Positions computed from Keplerian '
                f'orbital elements (JPL approximation) for the window {dstr(0)} → {dstr(371)}. Aspects use '
                'standard orbs; significance weights the slower, "heavier" bodies higher.</div>',
                "SKY DASHBOARD")
    body += "<h2>Events</h2>" + card(
        filt + f'<div style="overflow-x:auto"><table id="astbl">{"".join(rows)}</table></div>' + js +
        '<div class="legend">Aspects are angular relationships between two bodies (conjunction 0°, sextile 60°, '
        'square 90°, trine 120°, opposition 180°) within an orb of tolerance. Retrogrades are apparent backward '
        'motion, detected here from the sign of each body\'s daily change in geocentric longitude.</div>')
    try:
        bt = _moon_backtest(yf.download("^GSPC", period="max", interval="1d", auto_adjust=True,
                                        progress=False)["Close"].squeeze().dropna())
        body += "<h2>Does any of it work? The measured answer</h2>" + card(
            table(["Window", "Avg daily return", "% positive", "n"],
                  [(f"<b>{l}</b>", cnum(a, 3), f"{w:.1f}%", f"{n:,}") for l, a, w, n in bt]) +
            '<div class="legend">S&P 500 daily returns since 1990, grouped by lunar phase, computed from the '
            'same ephemeris driving the table above. The differences are a rounding error on transaction costs. '
            'This is the honest result, and it is the point of the section.</div>')
    except Exception:
        pass
    body += card(
        "This page is here because traders talk about it, not because it trades. The ephemeris is real — the "
        "positions, aspects and retrogrades are computed from orbital mechanics, not looked up in a magazine. "
        "The market claims attached to them are not: the lunar effect that survives in the academic literature "
        "is tiny and vanishes after costs, and Mercury retrograde has never survived a serious backtest. The "
        "measured table above uses this page's own numbers to make that case rather than asking you to take it "
        "on faith. Enjoy it as sky-watching; put your risk on the other twenty tabs.",
        "READ THIS BEFORE YOU TRADE IT")
    return dict(slug="astrology", title="Market Astrology",
                sub="A real computed ephemeris — aspects, retrogrades, lunar phases — and an honest measurement of whether any of it matters.",
                body=body, stance="info",
                headline=f"{phase} · {live_now} events live · " +
                         (f"{', '.join(retro_now[:2])} retrograde" if retro_now else "no retrogrades"))

THEMES = {
    "SKYY": ("Cloud computing", "SaaS and cloud infrastructure"),
    "IBB": ("Biotech (large)", "Large-cap biotech"),
    "ARKG": ("Genomics", "Genomic medicine"),
    "CIBR": ("Cybersecurity", "Cyber pure-play"),
    "KWEB": ("China internet", "China tech platforms"),
    "IHI": ("Medical devices", "Med-tech"),
    "XOP": ("Oil & gas E&P", "Smid-cap producers"),
    "IAI": ("Brokers & exchanges", "Capital markets"),
    "SMH": ("Semiconductors", "Chip designers and fabs"),
    "TAN": ("Solar", "Solar pure-play"),
    "LIT": ("Lithium & battery", "Battery supply chain"),
    "COPX": ("Copper miners", "Copper producers"),
    "REMX": ("Rare earths", "Strategic metals"),
    "URA": ("Uranium", "Nuclear fuel cycle"),
    "JETS": ("Airlines", "Global carriers"),
    "XHB": ("Homebuilders", "US housing"),
    "ITA": ("Defense", "Aerospace and defense"),
    "GDX": ("Gold miners", "Senior gold producers"),
    "BOTZ": ("Robotics & AI", "Automation and AI hardware"),
    "FINX": ("Fintech", "Financial technology"),
    "HACK": ("Cyber (equal-wt)", "Cybersecurity, equal weight"),
    "MOO": ("Agribusiness", "Agriculture value chain"),
    "PAVE": ("Infrastructure", "US infrastructure build-out"),
    "XBI": ("Biotech (equal-wt)", "Smid-cap biotech"),
}
CYCLE_LEADERS = {"Early": ["XLY", "XLF", "XLRE", "XLI"], "Mid": ["XLK", "XLI", "XLC"],
                 "Late": ["XLE", "XLB", "XLP", "XLV"], "Recession": ["XLP", "XLU", "XLV"]}

def m_screener(px):
    # --- master gauges (four independent risk reads)
    spy = px["SPY"].dropna()
    g_trend = bool(spy.iloc[-1] > spy.rolling(200).mean().iloc[-1])
    panel_cols = [t for t in PANEL if t in px.columns and px[t].dropna().shape[0] > 260]
    panel = px[panel_cols]
    a50 = float((panel.iloc[-1] > panel.rolling(50).mean().iloc[-1]).sum()) / len(panel_cols) * 100
    g_breadth = a50 >= 50
    g_credit = bool((px["HYG"] / px["IEF"]).dropna().iloc[-1] >
                    (px["HYG"] / px["IEF"]).dropna().rolling(50).mean().iloc[-1])
    g_vol = bool(px["^VIX"].dropna().iloc[-1] < 20)
    gauges = [("Index trend", g_trend, "SPY vs its 200-day"),
              ("Breadth", g_breadth, f"{a50:.0f}% of the panel above its 50-day"),
              ("Credit appetite", g_credit, "HYG/IEF vs its 50-day"),
              ("Volatility", g_vol, f"VIX {float(px['^VIX'].dropna().iloc[-1]):.1f}")]
    n_bull = sum(g for _, g, _ in gauges)
    if n_bull >= 3:
        regime, rcol = "Risk-on", GREEN
        rnote = ("Capital is leaning into risk. Trend, participation and credit agree — this is the regime "
                 "where breakouts work and dips get bought.")
    elif n_bull <= 1:
        regime, rcol = "Defense", RED
        rnote = ("The gauges have turned. Preservation beats participation here: reduce size, raise cash, and "
                 "wait for at least two gauges to flip back before re-engaging.")
    else:
        regime, rcol = "Mixed — trim", AMBER
        rnote = ("The gauges disagree. Half-size, tighter stops, and let the tape resolve. Mixed regimes are "
                 "where over-trading destroys accounts.")
    gauge_html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:10px">' + \
        "".join(f'<div><div class="slabel">{n}</div>'
                f'<div class="sval" style="color:{GREEN if g else RED}">{"BULLISH" if g else "BEARISH"}</div>'
                f'<div class="muted" style="font-size:11px">{d}</div></div>' for n, g, d in gauges) + "</div>"
    # --- cycle overlay
    try:
        infl = float((fred("CPIAUCSL", 3).pct_change(12).dropna().iloc[-1]) * 100)
        ipy = float((fred("INDPRO", 3).pct_change(12).dropna().iloc[-1]) * 100)
        phase = "Late" if infl > 3 and ipy > 0 else ("Mid" if ipy > 1 else "Early")
    except Exception:
        phase = "Mid"
    expected = CYCLE_LEADERS[phase]
    # --- sector leaders
    sec_rows = []
    for etf, name in SECTORS.items():
        s = px[etf].dropna()
        rs3 = float(((s.iloc[-1] / s.iloc[-64]) / (spy.iloc[-1] / spy.iloc[-64]) - 1) * 100)
        above20 = bool(s.iloc[-1] > s.rolling(20).mean().iloc[-1])
        star = "★" if etf in expected else ""
        sec_rows.append((etf, name, rs3, above20, star))
    sec_rows.sort(key=lambda r: -r[2])
    actual_top = [r[0] for r in sec_rows[:3]]
    diverge = not set(actual_top) & set(expected)
    # --- themes (auto-ranked, no hardcoded favourite)
    tsyms = [t for t in THEMES]
    th = yf.download(tsyms, period="1y", interval="1d", auto_adjust=True,
                     progress=False)["Close"].ffill(limit=3)
    trows = []
    for t, (name, note) in THEMES.items():
        if t not in th.columns:
            continue
        s = th[t].dropna()
        if len(s) < 60:
            continue
        ratio = (s / spy.reindex(s.index).ffill()).dropna()
        v20 = float((ratio.iloc[-1] / ratio.rolling(20).mean().iloc[-1] - 1) * 100)
        v50 = float((ratio.iloc[-1] / ratio.rolling(50).mean().iloc[-1] - 1) * 100)
        state = ("BULLISH", GREEN) if v20 > 0 and v50 > 0 else \
                (("BEARISH", RED) if v20 < 0 and v50 < 0 else ("MIXED", AMBER))
        trows.append((t, name, note, v20, v50, state))
    trows.sort(key=lambda r: -r[3])
    def theme_tbl(rs):
        return table(["Pair", "Theme", "vs 20d", "vs 50d", "State"],
                     [(f"<b>{t}/SPY</b>", f"{n}<div class='muted' style='font-size:11px'>{nt}</div>",
                       cnum(a, 2), cnum(b, 2),
                       f'<span style="color:{st[1]};font-weight:600">{st[0]}</span>')
                      for t, n, nt, a, b, st in rs])
    # --- stock table
    rows = []
    for t in panel_cols:
        s = px[t].dropna()
        s20 = float(s.rolling(20).mean().iloc[-1])
        s50 = float(s.rolling(50).mean().iloc[-1]); s200 = float(s.rolling(200).mean().iloc[-1])
        r1, r3 = float((s.iloc[-1] / s.iloc[-22] - 1) * 100), float((s.iloc[-1] / s.iloc[-64] - 1) * 100)
        rs = r3 - float((spy.iloc[-1] / spy.iloc[-64] - 1) * 100)
        rows.append((t, SECTORS[PANEL[t]], float(s.iloc[-1]), float((s.iloc[-1] / s20 - 1) * 100),
                     float((s.iloc[-1] / s50 - 1) * 100), float((s.iloc[-1] / s200 - 1) * 100), r1, r3, rs))
    rows.sort(key=lambda r: -r[8])
    trs = "\n".join(
        f"<tr><td><b>{t}</b></td><td class='muted'>{sec}</td><td>{p:,.2f}</td>"
        + "".join(f"<td style='color:{GREEN if v>0 else RED}'>{v:+.1f}%</td>" for v in (a, b, c, d, e, f))
        + "</tr>" for t, sec, p, a, b, c, d, e, f in rows)
    green_sectors = [r[0] for r in sec_rows if r[2] > 0 and r[3]]
    ideas = [r for r in rows if r[3] > 0 and PANEL[r[0]] in green_sectors][:10]
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{rcol}">{regime} · {n_bull}/4 gauges bullish</div>'
        f'<div class="muted" style="margin-top:3px">{rnote}</div>' + gauge_html, "MASTER GAUGES")
    body += "<h2>Sector leadership vs the cycle</h2>" + card(
        table(["Sector", "RS vs SPY (3m)", "Above 20d", "Cycle-expected"],
              [(f"<b>{e}</b> <span class='muted'>{n}</span>", cnum(r, 1), dot(a),
                f'<span style="color:{GOLD}">{st}</span>' if st else '<span class="muted">—</span>')
               for e, n, r, a, st in sec_rows]) +
        f'<div class="legend">★ marks the sectors that historically lead in a <b>{phase}</b>-cycle economy. '
        + ("Actual leadership DIVERGES from what the cycle expects — either the cycle classifier is early or "
           "the market is discounting a phase change. Extra caution is warranted either way."
           if diverge else
           "Actual leadership agrees with the cycle read, which raises confidence in both.") + "</div>")
    body += "<h2>Themes — leading</h2>" + card(
        theme_tbl(trows[:10]) +
        '<div class="legend">Every theme measured as its own ratio against SPY, ranked by distance above its '
        '20-day. Nothing here is hardcoded as "the story" — when one theme drops out of the top ten and '
        'another enters, that rotation IS the signal.</div>')
    body += "<h2>Themes — fading</h2>" + card(theme_tbl(trows[-5:][::-1]) +
        '<div class="legend">The weakest of the same universe: these are objectively losing capital versus '
        'the index. Avoid the temptation to call them cheap.</div>')
    if ideas:
        body += "<h2>Drill-down: names with regime and momentum</h2>" + card(
            table(["Ticker", "Sector", "vs 20d", "RS vs SPY (3m)"],
                  [(f"<b>{r[0]}</b>", f"<span class='muted'>{r[1]}</span>", cnum(r[3], 1), cnum(r[8], 1))
                   for r in ideas]) +
            '<div class="legend">Constituents of the leading sectors that are also above their own 20-day — '
            'both the regime and the name are working. A close back under the 20-day is the natural '
            'invalidation.</div>')
    body += "<h2>The full panel</h2>" + card(
        '<div class="muted" style="margin-bottom:8px">Click any header to re-sort.</div>'
        f"<div style='overflow-x:auto'><table id='scr'><tr>"
        "<th onclick='so(0,0)'>Ticker</th><th onclick='so(1,0)'>Sector</th><th onclick='so(2,1)'>Price</th>"
        "<th onclick='so(3,1)'>vs 20d</th><th onclick='so(4,1)'>vs 50d</th><th onclick='so(5,1)'>vs 200d</th>"
        f"<th onclick='so(6,1)'>1m</th><th onclick='so(7,1)'>3m</th>"
        f"<th onclick='so(8,1)'>RS vs SPY</th></tr>{trs}</table></div>"
        "<script>function so(i,num){const t=document.getElementById('scr');"
        "const r=[...t.rows].slice(1);const d=t.dataset['s'+i]!=='1';t.dataset['s'+i]=d?'1':'0';"
        "r.sort((a,b)=>{let x=a.cells[i].innerText.replace(/[,%+]/g,''),y=b.cells[i].innerText.replace(/[,%+]/g,'');"
        "return num?(d?y-x:x-y):(d?x.localeCompare(y):y.localeCompare(x));});"
        "r.forEach(x=>t.appendChild(x));}</script>")
    return dict(slug="screener", title="Screener",
                sub="Master risk gauges, sector leadership against the cycle, auto-ranked themes, and the full sortable panel.",
                body=body, stance="info",
                headline=f"{regime} ({n_bull}/4) · leading themes: {', '.join(r[1] for r in trows[:2])}")

def m_calculators():
    out_style = 'style="margin-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px"'
    body = card(
        '<div class="muted" style="font-size:12px;margin-bottom:6px">Risk a fixed percentage of the account '
        'per trade. The stop distance sets the size — never the other way round.</div>'
        '<label class="cl">Account $<br><input class="calc" id="c_acct" value="100000"></label>'
        '<label class="cl">Risk %<br><input class="calc" id="c_risk" value="1"></label>'
        '<label class="cl">Entry<br><input class="calc" id="c_in" value="100"></label>'
        '<label class="cl">Stop<br><input class="calc" id="c_st" value="96"></label>'
        f'<div id="c_out" {out_style}></div>'
        "<script>function cc(){const a=+c_acct.value,r=+c_risk.value/100,e=+c_in.value,s=+c_st.value;"
        "const rp=Math.abs(e-s);const o=document.getElementById('c_out');"
        "if(!a||!r||!rp){o.innerHTML='<span class=muted>—</span>';return}"
        "const sh=Math.floor(a*r/rp),risk=a*r,notional=sh*e;"
        "const cell=(l,v,c)=>`<div><div class=slabel>${l}</div><div class=sval style='color:${c||'#ffffff'}'>${v}</div></div>`;"
        "o.innerHTML=cell('Risk amount','$'+risk.toLocaleString(undefined,{maximumFractionDigits:2}),'#e05555')"
        "+cell('Position size',sh.toLocaleString()+' units')"
        "+cell('Notional exposure','$'+notional.toLocaleString(undefined,{maximumFractionDigits:0}))"
        "+cell('1R (per unit)',rp.toFixed(2))"
        "+cell('Exposure / account',(notional/a*100).toFixed(1)+'%',notional>a?'#e05555':'#606060');}"
        "['c_acct','c_risk','c_in','c_st'].forEach(i=>document.getElementById(i).addEventListener('input',cc));cc();</script>",
        "POSITION SIZE") + card(
        '<div class="muted" style="font-size:12px;margin-bottom:6px">The reward:risk ratio and the hit rate it '
        'requires just to break even, before costs.</div>'
        '<label class="cl">Entry<br><input class="calc" id="r_in" value="100"></label>'
        '<label class="cl">Stop<br><input class="calc" id="r_st" value="96"></label>'
        '<label class="cl">Target<br><input class="calc" id="r_tg" value="112"></label>'
        f'<div id="r_out" {out_style}></div>'
        "<script>function rc(){const e=+r_in.value,s=+r_st.value,t=+r_tg.value;"
        "const risk=Math.abs(e-s),rew=Math.abs(t-e);const o=document.getElementById('r_out');"
        "if(!risk){o.innerHTML='<span class=muted>—</span>';return}"
        "const rr=rew/risk,be=1/(1+rr)*100;"
        "const cell=(l,v,c)=>`<div><div class=slabel>${l}</div><div class=sval style='color:${c||'#ffffff'}'>${v}</div></div>`;"
        "o.innerHTML=cell('Reward : Risk',rr.toFixed(2)+' R',rr>=2?'#4caf7d':(rr<1?'#e05555':'#e0a94c'))"
        "+cell('Break-even win rate',be.toFixed(1)+'%')"
        "+cell('Risk per unit',risk.toFixed(2))+cell('Reward per unit',rew.toFixed(2));}"
        "['r_in','r_st','r_tg'].forEach(i=>document.getElementById(i).addEventListener('input',rc));rc();</script>",
        "RISK / REWARD") + card(
        '<div class="muted" style="font-size:12px;margin-bottom:6px">Positive expectancy plus surviving the '
        'variance is the whole game. Everything else is decoration.</div>'
        '<label class="cl">Win rate %<br><input class="calc" id="e_wr" value="45"></label>'
        '<label class="cl">Avg win (R)<br><input class="calc" id="e_w" value="2"></label>'
        '<label class="cl">Avg loss (R)<br><input class="calc" id="e_l" value="1"></label>'
        f'<div id="e_out" {out_style}></div>'
        "<script>function ec(){const w=+e_wr.value/100,aw=+e_w.value,al=+e_l.value;"
        "const ex=w*aw-(1-w)*al;const o=document.getElementById('e_out');"
        "const kel=al?((w*aw-(1-w)*al)/aw):0;"
        "const cell=(l,v,c)=>`<div><div class=slabel>${l}</div><div class=sval style='color:${c||'#ffffff'}'>${v}</div></div>`;"
        "o.innerHTML=cell('Expectancy',ex.toFixed(2)+'R / trade',ex>0?'#4caf7d':'#e05555')"
        "+cell('Over 100 trades',(ex*100).toFixed(0)+'R',ex>0?'#4caf7d':'#e05555')"
        "+cell('Kelly fraction',(kel*100).toFixed(1)+'%','#606060')"
        "+cell('Half-Kelly (practical)',(kel*50).toFixed(1)+'%','#606060');}"
        "['e_wr','e_w','e_l'].forEach(i=>document.getElementById(i).addEventListener('input',ec));ec();</script>",
        "R-MULTIPLE EXPECTANCY") + card(
        '<div class="muted" style="font-size:12px;margin-bottom:6px">Growth at a fixed rate per period, and '
        'what a drawdown costs you in the same currency.</div>'
        '<label class="cl">Start $<br><input class="calc" id="k_p" value="100000"></label>'
        '<label class="cl">Return %/period<br><input class="calc" id="k_r" value="15"></label>'
        '<label class="cl">Periods<br><input class="calc" id="k_y" value="10"></label>'
        '<label class="cl">Drawdown %<br><input class="calc" id="k_d" value="20"></label>'
        f'<div id="k_out" {out_style}></div>'
        "<script>function kc(){const p=+k_p.value,r=+k_r.value/100,y=+k_y.value,d=+k_d.value/100;"
        "const end=p*Math.pow(1+r,y);const o=document.getElementById('k_out');"
        "const recov=d<1?(1/(1-d)-1)*100:Infinity;"
        "const cell=(l,v,c)=>`<div><div class=slabel>${l}</div><div class=sval style='color:${c||'#ffffff'}'>${v}</div></div>`;"
        "o.innerHTML=cell('Ending value','$'+end.toLocaleString(undefined,{maximumFractionDigits:0}),'#4caf7d')"
        "+cell('Total gain','$'+(end-p).toLocaleString(undefined,{maximumFractionDigits:0}))"
        "+cell('Multiple',(end/p).toFixed(2)+'×')"
        "+cell('Gain needed to recover',(isFinite(recov)?recov.toFixed(1)+'%':'∞'),'#e05555');}"
        "['k_p','k_r','k_y','k_d'].forEach(i=>document.getElementById(i).addEventListener('input',kc));kc();</script>",
        "COMPOUNDING & DRAWDOWN MATH") + card(
        "Tools for planning, not advice. Position sizing assumes a fixed percentage of the account risked per "
        "trade. The break-even win rate is the hit rate a given reward:risk needs just to stop losing money — "
        "before commissions, slippage and taxes, all of which move it against you. Kelly is shown because it's "
        "the mathematically optimal growth fraction, and half-Kelly is shown because full Kelly's drawdowns are "
        "unlivable for actual humans. Note the last cell above: a 20% drawdown needs a 25% gain to recover, and "
        "a 50% drawdown needs 100%. That asymmetry is why risk management outranks entry selection.",
        "THE ARITHMETIC THAT DECIDES SURVIVAL")
    return dict(slug="calculators", title="Calculators",
                sub="Position sizing, reward:risk with break-even hit rates, expectancy, Kelly, and drawdown math.",
                body=body, stance="info",
                headline="Position size · risk/reward · expectancy · compounding")

GLOSSARY = {
    "Breadth": [
        ("A/D line", "Cumulative advancers minus decliners. The breadth backbone: index highs the A/D line refuses to confirm are suspect."),
        ("Breadth thrust", "A violent expansion in participation off a low. Rare, and historically one of the most reliable bullish signals there is."),
        ("McClellan oscillator", "EMA19 − EMA39 of ratio-adjusted net advances — the momentum of breadth. Extremes and thrusts carry the signal, not the daily wiggle."),
        ("Zweig breadth thrust", "10-day EMA of advances ÷ (advances + declines). Armed below 0.40, fires at 0.615 or higher within ten sessions."),
        ("% above 50-day", "Share of a panel in short-term uptrends. A mean-reverting oscillator with teeth only at the edges: above 80 or below 20."),
    ],
    "Volatility & options": [
        ("Term structure (vol)", "Near-dated implied vol against far-dated. Upward slope (contango) is normal; inversion is the cleanest regime-break signal in the vol space."),
        ("Variance risk premium", "Implied vol minus subsequently realized vol. Persistently positive because insurance costs money; its extremes are the signal."),
        ("Dealer gamma (GEX)", "Aggregate option gamma held by dealers. Positive gamma means their hedging suppresses moves and pins price; negative means it chases and accelerates."),
        ("Gamma flip", "The strike where cumulative dealer gamma crosses zero. Crossing it intraday is often when a quiet tape turns fast."),
        ("Max pain", "The strike at which the most option value expires worthless. A gravitational tendency into expiry, not a law."),
        ("Expected move", "The move the at-the-money straddle prices in before expiry — the options market's own forecast of its range."),
        ("SKEW", "The relative price of tail hedges. High SKEW means crash protection is bid even when spot vol sleeps."),
    ],
    "Positioning & flow": [
        ("COT report", "Weekly CFTC breakdown of futures open interest by trader class. Extremes are contrarian; mid-range readings carry no signal."),
        ("Commercials", "Producers and hedgers with real-world exposure. Counter-trend and early — the informed side of the COT table."),
        ("Large speculators", "Funds and managed money. Trend-followers by nature; their extremes mark crowded trades where the fuel is spent."),
        ("COT index", "Where commercials' net position sits inside its 26-week range, 0–100. Above 80 or below 20 are the contrarian zones."),
        ("Open interest", "Total leveraged contracts outstanding. Rising OI with rising price means new money funding the move; falling OI means positions closing."),
        ("Funding rate", "What perpetual-futures longs pay shorts (or vice versa) to hold. Persistently positive = crowded longs, and squeeze fuel below."),
        ("Liquidation ladder", "Where leveraged positions would be forcibly closed. Price gravitates to dense clusters because forced closes supply liquidity."),
    ],
    "Rotation & trend": [
        ("Relative strength", "An asset's performance versus a benchmark. It persists: what leads over three months tends to keep leading."),
        ("RRG quadrants", "Leading, Weakening, Lagging, Improving — the clockwise rotation of relative strength. Improving is where alpha is born; Weakening is the exit ramp."),
        ("12-1 momentum", "Last twelve months' return excluding the most recent month — the academic standard, skipping the month that mean-reverts."),
        ("Volume profile", "The distribution of volume by price. The POC is the auction's fairest price; the value area holds 70% of volume; thin zones travel fast."),
        ("Anchored VWAP", "Volume-weighted average price from a chosen event — an institutional cost basis, and a level the market actually remembers."),
        ("Confluence level", "A price where several independent methods agree. One moving average is a line on a chart; five methods stacked is real structure."),
    ],
    "Macro & rates": [
        ("Yield-curve inversion", "Short rates above long rates. The warning fires on inversion; the trouble historically lands after the curve re-steepens out of it."),
        ("Bear flattener", "Front-end yields rising faster than the long end — the market prices tightening the long end doubts the economy can absorb. Late-cycle."),
        ("Real yield", "The after-inflation cost of money (via TIPS). The single most important driver for gold, long-duration growth and Bitcoin."),
        ("Credit spread (OAS)", "The extra yield lenders demand over Treasuries — literally the market's price of \"will this borrower survive?\""),
        ("Net liquidity", "Fed balance sheet minus reverse repo minus the Treasury's cash account — the dollars actually available to the system."),
        ("NFCI", "The Chicago Fed's weekly composite of financial conditions. Negative means looser than average; the direction matters more than the level."),
        ("Sahm rule", "A 0.50pt rise in the three-month average unemployment rate off its twelve-month low. It has called every post-war US recession."),
        ("Taylor rule", "A reaction function estimating where policy rates 'should' sit given inflation and unemployment. A reference point, not a forecast."),
        ("Investment clock", "The growth × inflation quadrant — Goldilocks, Overheat, Stagflation, Disinflation. It maps to asset leadership faster than cycle phase does."),
    ],
    "Risk & process": [
        ("R (risk unit)", "Your per-trade risk, entry to stop. Denominating results in R makes any two trades comparable regardless of size or instrument."),
        ("Expectancy", "Win% × average win − loss% × average loss, in R. Positive expectancy plus sizing discipline is the entire game."),
        ("Break-even win rate", "The hit rate a given reward:risk needs just to stop losing money, before costs. A 3R target needs only 25%."),
        ("Kelly fraction", "The mathematically optimal bet size for growth. Full Kelly's drawdowns are unlivable, which is why practitioners use half."),
        ("Drawdown", "Decline from the running high. A 20% drawdown needs 25% to recover; 50% needs 100%. That asymmetry outranks entry selection."),
        ("Variance", "The reason a positive edge still loses money for a while. Survive it, or the edge never gets to pay you."),
    ],
}

def m_glossary():
    total = sum(len(v) for v in GLOSSARY.values())
    body = ('<input id="gq" class="calc" style="width:100%;max-width:340px;margin-bottom:12px" '
            'placeholder="Filter terms…">')
    for section, terms in GLOSSARY.items():
        body += f"<h2>{section}</h2>" + card("".join(
            f'<div class="gterm" style="padding:8px 0;border-bottom:1px solid var(--line)">'
            f'<b style="color:{GOLD}">{t}</b><div class="muted" style="margin-top:2px">{d}</div></div>'
            for t, d in terms))
    body += ("<script>document.getElementById('gq').addEventListener('input',function(e){"
             "const q=e.target.value.toLowerCase();"
             "document.querySelectorAll('.gterm').forEach(x=>{"
             "x.style.display=x.innerText.toLowerCase().includes(q)?'':'none';});"
             "document.querySelectorAll('h2').forEach(h=>{const c=h.nextElementSibling;"
             "const any=[...c.querySelectorAll('.gterm')].some(x=>x.style.display!=='none');"
             "h.style.display=any?'':'none';c.style.display=any?'':'none';});});</script>")
    return dict(slug="glossary", title="Glossary",
                sub="Every term used across this terminal, grouped and searchable, in plain language.",
                body=body, stance="info", headline=f"{total} terms across {len(GLOSSARY)} sections")

# ---------------------------------------------------------------- confluence + overview
# Three pillars, each with weighted members. Weight = how much independent information the
# signal carries (slow structural reads outrank fast noisy ones).
PILLARS = {
    "Trend & structure": {
        "desc": "Is the market's own price action healthy? Direction, participation and the price of risk.",
        "members": {"breadth": 3, "momentum": 3, "relative-strength": 2, "volatility": 2,
                    "valuation": 2, "key-levels": 1, "correlation": 1},
    },
    "Timing & positioning": {
        "desc": "Is the crowd leaning the wrong way? Sentiment, flows, positioning and the calendar.",
        "members": {"sentiment": 2, "cot": 2, "crypto": 1, "seasonality": 1, "calendar": 1},
    },
    "Macro environment": {
        "desc": "Is the backdrop paying you to take risk? Credit, liquidity, policy and the cycle.",
        "members": {"credit-spreads": 3, "liquidity": 3, "financial-conditions": 3,
                    "business-cycle": 2, "yield-curve": 2, "fed-path": 1, "election-cycle": 1},
    },
}
SCORE = {"bullish": 1, "neutral": 0, "bearish": -1}

def build_confluence(mods):
    by_slug = {m["slug"]: m for m in mods}
    pillar_out, pillar_scores = [], {}
    for pname, spec in PILLARS.items():
        rows, num, den = [], 0.0, 0.0
        for slug, w in spec["members"].items():
            m = by_slug.get(slug)
            if not m or m["stance"] == "info":
                continue
            s = SCORE[m["stance"]]
            num += s * w
            den += w
            rows.append((m, w, s))
        if not den:
            continue
        pscore = num / den  # -1..+1
        pillar_scores[pname] = pscore
        pcol = GREEN if pscore > 0.25 else (RED if pscore < -0.25 else AMBER)
        plabel = "Bullish" if pscore > 0.25 else ("Bearish" if pscore < -0.25 else "Neutral")
        bar = (f'<div style="background:#2a2a2a;border-radius:4px;height:8px;position:relative;margin:6px 0">'
               f'<div style="position:absolute;left:50%;width:1px;height:8px;background:{MUT}"></div>'
               f'<div style="position:absolute;left:{50 + min(0, pscore*50):.1f}%;width:{abs(pscore)*50:.1f}%;'
               f'height:8px;background:{pcol};border-radius:4px"></div></div>')
        rows.sort(key=lambda r: (-r[1], -r[2]))
        rhtml = "".join(
            f'<div style="display:flex;gap:8px;align-items:baseline;padding:3px 0;font-size:13px">'
            f'<a href="/terminal/{m["slug"]}/" style="min-width:150px"><b>{m["title"]}</b></a>'
            f'<span class="pill" style="background:{STANCE_COL[m["stance"]]}22;color:{STANCE_COL[m["stance"]]};font-size:10px">{m["stance"]}</span>'
            f'<span class="muted" style="font-size:11px">weight {w}</span>'
            f'<span class="muted" style="font-size:12px;margin-left:auto;text-align:right">{m["headline"]}</span></div>'
            for m, w, _s in rows)
        pillar_out.append(
            f'<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline">'
            f'<div><b>{pname}</b><div class="muted" style="font-size:12px">{spec["desc"]}</div></div>'
            f'<div style="text-align:right"><div class="sval" style="color:{pcol}">{plabel}</div>'
            f'<div class="muted" style="font-size:11px">{pscore:+.2f}</div></div></div>{bar}{rhtml}</div>')
    total = sum(pillar_scores.values()) / len(pillar_scores) if pillar_scores else 0
    agree = len([v for v in pillar_scores.values() if v > 0.25])
    disagree = len([v for v in pillar_scores.values() if v < -0.25])
    if agree == 3:
        verdict, vc = "Full alignment — risk-on", GREEN
        vtxt = ("All three pillars agree. This is the configuration that justifies committing serious capital: "
                "price action, positioning and the macro backdrop are pulling the same way.")
    elif disagree == 3:
        verdict, vc = "Full alignment — risk-off", RED
        vtxt = ("All three pillars agree on the downside. Capital preservation is the trade; the market will "
                "still be here when at least two pillars turn.")
    elif agree >= 2 and disagree == 0:
        verdict, vc = "Constructive", GREEN
        vtxt = ("Two pillars lean bullish with no pillar leaning against. A workable environment for risk, "
                "though the neutral pillar names the thing that could break it.")
    elif disagree >= 2 and agree == 0:
        verdict, vc = "Deteriorating", RED
        vtxt = ("Two pillars lean bearish. Reduce exposure ahead of the third confirming rather than after — "
                "the third pillar is usually price, and it confirms last.")
    else:
        verdict, vc = "Conflicted", AMBER
        vtxt = ("The pillars disagree, and that disagreement is itself the information. Slow signals "
                "(valuation, cycle) fighting fast ones (momentum, flow) is the signature of a turning point — "
                "half size, and let the tape resolve which is early and which is wrong.")
    scored = [m for m in mods if m["stance"] != "info"]
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{vc}">{verdict}</div>'
        f'<div class="muted" style="margin-top:3px">Weighted composite {total:+.2f} on a −1 to +1 scale · '
        f'{sum(m["stance"]=="bullish" for m in scored)} bullish · '
        f'{sum(m["stance"]=="bearish" for m in scored)} bearish · '
        f'{sum(m["stance"]=="neutral" for m in scored)} neutral, across {len(scored)} scored modules</div>'
        f'<div style="margin-top:8px">{vtxt}</div>', "SIGNAL CONFLUENCE")
    body += "<h2>The three pillars</h2>" + "".join(pillar_out)
    body += card(
        "Confluence is context, not a signal service. The stance directions are deliberately coarse — "
        "bullish, neutral, bearish — because pretending to more precision than the inputs carry is exactly how "
        "black boxes lie. The transparency is the product: every read, its source page, and its weight are on "
        "this screen.<br><br>"
        "<b>Known limits, stated plainly.</b> The signals are not fully independent — momentum and relative "
        "strength share DNA, so their agreement is worth less than agreement between, say, valuation and "
        "credit. Weights are judgement, not optimisation. And the slow signals will disagree with the fast "
        "ones at every genuine turning point; that disagreement is the information, not a bug to be averaged "
        "away. This page exists to stop you cherry-picking the modules that happen to agree with the position "
        "you already wanted to take.", "METHODOLOGY & HONESTY")
    return dict(slug="confluence", title="Confluence",
                sub="Every module's signal, weighted into three pillars — alignment is the edge, disagreement is the warning.",
                body=body, stance="info", headline=verdict)

def build_overview(mods, confl):
    slug_group = {}
    for gname, items in GROUPS:
        for slug, _ in items:
            slug_group[slug] = gname
    c = STANCE_COL["info"]
    hero = (f'<a href="/terminal/confluence/" class="card" style="display:block">'
            f'<div class="slabel">CONFLUENCE — THE ONE-LINE READ</div>'
            f'<div style="font-size:19px;font-weight:700;margin-top:4px">{confl["headline"]}</div>'
            f'<div class="muted" style="font-size:12px;margin-top:4px">Every module below, weighted into three '
            f'pillars. Click through for the full breakdown.</div></a>')
    sections = ""
    for gname, items in GROUPS:
        group_mods = [m for m in mods if slug_group.get(m["slug"]) == gname and m["slug"]]
        if not group_mods:
            continue
        cards = []
        for m in group_mods:
            cc = STANCE_COL[m["stance"]]
            cards.append(
                f'<a href="/terminal/{m["slug"]}/" class="card"><div class="slabel">{m["title"].upper()}</div>'
                f'<div style="margin-top:4px;font-size:13px">{m["headline"]}</div>'
                f'<div style="margin-top:6px"><span class="pill" style="background:{cc}22;color:{cc}">'
                f'{m["stance"] if m["stance"] != "info" else "reference"}</span></div></a>')
        sections += f'<h2>{gname}</h2><div class="ovgrid">{"".join(cards)}</div>'
    counts = {k: sum(1 for m in mods if m["stance"] == k) for k in ("bullish", "bearish", "neutral")}
    strip = card(stat_grid([
        ("Modules live", str(len(mods)), MUT),
        ("Bullish", str(counts["bullish"]), GREEN),
        ("Bearish", str(counts["bearish"]), RED),
        ("Neutral", str(counts["neutral"]), AMBER)]), "AT A GLANCE")
    body = hero + strip + sections
    return dict(slug="", title="Terminal Overview",
                sub="Every module's current read at a glance — click any card for the full analysis.",
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
    # Never overwrite a good terminal with a badly degraded one. A couple of dead
    # data sources is tolerable (that page shows "unavailable this run"); a pile of
    # them means the run is broken — bail out before writing anything and let the
    # previous build stand.
    MAX_FAILED = 3
    if failed:
        print(f"FAILED modules ({len(failed)}):")
        for f in failed:
            print("  -", f)
    if len(failed) > MAX_FAILED:
        print(f"ABORT: {len(failed)} module failures exceeds the limit of {MAX_FAILED}; "
              f"pages left untouched.")
        return 2
    slug_order = [s for _, items in GROUPS for s, _ in items]
    mods.sort(key=lambda m: slug_order.index(m["slug"]) if m["slug"] in slug_order else 99)
    confl = build_confluence(mods)
    ov = build_overview(mods, confl)
    for m in mods + [confl]:
        write_page(m["slug"], m["title"], m["sub"], m["body"])
    write_page("", ov["title"], ov["sub"], ov["body"])
    with open(os.path.join(ROOT, ".built"), "w") as f:
        f.write(NOW.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")
    print(f"built {len(mods)+2} pages -> {ROOT} ({len(failed)} degraded)")
    return 0

if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main() or 0)
