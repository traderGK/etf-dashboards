#!/usr/bin/env python3
"""
Insider activity feed for tradergk.com/insider (PUBLIC).

Scrapes OpenInsider's SEC Form 4 screener with GK's fixed settings:
  - Transactions: P (Purchase) + S (Sale) only
  - Insider titles: CEO + CFO only
  - Filing date: last 1 year, sorted by filing date desc
  - Traded value >= $500k  (small transactions excluded at the source)
  - All sectors except funds
Then computes repetition signals on top:
  - CLUSTER: >=2 DISTINCT insiders, same ticker, same direction, filings within 14 days
  - STREAK : same insider, same ticker, same direction, >=2 filings within 14 days
and writes public insider.json next to data.json.

Called from refresh_data.py (non-fatal). Throttled: refetches only when the
existing insider.json is older than 1 hour — filings don't move faster and it
keeps us polite toward OpenInsider. On ANY fetch/parse failure the previous
insider.json is left untouched (last-good survives outages), same philosophy
as the etf_full daily cache.

Fallback plan if OpenInsider ever blocks or changes markup: SEC EDGAR Form 4
direct (see docs — not built yet).
"""
import html as _html
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone

OUT_FILE = "insider.json"
MAX_AGE_MIN = 60           # refetch when older than this
PAGES = 3                  # 100 rows/page -> ~300 rows of >=$500k history
CLUSTER_WINDOW_DAYS = 14

# Nasdaq-100 members (static snapshot — update on index rebalances; keep in
# sync with the NDX list inside insider/index.html)
NDX = set(("AAPL MSFT NVDA AMZN META GOOGL GOOG AVGO TSLA COST NFLX AMD PEP ADBE CSCO QCOM "
           "TMUS INTU AMAT TXN CMCSA HON ISRG BKNG AMGN VRTX ADP PANW GILD SBUX MU ADI INTC "
           "LRCX MDLZ REGN KLAC SNPS CDNS PDD MELI CTAS CSX MAR ORLY CRWD ABNB FTNT NXPI PCAR "
           "ROP WDAY DASH CPRT MNST ROST AEP ODFL PAYX KDP FAST CHTR EA GEHC VRSK CTSH XEL KHC "
           "EXC LULU CCEP IDXX TTWO ZS DDOG TEAM FANG ON CDW GFS WBD MRVL ARM PLTR AXON APP "
           "MSTR SHOP LIN DXCM BKR CEG TTD AZN BIIB").split())
NDX_MIN_K = 100            # NDX pass: $100k floor (bands rendered client-side)
NDX_CHUNK = 20             # tickers per screener query
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

SCREENER = ("http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh="
            "&fd=365&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago="
            "&xp=1&xs=1"            # P - Purchase, S - Sale
            "&vl=500&vh="           # traded value min $500k
            "&ocl=&och=&sic1=-1&sicl=100&sich=9999"   # all sectors except funds
            "&isceo=1&iscfo=1"      # CEO + CFO
            "&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h="
            "&sortcol=0&cnt=100&page={page}")

# NDX-only pass: lower floor ($100k) and wider titles (COB/CEO/Pres/COO/CFO/Dir)
# — at mega-caps even a small officer/director trade is meaningful, and buys
# are rare enough to be signal on their own.
SCREENER_NDX = ("http://openinsider.com/screener?s={tickers}&o=&pl=&ph=&ll=&lh="
                "&fd=365&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago="
                "&xp=1&xs=1"
                "&vl=" + str(NDX_MIN_K) + "&vh="
                "&ocl=&och=&sic1=-1&sicl=100&sich=9999"
                "&iscob=1&isceo=1&ispres=1&iscoo=1&iscfo=1&isdirector=1"
                "&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h="
                "&sortcol=0&cnt=100&page={page}")


