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
    glob = sorted(((COUNTRIES[e], e, (px[e].dropna().iloc[-1] / px[e].dropna().rolling(200).mean().iloc[-1] - 1) * 100)
                   for e in COUNTRIES if e in px), key=lambda r: r[2], reverse=True)
    glob_above = sum(g[2] > 0 for g in glob) / len(glob) * 100

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
    body += "<h2>Sector participation</h2>" + card(table(
        ["Sector", "1m return", "> 50d", "> 200d", "Panel % > 50d"],
        [(f"<b>{e}</b> <span class='muted'>{nm}</span>", cnum(r), dot(a), dot(b),
          f"{pct(p) if not math.isnan(p) else '—'} <span class='muted'>(n={k})</span>")
         for e, nm, r, a, b, p, k in sec_rows]))
    body += "<h2>Global breadth</h2>" + card(
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:4px 18px">' +
        "".join(f'<div style="display:flex;gap:7px;align-items:baseline;font-size:13px">{dot(d>0)} <b>{nm}</b> '
                f'<span class="muted">{e}</span><span style="margin-left:auto;color:{GREEN if d>0 else RED}">{d:+.1f}%</span></div>'
                for nm, e, d in glob) + "</div>",
        "COUNTRY ETFs vs THEIR 200-DAY")
    return dict(slug="breadth", title="Market Breadth",
                sub="How many stocks are actually participating — the structural health under the index.",
                body=body, stance=stance,
                headline=f"{regime} — {pct(a50)} of the panel above its 50-day")

def m_volatility(px):
    vix = px["^VIX"].dropna(); v3m = px["^VIX3M"].dropna()
    spy = px["SPY"].dropna()
    lvl = vix.iloc[-1]
    p5y = pctile(vix, lvl)
    ratio = v3m.iloc[-1] / vix.iloc[-1]
    rv20 = spy.pct_change().rolling(20).std().iloc[-1] * math.sqrt(252) * 100
    vrp = lvl - rv20
    if ratio < 1.0:
        regime, rc, stance = "Stress (backwardation)", RED, "bearish"
        note = ("Near-term vol is priced above 3-month vol — the market is paying up for immediate protection. "
                "Historically this happens inside corrections; it also marks where bottoms eventually form.")
    elif lvl < 17 and ratio > 1.1:
        regime, rc, stance = "Calm carry", GREEN, "bullish"
        note = ("Low spot VIX with a steep term structure — the classic risk-on configuration. "
                "Trend-following and short-vol style behavior get paid until the structure flattens.")
    else:
        regime, rc, stance = "Transitional", AMBER, "neutral"
        note = ("Vol is neither cheap-and-steep nor inverted — an in-between tape. The ratio direction is "
                "the tell: flattening toward 1.0 = de-risk; re-steepening = all-clear.")
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{rc}">{regime}</div>' +
        stat_grid([("VIX", f"{lvl:.1f}", col(lvl, lambda v: v < 18, lambda v: v > 25)),
                   ("VIX 5y percentile", pct(p5y, 0), col(p5y, lambda v: v < 50, lambda v: v > 80)),
                   ("VIX3M / VIX", f"{ratio:.2f}", col(ratio, lambda v: v > 1.05, lambda v: v < 1.0)),
                   ("SPY realized vol (20d)", pct(rv20), MUT),
                   ("Implied − realized", f"{vrp:+.1f} pts", col(vrp, lambda v: v > 0))]) +
        f'<div class="muted" style="margin-top:10px">{note}</div>', "VOLATILITY REGIME")
    body += card(line_chart([vix.iloc[-252:].tolist()], [BLUE],
                            hlines=[(20, MUT, "20"), (30, RED, "30")]) +
                 '<div class="legend">VIX, last 12 months. Spikes &gt;30 mark panic; sub-15 marks complacency. '
                 'The term-structure ratio flags regime change earlier than the level itself.</div>')
    return dict(slug="volatility", title="Volatility Regime",
                sub="What the options market charges for risk — level, term structure, and the premium over realized.",
                body=body, stance=stance, headline=f"{regime} — VIX {lvl:.1f}, 3m/spot {ratio:.2f}")

