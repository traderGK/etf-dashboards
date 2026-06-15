import json, time, sys, re, os, subprocess
from datetime import datetime, timezone, timedelta
import yfinance as yf
import pandas as pd

# ── Ratio signal config ───────────────────────────────────────────────────────
CORE_R = [
    {"key":"XLY/XLP",   "num":"XLY",  "den":"XLP",  "master":True,  "inv":False},
    {"key":"HYG/LQD",   "num":"HYG",  "den":"LQD",  "master":True,  "inv":False},
    {"key":"SPY/TLT",   "num":"SPY",  "den":"TLT",  "master":True,  "inv":False},
    {"key":"CPER/GLD",  "num":"CPER", "den":"GLD",  "master":True,  "inv":False},
    {"key":"QQQ/SPY",   "num":"QQQ",  "den":"SPY",  "master":False, "inv":False},
    {"key":"IWM/SPY",   "num":"IWM",  "den":"SPY",  "master":False, "inv":False},
    {"key":"RSP/SPY",   "num":"RSP",  "den":"SPY",  "master":False, "inv":False},
    {"key":"GLD/SPY",   "num":"GLD",  "den":"SPY",  "master":False, "inv":True },
    {"key":"IWF/IWD",   "num":"IWF",  "den":"IWD",  "master":False, "inv":False},
    {"key":"EEM/EFA",   "num":"EEM",  "den":"EFA",  "master":False, "inv":False},
    {"key":"IYT/XLU",   "num":"IYT",  "den":"XLU",  "master":False, "inv":False},
    {"key":"XLK/SHY",   "num":"XLK",  "den":"SHY",  "master":False, "inv":False},
    {"key":"IBIT/GLD",  "num":"IBIT", "den":"GLD",  "master":False, "inv":False},
    {"key":"XLK/XLU",   "num":"XLK",  "den":"XLU",  "master":False, "inv":False},
    {"key":"KRE/SPY",   "num":"KRE",  "den":"SPY",  "master":False, "inv":False},
    {"key":"SPHB/SPLV", "num":"SPHB", "den":"SPLV", "master":False, "inv":False},
    {"key":"HYG/TLT",   "num":"HYG",  "den":"TLT",  "master":False, "inv":False},
    {"key":"GLD/TLT",   "num":"GLD",  "den":"TLT",  "master":False, "inv":False},
    {"key":"SMH/IGV",   "num":"SMH",  "den":"IGV",  "master":False, "inv":False},
    {"key":"EWJ/SPY",   "num":"EWJ",  "den":"SPY",  "master":False, "inv":False},
    {"key":"COPX/GLD",  "num":"COPX", "den":"GLD",  "master":False, "inv":False},
    {"key":"SKYY/SPY",  "num":"SKYY", "den":"SPY",  "master":False, "inv":False},
    # SMH/SPY, XBI/SPY, INDA/SPY live in THEME_R only — duplicating them here
    # made each one vote twice in the front-end regime score (orphan rows fall
    # back to weight 1 because the JS config no longer carries them as core).
]
THEME_R = [
    {"key":"SMH/SPY",   "num":"SMH",  "den":"SPY",  "master":False, "inv":False, "theme":True},
    {"key":"ITA/SPY",   "num":"ITA",  "den":"SPY",  "master":False, "inv":False, "theme":True},
    {"key":"ARKK/SPY",  "num":"ARKK", "den":"SPY",  "master":False, "inv":False, "theme":True},
    {"key":"QTUM/SMH",  "num":"QTUM", "den":"SMH",  "master":False, "inv":False, "theme":True},
    {"key":"SOXX/SMH",  "num":"SOXX", "den":"SMH",  "master":False, "inv":False, "theme":True},
    {"key":"XBI/SPY",   "num":"XBI",  "den":"SPY",  "master":False, "inv":False, "theme":True},
    {"key":"INDA/SPY",  "num":"INDA", "den":"SPY",  "master":False, "inv":False, "theme":True},
    {"key":"PAVE/SPY",  "num":"PAVE", "den":"SPY",  "master":False, "inv":False, "theme":True},
    {"key":"MAGS/SPY",  "num":"MAGS", "den":"SPY",  "master":False, "inv":False, "theme":True},
]
ALL_R = CORE_R + THEME_R
SMA_S, SMA_L = 20, 50

# ── Best Performers groups (must match JS BP_GROUPS exactly) ──────────────────
BP_GROUPS = {
    'US Sectors':      ['XLK','XLF','XLE','XLV','XLI','XLC','XLU','XLY','XLP','XLRE','XLB'],
    'Global Sectors':  ['IXN','IXJ','IXC','IXG','MXI','KXI'],
    'Macro / Asset':   ['QQQ','IWM','SMH','SOXX','IBIT','GLD','EEM','EFA','RSP','HYG','TLT','MAGS','SKYY','FINX','INDA'],
    'Trending Themes': ['ITA','XAR','SHLD','NASA','UFO','QTUM','AIQ','CHAT','BOTZ','CIBR','URA','ARKK','ARKG','XBI','COPX','PAVE','BLOK','ICLN','TAN','LIT','REMX'],
}
ALL_BP_TICKERS = list({t for g in BP_GROUPS.values() for t in g} | {'SPY'})

# ── All 62 ETFs on the dashboard ──────────────────────────────────────────────
ETF_TICKERS = [
    'XLK','XLF','XLE','XLV','XLI','XLC','XLU','XLY','XLP','XLRE','XLB',
    'IXN','IXJ','IXC','IXG','MXI','KXI',
    'SPY','QQQ','IWM','RSP','TLT','LQD','HYG','GLD','IBIT','SMH',
    'EEM','EFA','SHY','IWF','IWD','IYT',
    'ITA','XAR','SHLD','NASA','UFO','ARKX','QTUM','AIQ','CHAT','BOTZ',
    'CIBR','URA','BLOK','ICLN','TAN','LIT','ARKG','ARKK',
    'SOXX','MAGS','PAVE','XBI','IBB','INDA','COPX','SKYY','FINX','REMX','TUR',
]

# ── Leveraged ETFs (trade ideas in popup) — BULL + BEAR ───────────────────────
LEVERAGED_TICKERS = [
    # Bull leveraged
    'TECL','TQQQ','FAS','DPST','ERX','NRGU','CURE','LABU','DUSL','TPOR',
    'MIDU','TNA','URTY','SPXL','UPRO','UDOW','SOXL','USD','FNGU','DFEN',
    'WANT','INDL','EDC','TMF','UBT','BIB','BITX','BITU',
    'NAIL','DRN','HIBL','WEBL','UGL','NUGT','KLNE','EURL','EFO','EET',
    # Bear / inverse leveraged
    'TECS','SQQQ','FAZ','SKF','ERY','DRIP','LABD','SPXS','SPXU',
    'TZA','SRTY','TMV','TBT','TBF','GLL','DUST','SOXS','DRV','REK',
    'EDZ','EEV','HIBS','WEBS','FNGD','SBIT','QID',
]