def _age_min(path):
    try:
        with open(path) as f:
            gen = json.load(f).get("generated", "")
        dt = datetime.strptime(gen, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return 1e9


def _strip(cell_html):
    return _html.unescape(re.sub(r"<[^>]+>", "", cell_html)).strip()


def _num(s):
    s = s.replace("$", "").replace(",", "").replace("%", "").replace("+", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _fetch_page(page):
    return _get(SCREENER.format(page=page))


def _parse(page_html):
    i = page_html.find('class="tinytable"')
    if i < 0:
        return []
    j = page_html.find("</table>", i)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page_html[i:j], re.S)
    out = []
    for r in rows[1:]:  # skip header
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(cells) < 13:
            continue
        # ticker sits inside an <a href="/XXX"> in cell 3 — take it from the href
        m = re.search(r'href="/([A-Za-z.\-]+)"', cells[3])
        ticker = (m.group(1) if m else _strip(cells[3])).upper()
        ttype = _strip(cells[7])
        rec = {
            "flags":   _strip(cells[0]),
            "filed":   _strip(cells[1]),          # "2026-07-17 21:46:47"
            "traded":  _strip(cells[2]),          # "2026-07-15"
            "ticker":  ticker,
            "company": _strip(cells[4]),
            "insider": _strip(cells[5]),
            "title":   _strip(cells[6]),
            "type":    ttype,                     # "P - Purchase" / "S - Sale" / "S - Sale+OE"
            "dir":     "buy" if ttype.startswith("P") else "sell",
            "price":   _num(_strip(cells[8])),
            "qty":     _num(_strip(cells[9])),
            "owned":   _num(_strip(cells[10])),
            "dOwn":    _num(_strip(cells[11])),
            "value":   _num(_strip(cells[12])),
        }
        if rec["ticker"] and rec["filed"]:
            out.append(rec)
    return out


def _clusters(filings):
    """CLUSTER (>=2 distinct insiders) ranked above STREAK (same insider x2),
    both within a rolling CLUSTER_WINDOW_DAYS window per (ticker, direction)."""
    groups = {}
    for f in filings:
        groups.setdefault((f["ticker"], f["dir"]), []).append(f)
    out = []
    win = CLUSTER_WINDOW_DAYS * 86400
    for (ticker, d), fl in groups.items():
        fl.sort(key=lambda x: x["filed"], reverse=True)
        try:
            newest = time.mktime(time.strptime(fl[0]["filed"][:10], "%Y-%m-%d"))
        except Exception:
            continue
        recent = [f for f in fl
                  if time.mktime(time.strptime(f["filed"][:10], "%Y-%m-%d")) >= newest - win]
        if len(recent) < 2:
            continue
        insiders = {f["insider"] for f in recent}
        badge = "CLUSTER" if len(insiders) >= 2 else "STREAK"
        qty = sum(abs(f["qty"]) for f in recent) or 1
        out.append({
            "ticker": ticker,
            "ndx": recent[0].get("ndx", False),
            "company": recent[0]["company"],
            "dir": d,
            "badge": badge,
            "n_trades": len(recent),
            "n_insiders": len(insiders),
            "total_value": sum(f["value"] for f in recent),
            "avg_price": round(sum(f["price"] * abs(f["qty"]) for f in recent) / qty, 2),
            "last_filed": recent[0]["filed"][:10],
            "filings": recent,
        })
    out.sort(key=lambda c: (c["badge"] != "CLUSTER", -abs(c["total_value"])))
    return out


def refresh_insider(force=False):
    """Returns True if insider.json was (re)written."""
    age = _age_min(OUT_FILE)
    if not force and age < MAX_AGE_MIN:
        print(f"   Insider: fresh ({age:.0f} min old, limit {MAX_AGE_MIN}) — skipping")
        return False
    filings, seen = [], set()

    def _absorb(rows):
        n = 0
        for r in rows:
            k = (r["filed"], r["ticker"], r["insider"], r["value"])
            if k not in seen:
                seen.add(k)
                r["ndx"] = r["ticker"] in NDX
                filings.append(r)
                n += 1
        return n

    # Pass 1 — all-market: CEO/CFO, >=$500k (the clean headline feed)
    for p in range(1, PAGES + 1):
        rows = _parse(_fetch_page(p))
        if not rows:
            break
        _absorb(rows)
        time.sleep(1.5)  # be polite between pages
    if len(filings) < 20:
        # implausibly small — markup change or block; keep last-good file
        raise RuntimeError(f"only {len(filings)} filings parsed — keeping last-good {OUT_FILE}")

    # Pass 2 — Nasdaq-100 only: wider titles, >=$100k, queried in ticker chunks.
    # Non-fatal per chunk: a failed chunk just means fewer NDX rows this hour.
    ndx_rows = 0
    tickers = sorted(NDX)
    for i in range(0, len(tickers), NDX_CHUNK):
        chunk = "+".join(tickers[i:i + NDX_CHUNK])
        try:
            ndx_rows += _absorb(_parse(_get(SCREENER_NDX.format(tickers=chunk, page=1))))
        except Exception as e:
            print(f"   Insider: NDX chunk {i//NDX_CHUNK+1} failed (non-fatal): {e}")
        time.sleep(1.5)
    print(f"   Insider: +{ndx_rows} extra NDX rows (>= ${NDX_MIN_K}k, wide titles)")
    filings.sort(key=lambda f: f["filed"], reverse=True)
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "openinsider",
        "settings": {"min_value_usd": 500000, "titles": ["CEO", "CFO"],
                     "types": ["P", "S"], "window_days": CLUSTER_WINDOW_DAYS,
                     "ndx_min_usd": NDX_MIN_K * 1000,
                     "ndx_titles": ["COB", "CEO", "Pres", "COO", "CFO", "Dir"]},
        "clusters": _clusters(filings),
        "filings": filings[:600],
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"   Insider: {len(filings)} filings, {len(out['clusters'])} cluster rows → {OUT_FILE}")
    return True


if __name__ == "__main__":
    refresh_insider(force="--force" in os.sys.argv)