def m_relative_strength(px):
    rows = []
    for etf, name in {**SECTORS, "EFA": "Dev. intl", "EEM": "Emerging", "IWM": "Small caps",
                      "QQQ": "Nasdaq 100", "RSP": "Equal-weight"}.items():
        s = (px[etf] / px["SPY"]).dropna()
        r3, r1 = (s.iloc[-1] / s.iloc[-64] - 1) * 100, (s.iloc[-1] / s.iloc[-22] - 1) * 100
        rows.append((etf, name, r3, r1, r3 > 0 and r1 > 0, r3 < 0 and r1 < 0))
    rows.sort(key=lambda r: r[2], reverse=True)
    leaders = [r for r in rows if r[4]][:4]
    stance = "info"
    body = card(table(["vs SPY", "3-month", "1-month", "Status"],
                      [(f"<b>{e}</b> <span class='muted'>{nm}</span>", cnum(r3), cnum(r1),
                        f'<span style="color:{GREEN}">leading</span>' if ld else
                        (f'<span style="color:{RED}">lagging</span>' if lg else
                         '<span class="muted">turning</span>'))
                       for e, nm, r3, r1, ld, lg in rows]),
                "RELATIVE STRENGTH vs S&P 500 · RATIO CHANGE") + card(
        "Relative strength persists: what leads over 3 months tends to keep leading. The highest-signal names "
        "are green on BOTH horizons (established + still accelerating). A 3-month leader going red on 1-month "
        "is rotation starting — that's where tops in leadership themes first show up.", "HOW TO READ IT")
    return dict(slug="relative-strength", title="Relative Strength",
                sub="Which sectors and style baskets are beating the index — ratio momentum on two horizons.",
                body=body, stance=stance,
                headline="Leaders: " + ", ".join(r[0] for r in leaders) if leaders else "No dual-horizon leaders")