# ── Hardcoded fallback holdings (used when Yahoo Finance returns no data) ──────
# These are the tickers stored in the JS HOLDINGS array — used as last resort
HARDCODED_HOLDINGS = {
    'XLK': ['AAPL','NVDA','MSFT','AVGO','META','AMD','CRM','ADBE','AMAT','QCOM','ORCL','CSCO','NOW','INTU','PANW','KLAC','LRCX','MU','MRVL','SNPS','CDNS','FTNT'],
    'XLF': ['BRK.B','JPM','V','MA','BAC','WFC','GS','MS','BLK','SPGI','CME','ICE','AXP','C','USB','PNC','TRV','COF','MET','AON'],
    'XLE': ['XOM','CVX','COP','EOG','SLB','MPC','VLO','PSX','OXY','HAL','BKR','DVN','HES','MRO','OKE','WMB','KMI','LNG'],
    'XLV': ['UNH','LLY','JNJ','ABBV','MRK','PFE','TMO','DHR','ABT','ISRG','ELV','CVS','AMGN','CI','BMY','MDT','BSX','SYK','BDX','GEHC','ZTS','VRTX'],
    'XLI': ['GEV','RTX','CAT','HON','DE','LMT','PH','NOC','ETN','UNP','CTAS','RSG','FDX','NSC','CSX','ROK','EMR','JCI','AME','PCAR','URI','PWR'],
    'XLC': ['META','GOOGL','GOOG','NFLX','TMUS','CMCSA','DIS','T','CHTR','EA','VZ','WBD','OMC','TTWO','LYV','FOXA'],
    'XLU': ['NEE','SO','DUK','SRE','D','AEP','EXC','ED','XEL','WEC','ES','ETR','PPL','FE','CNP','NI','AES'],
    'XLY': ['AMZN','TSLA','HD','MCD','LOW','TJX','BKNG','NKE','SBUX','TGT','GM','F','CMG','YUM','HLT','MAR'],
    'XLP': ['PG','COST','WMT','KO','PEP','PM','MDLZ','CL','EL','GIS','STZ','HSY','MKC','CHD','KHC'],
    'XLRE': ['AMT','PLD','CCI','EQIX','PSA','O','WELL','SPG','DLR','AVB','EQR','VTR','ARE'],
    'XLB': ['LIN','APD','SHW','ECL','DD','PPG','NEM','FCX','NUE','DOW','ALB','CF'],
    'SPY': ['AAPL','NVDA','MSFT','AMZN','META','GOOGL','TSLA','BRK.B','AVGO','JPM','LLY','V'],
    'QQQ': ['AAPL','NVDA','MSFT','AMZN','META','GOOGL','TSLA','AVGO','COST','NFLX','AMD'],
    'IWM': ['SMCI','PLTR','AVAV','ESAB','ENSG','SFM','SAIA','BRBR','COOP','FN'],
    'SMH': ['NVDA','AVGO','TSM','AMAT','ASML','AMD','QCOM','KLAC','LRCX','MU','ADI','MRVL','MCHP','ON','TXN'],
    'SOXX': ['NVDA','AVGO','AMD','QCOM','AMAT','KLAC','LRCX','MU','ADI','MRVL','MCHP','ON','TXN','INTC','MPWR'],
    'ITA': ['GEV','LMT','RTX','NOC','BA','GD','HII','TDG','TXT','L3HT','MOOG','HEI'],
    'XAR': ['KTOS','RKLB','AVAV','HEI','TGI','DRS','CW','AXON','GEV','LMT','RTX'],
    'ARKK': ['TSLA','COIN','ROKU','SQ','TWLO','EXAS','BEAM','CRISPR','RXRX','PATH'],
    'ARKG': ['RXRX','PACB','CRSP','BEAM','NTLA','TDOC','VCYT','EXAS','FATE','SEER'],
    'CIBR': ['CRWD','PANW','OKTA','ZS','CYBR','S','TENB','VRNS','NET','FTNT','CSCO'],
    'BOTZ': ['NVDA','ISRG','ABB','FANUY','IRBT','AeroV','KLAC'],
    'AIQ':  ['NVDA','MSFT','GOOGL','META','AMZN','ORCL','CRM','BAIDU','SAP'],
    'QTUM': ['IONQ','RGTI','QUBT','QBTS','IBMQ','MSFT','GOOGL','NVDA','HONEYWELL'],
    'MAGS': ['AAPL','NVDA','MSFT','AMZN','META','GOOGL','TSLA'],
    'PAVE': ['VMC','MLM','ETN','PWR','FAST','GWW','NVR','PHM','URI','FERG'],
    'XBI':  ['RXRX','BEAM','CRSP','NTLA','ALNY','MRNA','VRTX','REGN','BIIB','SGEN'],
    'IBB':  ['ABBV','AMGN','GILD','REGN','VRTX','MRNA','BIIB','ILMN','ALNY'],
    'INDA': ['INFY','HDB','IBN','WIT','VEDL','SIFY','VNET'],
    'SKYY': ['AMZN','MSFT','GOOGL','CRM','ORCL','SNOW','DDOG','NET','CFLT','TWLO'],
    'ICLN': ['ENPH','FSLR','RUN','SEDG','PLUG','BE','ARRY','NOVA'],
    'TAN':  ['ENPH','FSLR','RUN','SEDG','ARRY','NOVA','SPWR','CSIQ'],
    'LIT':  ['ALB','SQM','LAC','LTHM','PLL','SGML'],
    'URA':  ['CCJ','NXE','DNN','UUUU','URG','PDN'],
    'COPX': ['FCX','SCCO','TECK','FM','IVN','ANTO'],
    'BLOK': ['COIN','MARA','RIOT','CLSK','HUT','BTBT','CIFR'],
    'FINX': ['V','MA','PYPL','SQ','AFRM','SOFI','UPST','HOOD','COIN','MQ'],
    'REMX': ['MP','LTHM','ALB','SQM','UUUU','SGML','NOVL'],
    'TUR':  ['AKBNK','GARAN','THYAO','TCELL','EREGL'],
    'NASA': ['RKLB','MNTS','ASTS','SPCE','MAXR','PL'],
    'UFO':  ['RKLB','PL','ASTS','SPCE','GSAT','VSAT'],
    'ARKX': ['RKLB','KTOS','IRDM','AVAV','AJRD','MAXR'],
    'CHAT': ['NVDA','MSFT','GOOGL','META','AMZN','ORCL','CRM','BAIDU'],
    'SHLD': ['LMT','RTX','PLTR','NOC','GD','KTOS','CACI','AXON','DFEN'],
    'IXN':  ['AAPL','NVDA','MSFT','AVGO','TSM','ASML','AMD','CRM'],
    'IXJ':  ['UNH','LLY','JNJ','ABBV','NVO','AZN','ROG'],
    'IXC':  ['XOM','CVX','SHEL','TTE','BP','EQNR'],
    'IXG':  ['JPM','BRK.B','BAC','WFC','GS','MS','HSBC'],
    'EEM':  ['TSM','BABA','TCEHY','SMSN','HDB','RELIANCE'],
    'EFA':  ['ASML','NVO','NESN','ROG','NOVN','SAP','LVMH','SONY'],
    'IWF':  ['AAPL','NVDA','MSFT','AMZN','META','GOOGL','LLY','AVGO'],
    'IWD':  ['BRK.B','JPM','XOM','JNJ','WMT','PG','BAC','CVX'],
    'TLT':  ['US30Y','TLH','GOVT'],  # bond ETF — no equity holdings
    'LQD':  [],  # bond ETF
    'HYG':  [],  # bond ETF
    'GLD':  [],  # gold ETF
    'IBIT': [],  # bitcoin ETF
    'SHY':  [],  # short treasury ETF
    'RSP':  ['AAPL','NVDA','MSFT','AMZN','META','GOOGL','JPM','V','UNH','XOM'],
    'IYT':  ['UPS','FDX','UNP','CSX','NSC','JBHT','ODFL','SAIA'],
    'MXI':  ['LIN','BHP','RIO','NEM','FCX','APD'],
    'KXI':  ['PG','NESN','NVO','MDLZ','KO','PEP','WMT'],
    'FINX': ['V','MA','PYPL','SQ','AFRM','SOFI','UPST'],
}

# ── Ticker validation ─────────────────────────────────────────────────────────
_TK_RE = re.compile(r'^[A-Z]{1,6}(\.[AB])?$')
def valid_tk(t):
    return bool(_TK_RE.match(str(t).strip()))

# ──────────────────────────────────────────────────────────────────────────────
# STEP 1 — Fetch real ETF holdings from Yahoo Finance (funds_data.top_holdings)
# ──────────────────────────────────────────────────────────────────────────────
print("Fetching real ETF holdings from Yahoo Finance...")
etf_holdings_map = {}   # etf -> [{t, n, w}, ...]
all_holding_tks  = set()

for etf in ETF_TICKERS:
    got_live = False
    try:
        fd = yf.Ticker(etf).funds_data
        if fd is not None:
            th = fd.top_holdings          # DataFrame: index=symbol, cols include holdingName, holdingPercent
            if th is not None and not th.empty:
                rows = []
                for sym, row in th.iterrows():
                    sym = str(sym).strip().upper()
                    if not valid_tk(sym) or sym == etf:
                        continue
                    # yfinance column names vary by version: 'Name'/'Holding Percent'
                    # (current) vs 'holdingName'/'holdingPercent' (older)
                    name = str(row.get('Name') or row.get('holdingName') or sym)
                    raw_pct = float(row.get('Holding Percent') or row.get('holdingPercent') or 0)
                    # Yahoo sometimes returns 0-1 fraction, sometimes 0-100 percentage
                    pct = raw_pct if raw_pct > 1 else raw_pct * 100
                    rows.append({'t': sym, 'n': name, 'w': round(pct, 2)})
                    all_holding_tks.add(sym)
                if rows:
                    etf_holdings_map[etf] = rows
                    got_live = True
                    print(f"  {etf}: {len(rows)} holdings from Yahoo Finance ✓")
    except Exception as ex:
        pass  # fall through to hardcoded

    if not got_live:
        # Use hardcoded fallback tickers
        fallback_tks = HARDCODED_HOLDINGS.get(etf, [])
        etf_holdings_map[etf] = [{'t': t, 'n': t, 'w': 0} for t in fallback_tks if valid_tk(t)]
        all_holding_tks.update(fallback_tks)
        src = 'hardcoded fallback' if fallback_tks else 'no equity holdings'
        print(f"  {etf}: {len(fallback_tks)} tickers ({src})")

    time.sleep(0.15)  # gentle rate limiting — Yahoo is free but don't hammer it

