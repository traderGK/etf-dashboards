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


def _fetch_page(page):
    req = urllib.request.Request(SCREENER.format(page=page), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


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
    for p in range(1, PAGES + 1):
        rows = _parse(_fetch_page(p))
        if not rows:
            break
        for r in rows:
            k = (r["filed"], r["ticker"], r["insider"], r["value"])
            if k not in seen:
                seen.add(k)
                filings.append(r)
        time.sleep(1.5)  # be polite between pages
    if len(filings) < 20:
        # implausibly small — markup change or block; keep last-good file
        raise RuntimeError(f"only {len(filings)} filings parsed — keeping last-good {OUT_FILE}")
    filings.sort(key=lambda f: f["filed"], reverse=True)
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "openinsider",
        "settings": {"min_value_usd": 500000, "titles": ["CEO", "CFO"],
                     "types": ["P", "S"], "window_days": CLUSTER_WINDOW_DAYS},
        "clusters": _clusters(filings),
        "filings": filings[:300],
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"   Insider: {len(filings)} filings, {len(out['clusters'])} cluster rows → {OUT_FILE}")
    return True


if __name__ == "__main__":
    refresh_insider(force="--force" in os.sys.argv)