def m_key_levels(px):
    rows = []
    for t in ["SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "BTC-USD"]:
        s = px[t].dropna()
        last = s.iloc[-1]
        s50, s200 = s.rolling(50).mean().iloc[-1], s.rolling(200).mean().iloc[-1]
        h52, l52 = s.rolling(252).max().iloc[-1], s.rolling(252).min().iloc[-1]
        mo = s.loc[s.index >= (s.index[-1] - pd.Timedelta(days=31))]
        piv = (mo.max() + mo.min() + last) / 3
        rows.append((t, last, s50, s200, h52, l52, piv))
    body = card(table(
        ["Asset", "Last", "50-day", "200-day", "52w high", "52w low", "Pivot (1m)"],
        [(f"<b>{t}</b> <span class='muted'>{ANAMES.get(t,'')}</span>", f"{l:,.0f}" if l > 500 else f"{l:,.2f}",
          f'<span style="color:{GREEN if l> a else RED}">{a:,.1f}</span>',
          f'<span style="color:{GREEN if l> b else RED}">{b:,.1f}</span>',
          f"{h:,.1f} <span class='muted'>({(l/h-1)*100:+.1f}%)</span>",
          f"{lo:,.1f} <span class='muted'>({(l/lo-1)*100:+.1f}%)</span>",
          f"{p:,.1f}") for t, l, a, b, h, lo, p in rows]),
        "TREND & REFERENCE LEVELS") + card(
        "Green moving-average cells = price above that average (trend support below); red = trend overhead "
        "as resistance. The 52-week extremes are the market's memory — approaches of the high with strong "
        "breadth break through; with weak breadth they get sold. Pivot = (1m high + low + close) / 3, a "
        "mean-reversion magnet for the coming weeks.", "HOW TO READ IT")
    spys = px["SPY"].dropna().iloc[-252:]
    body += card(line_chart([spys.tolist(), spys.rolling(50).mean().dropna().tolist(),
                             spys.rolling(200).mean().dropna().tolist()], [GOLD, BLUE, MUT]) +
                 f'<div class="legend"><span style="color:{GOLD}">▬</span> SPY · '
                 f'<span style="color:{BLUE}">▬</span> 50-day · <span style="color:{MUT}">▬</span> 200-day · 12 months</div>')
    return dict(slug="key-levels", title="Key Levels",
                sub="Where trend support, resistance, and the market's reference points sit right now.",
                body=body, stance="info",
                headline=f"SPY {px['SPY'].dropna().iloc[-1]:,.0f} — "
                         f"{'above' if px['SPY'].dropna().iloc[-1] > px['SPY'].dropna().rolling(200).mean().iloc[-1] else 'below'} its 200-day")

def m_valuation(px, gspc_m):
    spy = px["SPY"].dropna()
    logp = pd.Series(range(len(gspc_m)), index=gspc_m.index)
    import numpy as np
    y = np.log(gspc_m.values.astype(float))
    x = np.arange(len(y))
    b, a = np.polyfit(x, y, 1)
    trend = np.exp(a + b * x)
    dev = (gspc_m.values[-1] / trend[-1] - 1) * 100
    pe = None
    try:
        pe = yf.Ticker("SPY").info.get("trailingPE")
    except Exception:
        pass
    tnx = px["^TNX"].dropna().iloc[-1]
    ey = (100 / pe) if pe else None
    erp = (ey - tnx) if ey else None
    stance = "bearish" if dev > 40 else ("bullish" if dev < -20 else "neutral")
    items = [("S&P vs long-run trend", sgn(dev), col(dev, lambda v: v < 0, lambda v: v > 40)),
             ("10-year yield", pct(tnx, 2), MUT)]
    if pe:
        items += [("SPY trailing P/E", f"{pe:.1f}", col(pe, lambda v: v < 20, lambda v: v > 28)),
                  ("Earnings yield − 10y", f"{erp:+.2f} pts", col(erp, lambda v: v > 0))]
    dev_series = (pd.Series(gspc_m.values.astype(float), index=gspc_m.index) /
                  pd.Series(trend, index=gspc_m.index) - 1) * 100
    body = card(stat_grid(items) +
                '<div class="muted" style="margin-top:10px">Valuation is a regime dial, not a timing tool: '
                'stretched markets can stretch for years, but the further above trend, the thinner forward '
                'returns get and the harder drawdowns hit. It sets position size, not entry timing.</div>',
                "WHERE THE MARKET SITS") + card(
        line_chart([dev_series.iloc[-360:].tolist()], [GOLD], hlines=[(0, MUT, "trend"), (40, RED, "+40"), (-20, GREEN, "−20")]) +
        '<div class="legend">S&P 500 deviation from its full-history log-linear trend, last 30 years. '
        'Above +40% marks the historically expensive zone; −20% and below marks the cheap zone.</div>')
    return dict(slug="valuation", title="Valuation",
                sub="How expensive the market is versus its own history — the slow force under everything else.",
                body=body, stance=stance, headline=f"S&P {sgn(dev)} vs its long-run trend")

def m_correlation(px):
    names = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "HYG", "GLD", "DBC", "UUP", "BTC-USD"]
    rets = px[names].pct_change().iloc[-63:]
    cm = rets.corr()
    def cell(v):
        if v >= 0.99: return f'<td class="muted">—</td>'
        c = GREEN if v > 0.5 else (RED if v < -0.3 else "var(--tx)")
        return f'<td style="color:{c}">{v:+.2f}</td>'
    hdr = "".join(f"<th>{n.replace('-USD','')}</th>" for n in names)
    rows = "".join("<tr><td><b>" + n.replace("-USD", "") + "</b></td>" +
                   "".join(cell(cm.loc[n, m]) for m in names) + "</tr>" for n in names)
    sb = cm.loc["SPY", "TLT"]
    stance = "info"
    body = card(f"<table><tr><th></th>{hdr}</tr>{rows}</table>"
                '<div class="legend">Pairwise correlation of daily returns, trailing 3 months. '
                'Green &gt; +0.5 (moves together), red &lt; −0.3 (true diversifier).</div>',
                "3-MONTH CORRELATION MATRIX") + card(
        f"Stock–bond correlation is <b style='color:{GREEN if sb < 0 else AMBER}'>{sb:+.2f}</b>. "
        "Negative = bonds hedge equity risk again (the classic 60/40 regime). Positive = both sell off "
        "together, which is when portfolios that look diversified aren't — and when gold and the dollar "
        "earn their place.", "THE PAIR THAT MATTERS MOST")
    return dict(slug="correlation", title="Correlation Matrix",
                sub="What actually diversifies right now — trailing co-movement across the major assets.",
                body=body, stance=stance, headline=f"Stock–bond correlation {sb:+.2f}")