print(f"\nTotal unique holding tickers discovered: {len(all_holding_tks)}")

# ──────────────────────────────────────────────────────────────────────────────
# STEP 2 — Ratio signal computation (1-year data for SMA-20 / SMA-50)
# ──────────────────────────────────────────────────────────────────────────────
def classify(curr, s20, s50, inv=False):
    above20 = curr > s20
    s20_above_s50 = s20 > s50
    if above20 and s20_above_s50:            sig = "strong-bull"
    elif above20:                             sig = "bull"
    elif not above20 and not s20_above_s50:  sig = "strong-bear"
    else:                                     sig = "bear"
    if inv:
        flip = {"strong-bull":"strong-bear","bull":"bear","bear":"bull","strong-bear":"strong-bull"}
        sig = flip[sig]
    return sig

def sma(series, n):
    s = series[-min(n, len(series)):]
    return sum(s) / len(s)

ratio_tickers = list({r["num"] for r in ALL_R} | {r["den"] for r in ALL_R})
print(f"\nFetching {len(ratio_tickers)} ratio tickers (1y for SMA)...")

try:
    raw = yf.download(ratio_tickers, period="1y", interval="1d",
                      auto_adjust=True, progress=False, threads=True)
except Exception as e:
    print(f"Ratio download failed: {e}", file=sys.stderr)
    sys.exit(1)

closes = {}
if isinstance(raw.columns, pd.MultiIndex):
    close_df = raw["Close"]
    for t in ratio_tickers:
        if t in close_df.columns:
            s = close_df[t].dropna()
            if len(s) >= SMA_L + 5:
                closes[t] = s
else:
    t = ratio_tickers[0]
    s = raw["Close"].dropna()
    if len(s) >= SMA_L + 5:
        closes[t] = s

print(f"Got ratio data for {len(closes)}/{len(ratio_tickers)} tickers")

results = []
for r in ALL_R:
    num_t, den_t = r["num"], r["den"]
    if num_t not in closes or den_t not in closes:
        results.append({**r, "error": True}); continue
    num_s, den_s = closes[num_t], closes[den_t]
    common_idx = num_s.index.intersection(den_s.index)
    if len(common_idx) < SMA_L + 5:
        results.append({**r, "error": True}); continue
    ratio  = (num_s[common_idx] / den_s[common_idx]).values.tolist()
    curr   = ratio[-1]
    prev5  = ratio[max(0, len(ratio)-6)]
    s20    = sma(ratio, SMA_S)
    s50    = sma(ratio, SMA_L)
    cl     = classify(curr, s20, s50, r.get("inv", False))
    # Save last 22 ratio values for sparkline rendering in the frontend
    vals = [round(v, 6) for v in ratio[-22:]]
    results.append({**r, "error": False, "curr": round(curr,6), "s20": round(s20,6),
                    "s50": round(s50,6), "prev5": round(prev5,6), "cl": cl, "vals": vals})
    print(f"  {r['key']:12s} → {cl}")

# ──────────────────────────────────────────────────────────────────────────────
# STEP 2.5 — Download 1y closes for BP tickers not already fetched
# ──────────────────────────────────────────────────────────────────────────────
bp_need_1y = [t for t in ALL_BP_TICKERS if valid_tk(t) and t not in closes]
if bp_need_1y:
    print(f"\nFetching 1y closes for {len(bp_need_1y)} Best Performer tickers...")
    try:
        raw_bp = yf.download(bp_need_1y, period="1y", interval="1d",
                             auto_adjust=True, progress=False, threads=True)
        if isinstance(raw_bp.columns, pd.MultiIndex):
            bp_df = raw_bp["Close"]
            for t in bp_need_1y:
                if t in bp_df.columns:
                    s = bp_df[t].dropna()
                    if len(s) >= 25:
                        closes[t] = s
        elif len(bp_need_1y) == 1:
            s = raw_bp["Close"].dropna()
            if len(s) >= 25:
                closes[bp_need_1y[0]] = s
    except Exception as e:
        print(f"BP 1y fetch warning: {e}", file=sys.stderr)

# ──────────────────────────────────────────────────────────────────────────────
# STEP 2.6 — Compute BP scores: ETF/SPY relative strength + SMA20/50
# ──────────────────────────────────────────────────────────────────────────────
def compute_bp(ticker, spy_s):
    etf_s = closes.get(ticker)
    if etf_s is None or spy_s is None or len(etf_s) < 25:
        return None
    common = etf_s.index.intersection(spy_s.index)
    if len(common) < 25:
        return None
    ratio = (etf_s[common] / spy_s[common]).values.tolist()
    curr  = ratio[-1]
    s20   = sma(ratio, 20)
    s50   = sma(ratio, min(50, len(ratio)))
    pct   = (curr - s20) / s20 * 100
    prev5 = ratio[max(0, len(ratio) - 6)]
    chg5  = (curr - prev5) / prev5 * 100
    bullish = curr > s20
    if   curr > s20 and s20 > s50: sig = "strong-bull"
    elif curr > s20:                sig = "bull"
    elif s20 < s50:                 sig = "strong-bear"
    else:                           sig = "bear"
    etf_price = float(etf_s.iloc[-1])
    return {
        "curr":     round(curr, 6),
        "s20":      round(s20, 6),
        "s50":      round(s50, 6),
        "pct":      round(pct, 3),
        "chg5":     round(chg5, 3),
        "sig":      sig,
        "bullish":  bullish,
        "closes":   [round(v, 6) for v in ratio[-20:]],
        "etfPrice": round(etf_price, 2),
    }

spy_s = closes.get('SPY')
bp_scores = {}
if spy_s is not None:
    for grp, tickers in BP_GROUPS.items():
        for tk in tickers:
            score = compute_bp(tk, spy_s)
            if score:
                bp_scores[tk] = score
    print(f"BP scores: {len(bp_scores)}/{sum(len(v) for v in BP_GROUPS.values())} ETFs computed")
else:
    print("WARNING: SPY closes not available — BP scores skipped")

# ──────────────────────────────────────────────────────────────────────────────
# STEP 3 — Price download for all ETFs + holdings + leveraged ETFs (5d, fast)
# ──────────────────────────────────────────────────────────────────────────────
# Tickers shown in the dashboard's static top-10 holdings tables that may not
# appear in Yahoo's live topHoldings (so they'd otherwise have no price).
STATIC_PAGE_TICKERS = [
 'AAON','ABB','ABT','ACM','ACN','ADBE','ADI','AEIS','AES','AI','AIR','AMBA','AMC','AME','AON','APOG',
 'ARE','ARQT','ARRY','ATEN','AVB','AXON','AZN','BAH','BAKKT','BALL','BBY','BDX','BEP','BHP','BIDU','BLK',
 'BMY','BNTX','BOX','BP','BRK.B','BSX','BTBT','CACI','CAG','CC','CCJ','CCO','CDNA','CDNS','CE','CELH',
 'CEVA','CF','CFLT','CGNX','CHD','CHKP','CHTR','CI','CMCSA','CME','CMG','CNP','COF','COHU','CPB','CRM',
 'CSIQ','CSWI','CTAS','CVS','CYBR','DCO','DD','DECK','DGHI','DHR','DKNG','DNN','DOW','DQ','DRS','DVN',
 'EB','ECL','ED','EFR','EL','ELV','EME','EMR','ENTG','EQNR','EQR','ES','ESLT','ESTC','EU','EVRG','EWJ',
 'EXAS','EXC','EXR','F','FANG','FATE','FE','FI','FIX','FORM','FOXA','FSLY','GEHC','GEN','GIS','GOLD',
 'GRMN','GTLB','GVA','HAL','HBM','HES','HLT','HRL','HSBC','HSY','HUBS','HWC','ICE','IDCC','IESC','IFF',
 'INFY','INVH','IP','IPG','IRM','IVN','J','JBHT','JCI','JOBY','KFRC','KHC','KMI','KRE','LDOS','LNG',
 'LNT','LUV','LYB','MAA','MARA','MDB','MDT','MDU','MET','MKC','MKSI','MLM','MPWR','MRCY','MRNA','MSTR',
 'MTCH','MYRG','NEO','NFLX','NI','NKE','NNN','NOW','NRG','NTLA','NVR','NVS','NWSA','NXE','OKE','ONTO',
 'OXY','PACB','PARA','PATH','PCAR','PDN','PH','PKG','PLS','PLXS','PNC','PNW','PPG','PPL','PRCT','QBTS',
 'QLYS','QUBT','RARE','RCUS','RGEN','RGTI','RH','RIOT','RMBS','ROAD','ROP','RPD','RPM','RSG','RXRX','S',
 'SAIA','SAIC','SAIL','SAN','SBAC','SHEL','SJM','SLAB','SMCI','SMPL','SNOW','SNPS','SOUN','SPCE','SPGI',
 'SPHB','SPIR','SPOT','SPR','SPSC','SQ','SRRK','STZ','SWKS','SYK','T','TAP','TEAM','TENB','TGT','TKO',
 'TMUS','TREX','TRGP','TRMB','TRV','TTE','TWLO','TXT','UDR','UFPI','UL','USB','UUUU','VALE','VCYT',
 'VRNS','VRRM','VZ','WEC','WOLF','YUM','ZBRA','ZM','ZS','ZTS','EFZ','QLD','UTSL',
]

all_price_tks = sorted(set(
    t for t in list(all_holding_tks) + ETF_TICKERS + LEVERAGED_TICKERS + STATIC_PAGE_TICKERS
    if valid_tk(t)
))
# Skip tickers already in closes (1y data → reuse)
need_5d = [t for t in all_price_tks if t not in closes]
price_closes = dict(closes)

if need_5d:
    print(f"\nFetching prices for {len(need_5d)} tickers (5d)...")
    try:
        raw2 = yf.download(need_5d, period="5d", interval="1d",
                           auto_adjust=True, progress=False, threads=True)
        if isinstance(raw2.columns, pd.MultiIndex):
            c2 = raw2["Close"]
            for t in need_5d:
                if t in c2.columns:
                    s = c2[t].dropna()
                    if len(s) >= 2:
                        price_closes[t] = s
        elif len(need_5d) == 1:
            s = raw2["Close"].dropna()
            if len(s) >= 2:
                price_closes[need_5d[0]] = s
    except Exception as e:
        print(f"5d price fetch warning: {e}", file=sys.stderr)

# ──────────────────────────────────────────────────────────────────────────────
# STEP 4 — Compute ticker_prices {ticker: {p, c}}
# ──────────────────────────────────────────────────────────────────────────────
ticker_prices = {}
for tk in all_price_tks:
    s = price_closes.get(tk)
    if s is None or len(s) < 2:
        continue
    try:
        price = float(s.iloc[-1])
        prev  = float(s.iloc[-2])
        if prev <= 0 or price != price or prev != prev:   # NaN guard
            continue
        ticker_prices[tk] = {"p": round(price, 2), "c": round((price/prev - 1)*100, 2)}
    except Exception:
        pass

print(f"ticker_prices: {len(ticker_prices)} tickers with price data")

# ──────────────────────────────────────────────────────────────────────────────
# STEP 4.5 — Correct prices via Yahoo spark quote meta (authoritative).
# The daily-bar download sometimes has a null close for the latest session
# (e.g. DAL 2026-06-10), which silently falls back to a stale bar. The spark
# meta carries regularMarketPrice + chartPreviousClose and is always current.
# ──────────────────────────────────────────────────────────────────────────────
import urllib.request as _ur
import json as _json

def _spark_chunk(symbols):
    url = ("https://query1.finance.yahoo.com/v7/finance/spark?symbols="
           + ",".join(symbols) + "&range=1d&interval=1d")
    req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _ur.urlopen(req, timeout=20) as r:
        return _json.load(r)

corrected = 0
spark_fail = 0
day_hilo = {}   # ticker -> (day_low, day_high) for wick-accurate setup tracking
for i in range(0, len(all_price_tks), 20):
    chunk = all_price_tks[i:i+20]
    try:
        js = _spark_chunk(chunk)
        for res in (js.get("spark", {}).get("result") or []):
            try:
                meta = res["response"][0]["meta"]
                tk = meta["symbol"]
                p = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose")
                if not p or not prev or prev <= 0:
                    continue
                new = {"p": round(float(p), 2), "c": round((float(p)/float(prev) - 1)*100, 2)}
                if ticker_prices.get(tk) != new:
                    corrected += 1
                ticker_prices[tk] = new
                dl, dh = meta.get("regularMarketDayLow"), meta.get("regularMarketDayHigh")
                if dl and dh and dl > 0:
                    day_hilo[tk] = (float(dl), float(dh))
            except Exception:
                pass
    except Exception as e:
        spark_fail += 1
        if spark_fail <= 3:
            print(f"spark chunk warning: {e}", file=sys.stderr)

print(f"spark correction: {corrected} prices updated, {spark_fail} chunks failed")

# ──────────────────────────────────────────────────────────────────────────────
# STEP 4.7 — Today's Setups scan: SMA/ATR/volume/RS analytics for every stock,
# market internals, and pre-classified swing-trade candidates.
# ──────────────────────────────────────────────────────────────────────────────
SECTOR_ETFS = ['XLK','XLF','XLE','XLV','XLI','XLC','XLU','XLY','XLP','XLRE','XLB']
THEME_ETFS  = [e for e in ETF_TICKERS if e not in SECTOR_ETFS and e not in
               ('SPY','RSP','SHY','TLT','LQD','HYG','GLD','IWF','IWD')]

# stock → parent ETF (sectors take priority over themes)
stock_parent = {}
for etf in SECTOR_ETFS + THEME_ETFS:
    for h in etf_holdings_map.get(etf, []):
        stock_parent.setdefault(h['t'], etf)

# Tickers NOT tradeable on GK broker -> kept out of the entire setups system
# (universe scan, watchlist, alerts, website). Add more here as needed.
EXCLUDE_TICKERS = {"XEL", "HASI"}
stock_tks = sorted(set(stock_parent) - set(ETF_TICKERS) - set(LEVERAGED_TICKERS) - EXCLUDE_TICKERS)
print(f"\nSetups scan: {len(stock_tks)} stocks across {len(set(stock_parent.values()))} parent ETFs")