def m_momentum(px):
    rows = []
    for t in ["SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "HYG", "GLD", "SLV", "USO", "DBC", "UUP", "BTC-USD", "ETH-USD"]:
        s = px[t].dropna()
        def r(d): return (s.iloc[-1] / s.iloc[-d - 1] - 1) * 100
        m121 = (s.iloc[-22] / s.iloc[-253] - 1) * 100 if len(s) > 253 else float("nan")
        rows.append((t, r(21), r(63), r(126), m121,
                     s.iloc[-1] > s.rolling(200).mean().iloc[-1]))
    spy = px["SPY"].dropna()
    spy_m = spy.resample("ME").last()
    sig10 = spy_m.iloc[-1] > spy_m.rolling(10).mean().iloc[-1]
    stance = "bullish" if sig10 else "bearish"
    body = card(table(["Asset", "1m", "3m", "6m", "12-1 mom", "> 200d"],
                      [(f"<b>{t.replace('-USD','')}</b> <span class='muted'>{ANAMES.get(t,'')}</span>",
                        cnum(a), cnum(b), cnum(c),
                        cnum(d) if not math.isnan(d) else "—", dot(e))
                       for t, a, b, c, d, e in rows]), "CROSS-ASSET MOMENTUM") + card(
        f"The classic 10-month moving-average filter on the S&P is currently "
        f"<b style='color:{GREEN if sig10 else RED}'>{'RISK-ON (price above)' if sig10 else 'RISK-OFF (price below)'}</b>. "
        "It's a blunt tool that whipsaws in chop, but it has kept investors out of every major bear market for "
        "a century. 12-1 momentum (last year excluding the latest month) is the academic standard: own what's "
        "already working, skip the most recent month to dodge mean-reversion.", "THE TWO FILTERS THAT MATTER")
    return dict(slug="momentum", title="Momentum",
                sub="What's working across assets and timeframes — trend as a signal, not a story.",
                body=body, stance=stance,
                headline=f"10-month filter: {'risk-on' if sig10 else 'risk-off'}")

def m_seasonality(gspc_m):
    m = gspc_m.pct_change().dropna()
    m = m[m.index.year >= 1950]
    by_mo = m.groupby(m.index.month)
    avg = by_mo.mean() * 100
    winr = by_mo.apply(lambda g: (g > 0).mean() * 100)
    cur = NOW.month
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    stance = "bullish" if avg[cur] > 0.5 else ("bearish" if avg[cur] < 0 else "neutral")
    body = card(bar_chart(labels, [avg.get(i, 0) for i in range(1, 13)], highlight=cur - 1) +
                '<div class="legend">Average S&P 500 monthly return since 1950 · gold bar = current month.</div>',
                "MONTHLY SEASONALITY") + card(
        f"<b>{labels[cur-1]}</b> has averaged <b style='color:{GREEN if avg[cur]>0 else RED}'>{avg[cur]:+.2f}%</b> "
        f"with a {winr[cur]:.0f}% hit rate since 1950. Seasonality is a tailwind/headwind gauge — worth maybe "
        "a sizing adjustment, never a standalone trade. The famous patterns: Nov–Apr carries most of the "
        "market's annual return; September is the only reliably negative month; October is volatile but a "
        "bottom-maker, not a top-maker.", "THIS MONTH IN CONTEXT")
    return dict(slug="seasonality", title="Seasonality",
                sub="The calendar's historical drift — which months carry the return and which take it back.",
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

def m_sentiment(px):
    vix = px["^VIX"].dropna(); skew = px["^SKEW"].dropna()
    vix_p = pctile(vix, vix.iloc[-1])
    skew_p = pctile(skew, skew.iloc[-1])
    hyg_ief = (px["HYG"] / px["IEF"]).dropna()
    risk_app = (hyg_ief.iloc[-1] / hyg_ief.iloc[-64] - 1) * 100
    gld_spy = (px["GLD"] / px["SPY"]).dropna()
    fear_flow = (gld_spy.iloc[-1] / gld_spy.iloc[-64] - 1) * 100
    # composite: low vix pctile + rising HYG/IEF = greed; opposite = fear
    score = (50 - vix_p) * 0.4 + (10 if risk_app > 0 else -10) + (-fear_flow * 0.5)
    mood = "Greed" if score > 15 else ("Fear" if score < -15 else "Neutral")
    mc = GREEN if mood == "Greed" else (RED if mood == "Fear" else AMBER)
    stance = "bearish" if mood == "Greed" and vix_p < 15 else ("bullish" if mood == "Fear" else "neutral")
    body = card(
        f'<div style="font-size:19px;font-weight:700;color:{mc}">{mood}</div>' +
        stat_grid([("VIX 5y percentile", pct(vix_p, 0), col(vix_p, lambda v: 20 < v < 70, lambda v: v < 10 or v > 90)),
                   ("SKEW percentile", pct(skew_p, 0), MUT),
                   ("Risk appetite (HYG/IEF 3m)", sgn(risk_app), col(risk_app, lambda v: v > 0)),
                   ("Fear flow (GLD/SPY 3m)", sgn(fear_flow), col(fear_flow, lambda v: v < 0))]) +
        '<div class="muted" style="margin-top:10px">Sentiment is a contrarian tool only at extremes: '
        'crowded fear (VIX &gt;90th percentile, gold bid, credit dumped) marks bottoms; total complacency '
        '(VIX &lt;10th percentile with junk-bond euphoria) removes the fuel rallies run on. In between, '
        'the crowd is right — trend beats fading it.</div>', "COMPOSITE MOOD (PRICE-BASED PROXIES)")
    return dict(slug="sentiment", title="Sentiment",
                sub="Fear and greed read from prices, not surveys — vol, credit appetite, and safe-haven flows.",
                body=body, stance=stance, headline=f"{mood} — VIX in its {vix_p:.0f}th percentile")

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

def m_cot():
    MKTS = [("E-MINI S&P 500", "S&P 500 e-mini"), ("NASDAQ MINI", "Nasdaq mini"),
            ("GOLD", "Gold"), ("WTI", "WTI crude"), ("EURO FX", "Euro FX"),
            ("UST 10Y NOTE", "10y T-Note")]
    rows = []
    for key, label in MKTS:
        try:
            q = ("https://publicreporting.cftc.gov/resource/6dca-aqww.json?"
                 f"$where=upper(market_and_exchange_names)%20like%20%27%25{urllib.request.quote(key)}%25%27"
                 "&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=156")
            with urllib.request.urlopen(q, timeout=30) as r:
                data = json.loads(r.read())
            if not data:
                continue
            name0 = data[0]["market_and_exchange_names"]
            data = [d for d in data if d["market_and_exchange_names"] == name0]
            nets = [int(d["noncomm_positions_long_all"]) - int(d["noncomm_positions_short_all"]) for d in data]
            cur = nets[0]
            p = float(pd.Series(nets[::-1]).rank(pct=True).iloc[-1] * 100)
            rows.append((label, cur, p, data[0]["report_date_as_yyyy_mm_dd"][:10]))
        except Exception:
            continue
    if not rows:
        raise RuntimeError("CFTC API unavailable")
    body = card(table(["Market", "Large-spec net position", "3y percentile", "Report date"],
                      [(f"<b>{l}</b>", f"{n:+,.0f}",
                        f'<span style="color:{RED if p>90 or p<10 else "var(--tx)"}">{p:.0f}%</span>', d)
                       for l, n, p, d in rows]), "NON-COMMERCIAL (SPECULATOR) POSITIONING") + card(
        "Speculator positioning is a contrarian signal only at extremes: when large specs are at a 3-year "
        "high in net length (&gt;90th percentile), the buying that drove the trend is already done — and vice "
        "versa at the lows. Mid-range readings carry no signal. Commercials are the other side of this table "
        "by construction. Data: CFTC legacy COT report, updated Fridays.", "HOW TO READ IT")
    ext = [r for r in rows if r[2] > 90 or r[2] < 10]
    return dict(slug="cot", title="COT Positioning",
                sub="What the big speculators hold in the futures market — crowding as a contrarian tell.",
                body=body, stance="info",
                headline=("Extremes: " + ", ".join(r[0] for r in ext)) if ext else "No positioning extremes")

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