setups_out = {"internals": {}, "list": [], "scanned": 0}
kv_prev_ok = False   # True only once the previous book is read from KV without error
try:
    raw3 = yf.download(stock_tks + ETF_TICKERS, period="3mo", interval="1d",
                       auto_adjust=True, progress=False, threads=True)
    cl3, hi3, lo3, vo3 = raw3["Close"], raw3["High"], raw3["Low"], raw3["Volume"]

    def series_of(frame, t):
        try:
            s = frame[t].dropna()
            return s if len(s) >= 25 else None
        except Exception:
            return None

    def ret20(t):
        s = series_of(cl3, t)
        if s is None or len(s) < 21: return None
        return (float(s.iloc[-1]) / float(s.iloc[-21]) - 1) * 100

    etf_ret20 = {e: ret20(e) for e in ETF_TICKERS}
    spy_r20 = etf_ret20.get('SPY')

    stocks_above_s20 = 0; stocks_total = 0; new_highs = 0; new_lows = 0
    universe = []
    for t in stock_tks:
        s = series_of(cl3, t)
        if s is None: continue
        closes = [float(x) for x in s]
        price = ticker_prices.get(t, {}).get('p') or closes[-1]
        chg   = ticker_prices.get(t, {}).get('c', 0)
        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
        if sma50 is None: continue
        hi = series_of(hi3, t); lo = series_of(lo3, t); vo = series_of(vo3, t)
        # ATR14 (true range needs aligned H/L/C)
        atr_pct = None
        if hi is not None and lo is not None:
            h = [float(x) for x in hi[-15:]]; l = [float(x) for x in lo[-15:]]
            c = closes[-16:]
            if len(h) >= 14 and len(l) >= 14 and len(c) >= 15:
                trs = [max(h[i]-l[i], abs(h[i]-c[i]), abs(l[i]-c[i])) for i in range(1, min(len(h), len(l), len(c)-1))]
                if trs: atr_pct = round(sum(trs[-14:]) / len(trs[-14:]) / price * 100, 2)
        vol_ratio = None
        if vo is not None and len(vo) >= 21:
            v = [float(x) for x in vo]
            avg20 = sum(v[-21:-1]) / 20
            if avg20 > 0: vol_ratio = round(v[-1] / avg20, 2)
        hi3m = max(closes); lo3m = min(closes)
        near_high = price >= hi3m * 0.98
        near_low  = price <= lo3m * 1.02
        d20 = (price / sma20 - 1) * 100
        d50 = (price / sma50 - 1) * 100
        stocks_total += 1
        if price > sma20: stocks_above_s20 += 1
        if near_high: new_highs += 1
        if near_low: new_lows += 1

        parent = stock_parent.get(t)
        bp = bp_scores.get(parent) or {}
        p_r20 = etf_ret20.get(parent)
        s_r20 = ret20(t)
        if s_r20 is None or p_r20 is None: continue
        rs_sector  = round(s_r20 - p_r20, 2)            # stock vs own ETF, 20d
        sector_rs  = round(p_r20 - spy_r20, 2) if spy_r20 is not None else 0  # ETF vs SPY

        sec_bull = bool(bp.get('bullish'))
        up = sma20 > sma50; down = sma20 < sma50

        # ── Tradeability guards (win-rate filters) ────────────────────────────
        # price < $5: spread/manipulation risk. ATR > 8%: stop too wide to swing.
        # |day move| > 5%: event-driven (earnings/news) — no edge in the setup.
        if price < 5: continue
        if atr_pct is None or atr_pct > 8: continue
        if abs(chg) > 5: continue

        universe.append({
            "t": t, "etf": parent, "p": price, "c": chg,
            "s20": sma20, "s50": sma50, "d20": d20, "d50": d50,
            "atr": atr_pct, "vr": vol_ratio,
            "rsS": rs_sector, "rsE": sector_rs,
            "hi3m": hi3m, "lo3m": lo3m,
            "sec_bull": sec_bull, "up": up, "down": down,
        })

    # ── Two-pass classification: strict (A-quality windows) first, then a
    # "near-miss" pass with slightly wider windows to fill each line to 4. ──
    def classify(m, loose):
        d20, rs, p = m["d20"], m["rsS"], m["p"]
        nh = p >= m["hi3m"] * (0.96 if loose else 0.98)
        nl = p <= m["lo3m"] * (1.04 if loose else 1.02)
        pbL, pbH   = (-4, 2)   if loose else (-2.5, 1)    # pullback window
        rpL, rpH   = (-2, 4)   if loose else (-1, 2.5)    # rip window
        ldH        = 11        if loose else 8            # leader extension cap
        lgL        = -11       if loose else -8           # laggard capitulation cap
        rsMin      = 2         if loose else 3            # RS threshold for breakout types
        if m["sec_bull"] and m["up"] and rs > 0 and pbL <= d20 <= pbH and p > m["s50"]:
            return 'pullback_long'
        if (not m["sec_bull"]) and m["down"] and rs < 0 and rpL <= d20 <= rpH and p < m["s50"]:
            return 'rip_short'
        if m["sec_bull"] and rs > rsMin and nh and m["up"] and 0 <= d20 <= ldH:
            return 'rs_leader'
        if (not m["sec_bull"]) and rs < -rsMin and nl and m["down"] and lgL <= d20 <= 0:
            return 'rs_laggard'
        return None

    def score_of(m, typ, loose):
        # Mean-reversion-to-trend entries carry the higher win rate → priority.
        # Volume must CONFIRM: quiet pullback/rip (≤1.1×) healthy; loud
        # breakout/breakdown (≥1.5×) is conviction. Near-misses pay a penalty.
        vr = m["vr"] or 1.0
        s = abs(m["rsS"]) + abs(m["rsE"]) * 0.5
        if typ in ('pullback_long', 'rip_short'):
            s += 2.0
            s += 1.5 if vr <= 1.1 else (-1.0 if vr >= 1.8 else 0)
        else:
            s += 1.5 if vr >= 1.5 else (-0.5 if vr < 0.7 else 0)
        if loose: s -= 1.5
        return round(s, 2)

    def add_trading_days(dt, n):
        """dt + n trading sessions (weekends skipped; holidays ignored —
        close enough for setup expiry, and always errs on the early side)."""
        cur, added = dt, 0
        while added < n:
            cur += timedelta(days=1)
            if cur.weekday() < 5:
                added += 1
        return cur

    def trading_days_between(a_str, b_str):
        """Trading sessions from date a to date b (YYYY-MM-DD strings)."""
        try:
            a = datetime.strptime(a_str, "%Y-%m-%d").date()
            b = datetime.strptime(b_str, "%Y-%m-%d").date()
        except Exception:
            return 0
        n, cur = 0, a
        while cur < b:
            cur += timedelta(days=1)
            if cur.weekday() < 5:
                n += 1
        return n

    def trade_plan(m, typ):
        """Entry/stop/T1/T2 computed server-side so the tracker scores exactly
        what was published. Entry is a resting limit at a level, never market.
        Stop = 2×ATR from entry (house rule). T1 = 1.5R (sell half, stop→BE).
        T2 = 3-mo extreme if it pays ≥2R, else a synthetic 2.5R extension."""
        p, s20 = m["p"], m["s20"]
        atr_abs = (m["atr"] or 2.0) / 100.0 * p
        long_side = typ in ('pullback_long', 'rs_leader')
        if typ == 'pullback_long':
            if p > s20 * 1.002: entry, trig = s20, 'limit at SMA20 support — wait for the dip'
            else: entry, trig = p - 0.3 * atr_abs, 'limit 0.3×ATR under the print — let the wick fill you'
        elif typ == 'rip_short':
            if p < s20 * 0.998: entry, trig = s20, 'limit on spike into falling SMA20'
            else: entry, trig = p + 0.3 * atr_abs, 'limit 0.3×ATR above the print — sell the wick'
        elif typ == 'rs_leader':
            entry, trig = max(s20, p - 0.5 * atr_abs), 'limit on 0.5×ATR intraday dip'
        else:  # rs_laggard
            entry, trig = min(s20, p + 0.5 * atr_abs), 'limit on 0.5×ATR bounce'
        risk = 2 * atr_abs
        stop = entry - risk if long_side else entry + risk
        t1 = entry + 1.5 * risk if long_side else entry - 1.5 * risk
        if long_side:
            structural = m["hi3m"] >= entry + 2 * risk
            t2 = m["hi3m"] if structural else entry + 2.5 * risk
            t2b = '3-mo high' if structural else '2.5R ext'
        else:
            structural = m["lo3m"] <= entry - 2 * risk
            t2 = m["lo3m"] if structural else entry - 2.5 * risk
            t2b = '3-mo low' if structural else '2.5R ext'
        return {
            "side": "long" if long_side else "short",
            "entry": round(entry, 2), "stop": round(stop, 2),
            "t1": round(t1, 2), "t2": round(t2, 2), "risk": round(risk, 4),
            "t2b": t2b, "trig": trig,
            # 5 trading sessions = one real market week; a Friday setup no
            # longer loses 2 of its 7 calendar days to the weekend
            "expires": add_trading_days(datetime.now(timezone.utc), 5).strftime("%Y-%m-%d"),
        }

    def emit(m, typ, loose):
        rec = {
            "t": m["t"], "etf": m["etf"], "type": typ,
            "p": round(m["p"], 2), "c": m["c"],
            "s20": round(m["s20"], 2), "s50": round(m["s50"], 2),
            "d20": round(m["d20"], 2), "d50": round(m["d50"], 2),
            "atr": m["atr"], "vr": m["vr"], "rsS": m["rsS"], "rsE": m["rsE"],
            "hi3m": round(m["hi3m"], 2), "lo3m": round(m["lo3m"], 2),
            "score": score_of(m, typ, loose), "nm": 1 if loose else 0,
        }
        rec.update(trade_plan(m, typ))
        return rec

    PER_TYPE_TARGET = 4
    strict = []
    for m in universe:
        typ = classify(m, loose=False)
        if typ: strict.append(emit(m, typ, False))
    strict.sort(key=lambda x: -x["score"])
    per_type, final, taken = {}, [], set()
    for cnd in strict:
        if per_type.get(cnd["type"], 0) >= PER_TYPE_TARGET: continue
        per_type[cnd["type"]] = per_type.get(cnd["type"], 0) + 1
        final.append(cnd); taken.add(cnd["t"])
    # near-miss fill
    loose_pool = []
    for m in universe:
        if m["t"] in taken: continue
        typ = classify(m, loose=True)
        if typ and per_type.get(typ, 0) < PER_TYPE_TARGET:
            loose_pool.append(emit(m, typ, True))
    loose_pool.sort(key=lambda x: -x["score"])
    for cnd in loose_pool:
        if per_type.get(cnd["type"], 0) >= PER_TYPE_TARGET: continue
        per_type[cnd["type"]] = per_type.get(cnd["type"], 0) + 1
        final.append(cnd); taken.add(cnd["t"])

    # ── Setup tracker: every published setup is logged and scored on later
    # refreshes. History persists INSIDE data.json (read old → advance → write).
    def advance_setup(s, price, lo, hi, today_str):
        """Advance one tracked setup's lifecycle using the day's LOW/HIGH so
        intraday wicks count (a snapshot-only check misses fills and stops
        between refreshes). Mutates and returns s.
        pending → triggered (limit touched by the wick) | expired
        triggered → stopped (-1R) | t1 (half off at 1.5R, stop→breakeven)
        t1 → t2 (full win, r=(1.5+rr2)/2) | be (rest flat, r=+0.75)
        Tie-breaks are CONSERVATIVE: if both stop and target were touched the
        same day (order unknowable from hi/lo), the stop wins; after T1, the
        breakeven exit wins over T2. The track record can only understate.
        triggered older than 15 trading sessions → timeout at market R."""
        long_side = s["side"] == "long"
        if s["status"] == "pending":
            if today_str > s["expires"]:
                s["status"] = "expired"; s["closed"] = today_str; return s
            filled = (lo <= s["entry"]) if long_side else (hi >= s["entry"])
            if filled:
                s["status"] = "triggered"; s["trigDate"] = today_str
        if s["status"] == "triggered":
            # timeout after 15 trading sessions (~3 market weeks), not
            # calendar days — weekends no longer eat into the trade's clock
            age = trading_days_between(s.get("trigDate", today_str), today_str)
            stop_hit = (lo <= s["stop"]) if long_side else (hi >= s["stop"])
            t1_hit   = (hi >= s["t1"])  if long_side else (lo <= s["t1"])
            if stop_hit:   # conservative: stop wins a same-day tie with T1
                s["status"] = "stopped"; s["r"] = -1.0; s["closed"] = today_str; return s
            if t1_hit:
                s["status"] = "t1"; s["t1Date"] = today_str
            elif age > 15:
                mr = (price - s["entry"]) / s["risk"] * (1 if long_side else -1)
                s["status"] = "timeout"; s["r"] = round(mr, 2); s["closed"] = today_str; return s
        if s["status"] == "t1":
            be_hit = (lo <= s["entry"]) if long_side else (hi >= s["entry"])
            t2_hit = (hi >= s["t2"])    if long_side else (lo <= s["t2"])
            if be_hit:     # conservative: BE exit wins a same-day tie with T2
                s["status"] = "be"; s["r"] = 0.75; s["closed"] = today_str
            elif t2_hit:
                rr2 = abs(s["t2"] - s["entry"]) / s["risk"]
                s["status"] = "t2"; s["r"] = round((1.5 + rr2) / 2, 2); s["closed"] = today_str
        return s

    prev_hist = []
    # Setups now live in Cloudflare KV (paywalled), NOT the public data.json — so
    # the tracker must read its previous state from KV to carry open/triggered
    # positions forward across runs. Falls back to data.json for local dev runs.
    _kt = os.environ.get("CF_KV_TOKEN"); _ka = os.environ.get("CF_ACCOUNT_ID"); _kn = os.environ.get("CF_KV_NS")
    if _kt and _ka and _kn:
        try:
            import urllib.request as _ureq
            _u = f"https://api.cloudflare.com/client/v4/accounts/{_ka}/storage/kv/namespaces/{_kn}/values/latest"
            _r = _ureq.Request(_u, headers={"Authorization": f"Bearer {_kt}", "User-Agent": "Mozilla/5.0"})
            prev_hist = (json.load(_ureq.urlopen(_r, timeout=20)).get("hist")) or []
            kv_prev_ok = True   # read succeeded — safe to write the carried-forward book back
            print(f"   Prev setups from KV: {len(prev_hist)} hist rows")
        except Exception as e:
            print(f"prev setups from KV failed (non-fatal): {e}", file=sys.stderr)
    if not prev_hist:
        try:
            with open("data.json") as _pf:
                prev_hist = (json.load(_pf).get("setups") or {}).get("hist") or []
        except Exception:
            pass
    prev_hist = [s for s in prev_hist if s.get("t") not in EXCLUDE_TICKERS]  # drop excluded tickers from the carried-forward open book
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    OPEN_STATES = ("pending", "triggered", "t1")
    for s in prev_hist:
        if s.get("status") in OPEN_STATES and all(k in s for k in ("side","entry","stop","t1","t2","risk","expires")):
            tp = ticker_prices.get(s.get("t"))
            if tp:
                lo, hi = day_hilo.get(s["t"], (tp["p"], tp["p"]))
                # Creation day: the day's wicks predate the setup, so a fill or
                # stop "hit" by a pre-publication wick would be fiction. Use the
                # live snapshot only; full wick accuracy starts the next session.
                if s.get("created") == today_str:
                    lo = hi = tp["p"]
                advance_setup(s, tp["p"], lo, hi, today_str)
    open_keys = {(s.get("t"), s.get("type")) for s in prev_hist if s.get("status") in OPEN_STATES}
    # Market context frozen at publication — the self-evaluation layer needs
    # to know what the tape looked like when each idea was issued, with no
    # possibility of hindsight (these numbers are computed BEFORE the outcome).
    mkt_ctx = {
        "pa20": round(stocks_above_s20 / stocks_total * 100, 1) if stocks_total else None,
        "hl": new_highs - new_lows,
        "secBull": sum(1 for e in SECTOR_ETFS if (bp_scores.get(e) or {}).get('bullish')),
    }
    for cnd in final[:16]:
        if (cnd["t"], cnd["type"]) in open_keys: continue
        rec = {k: cnd.get(k) for k in ("t","etf","type","nm","side","entry","stop","t1","t2",
                                       "risk","expires","score","atr","vr","rsS","rsE","d20","t2b")}
        # cts = exact publication timestamp (ms) — anchors the TradingView box
        # to the real moment the setup appeared, on any chart timeframe
        rec.update({"created": today_str, "cts": int(time.time() * 1000),
                    "status": "pending", "mkt": mkt_ctx})
        prev_hist.append(rec); open_keys.add((cnd["t"], cnd["type"]))
    # ── Permanent archive: EVERY published proposal lands here when it
    # resolves (stopped / t2 / be / timeout / expired) — nothing is ever
    # deleted, unlike the 35-day window inside data.json. Each record keeps
    # its full lifecycle (created→trigDate→t1Date→closed, final R) plus the
    # publication-time features (score/atr/vr/RS/mkt) AND the daily OHLC path
    # of the trade, so future versions of the system can replay every trade
    # against alternative rules (different stops, targets, entries).
    try:
        try:
            arch = json.load(open("archive.json"))
        except Exception:
            arch = []
        arch = [a for a in arch if a.get("t") not in EXCLUDE_TICKERS]   # scrub excluded tickers from trade history
        akeys = {(a.get("t"), a.get("type"), a.get("created")) for a in arch}
        new_arch = 0
        for s in prev_hist:
            if s.get("status") in OPEN_STATES: continue
            k = (s.get("t"), s.get("type"), s.get("created"))
            if k in akeys: continue
            rec = dict(s)
            try:
                o4, c4 = raw3["Open"][s["t"]], cl3[s["t"]]
                h4, l4 = hi3[s["t"]], lo3[s["t"]]
                path = []
                for idx in c4.index:
                    dstr = idx.strftime("%Y-%m-%d")
                    if not (s.get("created", "") <= dstr <= s.get("closed", "9999")):
                        continue
                    bar = [float(o4.get(idx)), float(h4.get(idx)),
                           float(l4.get(idx)), float(c4.get(idx))]
                    if any(v != v for v in bar):   # NaN guard
                        continue
                    path.append([dstr] + [round(v, 2) for v in bar])
                if path:
                    rec["path"] = path
            except Exception:
                pass
            arch.append(rec); akeys.add(k); new_arch += 1
        if new_arch:
            json.dump(arch, open("archive.json", "w"), separators=(",", ":"))
            # the workflow's commit step only re-adds data.json — stage the
            # archive here so it rides along in the same data commit
            if os.environ.get("GITHUB_ACTIONS") == "true":
                subprocess.run(["git", "add", "archive.json"], check=False)
            print(f"Archive: +{new_arch} resolved setups (total {len(arch)})")
    except Exception as e:
        print(f"Archive warning (non-fatal): {e}", file=sys.stderr)

    # ── STEP 4.8 — Self-evaluation advisor ────────────────────────────────────
    # Replays every archived trade on its stored daily price path under
    # ALTERNATIVE rules (tighter/wider stop, closer entries, different T1,
    # no breakeven move) and turns statistically-backed differences into
    # written proposals. ADVICE ONLY: nothing here ever modifies the live
    # strategy — GK reads the report and confirms changes by hand.
    def _replay(tr, stop_mult=2.0, t1_r=1.5, be_move=True, market_entry=False):
        """Counterfactual outcome of one archived trade, in R units of the
        VARIANT risk. Same conservative tie-breaks as the live tracker:
        stop beats T1 on the same bar, breakeven beats T2 after T1.
        Returns None if the variant never fills or data is missing."""
        path = tr.get("path") or []
        if not path or not tr.get("risk") or not tr.get("entry"):
            return None
        long_side = tr.get("side") == "long"
        risk_v = (tr["risk"] / 2.0) * stop_mult     # live risk = 2×ATR
        if risk_v <= 0:
            return None
        entry = path[0][4] if market_entry else tr["entry"]
        d = 1 if long_side else -1
        stop = entry - d * risk_v
        t1 = entry + d * t1_r * risk_v
        t2 = tr.get("t2")
        state = "in" if market_entry else "wait"
        for _, o, h, l, c in path:
            if state == "wait":
                if (l <= entry) if long_side else (h >= entry):
                    state = "in"          # fall through: stop checked same bar
                else:
                    continue
            if state == "in":
                if (l <= stop) if long_side else (h >= stop):
                    return -1.0
                if (h >= t1) if long_side else (l <= t1):
                    state = "t1" if be_move else "run"
                else:
                    continue
            if state == "t1":
                if (l <= entry) if long_side else (h >= entry):
                    return round(t1_r / 2, 3)        # half banked, half at BE
                if t2 is not None and ((h >= t2) if long_side else (l <= t2)):
                    return round((t1_r + abs(t2 - entry) / risk_v) / 2, 3)
            elif state == "run":
                if (l <= stop) if long_side else (h >= stop):
                    return -1.0
                if t2 is not None and ((h >= t2) if long_side else (l <= t2)):
                    return round(abs(t2 - entry) / risk_v, 3)
        if state == "wait":
            return None                              # variant never filled
        mr = (path[-1][4] - entry) / risk_v * d      # mark-to-last-close
        if state == "t1":
            return round((t1_r + max(mr, 0.0)) / 2, 3)
        return round(mr, 3)

    advisor = {"asof": today_str, "findings": [], "status": "collecting"}
    try:
        try:
            arch_all = json.load(open("archive.json"))
        except Exception:
            arch_all = []
        arch_all = [a for a in arch_all if a.get("t") not in EXCLUDE_TICKERS]   # exclude from advisor history
        RES_STATES = ("stopped", "t2", "be", "timeout")
        resolved = [a for a in arch_all if a.get("status") in RES_STATES]
        trig_res = [a for a in resolved if a.get("path")]
        expired_p = [a for a in arch_all if a.get("status") == "expired" and a.get("path")]
        advisor.update({"nArchived": len(arch_all), "nResolved": len(resolved),
                        "nExpired": sum(1 for a in arch_all if a.get("status") == "expired")})
        F = advisor["findings"]
        mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None

        # 0. Trust metric: the replay engine must reproduce reality before its
        # counterfactuals deserve any weight (±0.35R tolerance: replay sees
        # full daily bars where the live tracker saw a snapshot on day one).
        chk = [(a["r"], _replay(a)) for a in trig_res if a.get("r") is not None]
        chk = [(ar, rr) for ar, rr in chk if rr is not None]
        if chk:
            advisor["replayCheck"] = {"n": len(chk),
                                      "match": sum(1 for ar, rr in chk if abs(ar - rr) <= 0.35)}

        # 1. Stop width + T1 distance + breakeven rule (need 20 closed trades)
        if len(trig_res) >= 20:
            def variant_delta(**kw):
                pairs = [(_replay(a), _replay(a, **kw)) for a in trig_res]
                pairs = [(b, v) for b, v in pairs if b is not None and v is not None]
                if len(pairs) < 20: return None, 0
                return round(mean([v for _, v in pairs]) - mean([b for b, _ in pairs]), 2), len(pairs)
            for kw, title, action in (
                ({"stop_mult": 1.5}, "Tighter stop pays", "Propose stop 1.5×ATR instead of 2×ATR"),
                ({"stop_mult": 2.5}, "Wider stop pays", "Propose stop 2.5×ATR instead of 2×ATR"),
                ({"t1_r": 1.0}, "Earlier first target pays", "Propose T1 at 1R instead of 1.5R"),
                ({"t1_r": 2.0}, "Later first target pays", "Propose T1 at 2R instead of 1.5R"),
                ({"be_move": False}, "Skipping the breakeven move pays", "Propose holding full stop after T1 (no BE move)"),
            ):
                dr, n = variant_delta(**kw)
                if dr is not None and dr >= 0.15:
                    F.append({"sev": "act", "title": title, "dr": dr, "n": n,
                              "ev": f"Replaying all {n} closed trades with this one change moves expectancy by {dr:+}R per trade. Same entries, same conservative tie-breaks — only this rule differs.",
                              "action": action})

        # 2. Entry proximity — two independent lines of evidence
        if len(expired_p) >= 10:
            hyp = [r for r in (_replay(a, market_entry=True) for a in expired_p) if r is not None]
            if len(hyp) >= 10:
                m = mean(hyp)
                if m is not None and m >= 0.3:
                    F.append({"sev": "act", "title": "Expired setups were winners you missed", "dr": m, "n": len(hyp),
                              "ev": f"{len(hyp)} setups expired untriggered. Entering those at market on day one (same stop/targets) would have averaged {m:+}R within the setup window.",
                              "action": "Propose entries closer to market: 0.2×ATR offsets instead of 0.3–0.5×ATR, or market-on-open for A-grades"})
                elif m is not None and m <= -0.2:
                    F.append({"sev": "info", "title": "Letting setups expire is saving money", "dr": m, "n": len(hyp),
                              "ev": f"Hypothetical market entries on the {len(hyp)} expired setups would have averaged {m:+}R. The resting-limit discipline is filtering out losers.",
                              "action": "Keep resting limits exactly as they are"})
        if len(resolved) + advisor["nExpired"] >= 15:
            tr_rate = round(len(resolved) / (len(resolved) + advisor["nExpired"]) * 100, 1)
            advisor["trigRate"] = tr_rate
            if tr_rate < 35:
                F.append({"sev": "watch", "title": "Most setups never trigger", "n": len(resolved) + advisor["nExpired"],
                          "ev": f"Only {tr_rate}% of archived setups ever filled. Entries may be parked too deep below/above the market.",
                          "action": "Consider smaller limit offsets (entries nearer to the market price)"})
            elif tr_rate > 85:
                F.append({"sev": "watch", "title": "Nearly everything triggers", "n": len(resolved) + advisor["nExpired"],
                          "ev": f"{tr_rate}% of archived setups filled — limits this close to the print behave like market orders (no pullback edge captured).",
                          "action": "Consider deeper limit offsets, or require a level (SMA20) instead of an ATR offset"})
        if len(trig_res) >= 15:
            fast_stop = [a for a in trig_res if a.get("status") == "stopped"
                         and trading_days_between(a.get("trigDate", ""), a.get("closed", "")) <= 2]
            fr = round(len(fast_stop) / len(trig_res) * 100, 1)
            if fr >= 40:
                F.append({"sev": "watch", "title": "Stops dying within 2 sessions", "n": len(trig_res),
                          "ev": f"{fr}% of triggered trades hit the stop within 2 sessions of filling — fills are catching falling knives, not pullbacks.",
                          "action": "Propose entry confirmation (e.g. fill only if the day closes back above the level) or wider 2.5×ATR stop"})

        # 3. Per-type edge (10 closed per type to speak, 20 to act)
        by_t = {}
        for a in resolved:
            by_t.setdefault(a.get("type", "?"), []).append(a.get("r") or 0)
        for typ, rs in by_t.items():
            if len(rs) < 10: continue
            m = mean(rs)
            sev = "act" if len(rs) >= 20 else "watch"
            if m is not None and m < -0.1:
                F.append({"sev": sev, "title": f"No edge detected: {typ}", "dr": m, "n": len(rs),
                          "ev": f"{len(rs)} closed {typ} trades average {m:+}R. The market is not paying for this pattern right now.",
                          "action": f"Propose demoting {typ} to half-size or PASS until expectancy recovers"})
            elif m is not None and m >= 0.5:
                F.append({"sev": sev, "title": f"Strong edge: {typ}", "dr": m, "n": len(rs),
                          "ev": f"{len(rs)} closed {typ} trades average {m:+}R — the system's best pattern.",
                          "action": f"Propose taking every A-grade {typ} at full size"})

        # 4. Timeout drag + near-miss audit
        tmo = [a.get("r") or 0 for a in resolved if a.get("status") == "timeout"]
        if len(tmo) >= 8 and (mean(tmo) or 0) < 0:
            F.append({"sev": "watch", "title": "Stale trades are bleeding", "dr": mean(tmo), "n": len(tmo),
                      "ev": f"{len(tmo)} trades hit the 15-session timeout averaging {mean(tmo):+}R — winners pay within ~2 weeks, the rest decay.",
                      "action": "Propose cutting untouched trades after 10 sessions instead of 15"})
        nm_rs = [a.get("r") or 0 for a in resolved if a.get("nm")]
        st_rs = [a.get("r") or 0 for a in resolved if not a.get("nm")]
        if len(nm_rs) >= 10 and len(st_rs) >= 10:
            dm = round((mean(nm_rs) or 0) - (mean(st_rs) or 0), 2)
            if dm <= -0.3:
                F.append({"sev": "act", "title": "Near-miss fills are diluting the edge", "dr": dm, "n": len(nm_rs),
                          "ev": f"Near-miss setups average {mean(nm_rs):+}R vs {mean(st_rs):+}R for strict ones ({dm:+}R gap). Filling lines to 4 ideas costs money.",
                          "action": "Propose publishing strict-screen setups only (fewer ideas, better ideas)"})

        advisor["status"] = "active" if F else "collecting"
        if not F:
            advisor["needs"] = {
                "stop / T1 / breakeven replay": f"{len(trig_res)}/20 closed trades",
                "entry-proximity experiment": f"{len(expired_p)}/10 expired setups",
                "per-pattern edge report": "10 closed trades per type",
            }
        print(f"Advisor: {advisor['status']}, {len(F)} findings "
              f"({len(resolved)} resolved, {advisor['nExpired']} expired archived)")
    except Exception as e:
        print(f"Advisor warning (non-fatal): {e}", file=sys.stderr)

    cutoff35 = (datetime.now(timezone.utc) - timedelta(days=35)).strftime("%Y-%m-%d")
    cutoff30 = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    hist = [s for s in prev_hist if s.get("status") in OPEN_STATES
            or (s.get("closed") or s.get("created") or "") >= cutoff35]

    recent = [s for s in hist if (s.get("created") or "") >= cutoff30]
    CLOSED_STATES = ("stopped", "t2", "be", "timeout")
    closed = [s for s in recent if s.get("status") in CLOSED_STATES]
    # A trade that reached T1 is ALREADY a win: half banked at +1.5R, stop at
    # breakeven — worst case +0.75R locked. Count it immediately, don't wait
    # for T2; the final R only improves (t2) or stays (be) when it closes.
    t1_open = [s for s in recent if s.get("status") == "t1"]
    trig_n = sum(1 for s in recent if s.get("status") not in ("pending", "expired", "cancelled_gap"))
    wins   = [s for s in closed if (s.get("r") or 0) > 0]
    losses = [s for s in closed if (s.get("r") or 0) <= 0]
    win_rs  = [s["r"] for s in wins] + [0.75] * len(t1_open)     # t1 = locked minimum
    all_rs  = [s.get("r") or 0 for s in closed] + [0.75] * len(t1_open)
    n_scored = len(closed) + len(t1_open)
    by_type = {}
    for s in recent:
        bt = by_type.setdefault(s["type"], {"n": 0, "w": 0, "l": 0})
        bt["n"] += 1
        if s.get("status") == "t1":
            bt["w"] += 1
        elif s.get("status") in CLOSED_STATES:
            if (s.get("r") or 0) > 0: bt["w"] += 1
            else: bt["l"] += 1
    stats = {
        "generated": len(recent),
        "trigRate": round(trig_n / len(recent) * 100, 1) if recent else None,
        "closed": len(closed), "wins": len(wins) + len(t1_open), "losses": len(losses),
        "t1Locked": len(t1_open),
        "hitRate": round((len(wins) + len(t1_open)) / n_scored * 100, 1) if n_scored else None,
        "avgWinR": round(sum(win_rs) / len(win_rs), 2) if win_rs else None,
        "avgLossR": round(sum(s["r"] for s in losses) / len(losses), 2) if losses else None,
        "expR": round(sum(all_rs) / n_scored, 2) if n_scored else None,
        "byType": by_type,
    }
    open_view = []
    for s in hist:
        if s.get("status") not in OPEN_STATES: continue
        tp = ticker_prices.get(s.get("t")) or {}
        ov = dict(s)
        if tp.get("p") is not None:
            ov["px"] = tp["p"]
            if s["status"] in ("triggered", "t1") and s.get("risk"):
                dirn = 1 if s["side"] == "long" else -1
                ov["uR"] = round((tp["p"] - s["entry"]) / s["risk"] * dirn, 2)
        open_view.append(ov)
    print(f"Tracker: {len(hist)} in history, {len(open_view)} open, "
          f"{len(closed)} closed in 30d (hit {stats['hitRate']}%, exp {stats['expR']}R)")

    sec_bull_n = sum(1 for e in SECTOR_ETFS if (bp_scores.get(e) or {}).get('bullish'))
    rsp = bp_scores.get('RSP') or {}
    setups_out = {
        "internals": {
            "sectorsBull": sec_bull_n, "sectorsTotal": len(SECTOR_ETFS),
            "pctAboveS20": round(stocks_above_s20 / stocks_total * 100, 1) if stocks_total else None,
            "newHighs": new_highs, "newLows": new_lows, "universe": stocks_total,
            "rspBull": bool(rsp.get('bullish')), "rspPct": rsp.get('pct'),
        },
        "list": final[:16],
        "scanned": stocks_total,
        "stats": stats,
        "open": open_view,
        "hist": hist,
        "advisor": advisor,   # self-evaluation report — proposals only, never auto-applied
    }
    print(f"Setups: {len(final[:16])} candidates from {stocks_total} stocks "
          f"({', '.join(f'{k}:{v}' for k,v in per_type.items())})")
except Exception as e:
    print(f"Setups scan failed (non-fatal): {e}", file=sys.stderr)

# ──────────────────────────────────────────────────────────────────────────────
# STEP 5 — Write data.json
# ──────────────────────────────────────────────────────────────────────────────
output = {
    "ts":            int(time.time()*1000),
    "generated":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "data":          results,
    "ticker_prices": ticker_prices,
    "etf_holdings":  etf_holdings_map,
    "bp_scores":     bp_scores,          # pre-computed ETF/SPY relative strength — no CORS needed
    # NOTE: "setups" is intentionally NOT in the public data.json. Today's Setups /
    # alerts are protected: they are pushed to a private Cloudflare KV store below
    # and served only behind a valid weekly code by the api.tradergk.com Worker.
}
with open("data.json", "w") as f:
    json.dump(output, f, separators=(",",":"))

# ──────────────────────────────────────────────────────────────────────────────
# STEP 5b — Push protected setups to Cloudflare KV (server-side gated)
# Only runs in CI where the CF_* secrets are present. Non-fatal on failure so a
# KV hiccup never breaks the public data refresh.
# ──────────────────────────────────────────────────────────────────────────────
_kv_token = os.environ.get("CF_KV_TOKEN")
_kv_acc   = os.environ.get("CF_ACCOUNT_ID")
_kv_ns    = os.environ.get("CF_KV_NS")
if not (_kv_token and _kv_acc and _kv_ns):
    print("   Setups → Cloudflare KV: skipped (CF_* env not set — local run)")
elif not (kv_prev_ok and "hist" in setups_out):
    # SAFETY GUARD: never overwrite the live book unless we (a) read the previous
    # book from KV without error AND (b) produced a full scan this run. Otherwise a
    # transient KV-read failure or a crashed scan would push an empty/partial book
    # and wipe every carried open position. Skip → KV keeps the last good book.
    print(f"   Setups → Cloudflare KV: SKIPPED to protect the book "
          f"(kv_prev_ok={kv_prev_ok}, full_scan={'hist' in setups_out})", file=sys.stderr)
else:
    try:
        import urllib.request
        body = json.dumps(setups_out, separators=(",", ":")).encode()
        url = f"https://api.cloudflare.com/client/v4/accounts/{_kv_acc}/storage/kv/namespaces/{_kv_ns}/values/latest"
        req = urllib.request.Request(url, data=body, method="PUT",
            headers={"Authorization": f"Bearer {_kv_token}", "Content-Type": "text/plain"})
        with urllib.request.urlopen(req, timeout=25) as r:
            print(f"   Setups → Cloudflare KV: pushed ({len(body)} bytes, HTTP {r.status})")
    except Exception as e:
        print(f"KV push failed (non-fatal): {e}", file=sys.stderr)

ok = sum(1 for r in results if not r.get("error"))
live_h = sum(1 for v in etf_holdings_map.values() if v and v[0].get('w',0) > 0)
print(f"\n✅ data.json written")
print(f"   Ratios:        {ok}/{len(results)} OK")
print(f"   ETF holdings:  {live_h}/{len(ETF_TICKERS)} from Yahoo Finance live")
print(f"   Ticker prices: {len(ticker_prices)} tickers")
