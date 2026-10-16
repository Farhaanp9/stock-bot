"""Round-3 stress data: long history (2017-) for the list + benchmarks + control, and a wide no-hindsight pool."""
import yfinance as yf, pandas as pd, json, time, sys
WATCH = "AAOI BE IREN LITE NBIS INFQ CRWV AXTI SPCX SNDK MU ARM AMD NVDA IONQ WULF WDC STX".split()
BENCH = "SPY QQQ SMH IWM ^VIX".split()
CONTROL = "AAPL MSFT GOOGL AMZN META AVGO TSLA ORCL CRM NFLX HOOD".split()
# Pool: names a retail trader could have watched at some point 2020-2026, winners and busts alike. No hindsight on who won after.
POOL = """SMCI INTC MRVL TSM ASML AMAT LRCX KLAC QCOM TXN ADI NXPI ON MCHP SWKS QRVO SITM CRDO ALAB COHR CIEN ANET DELL HPE PSTG VRT ONTO ACLS AEHR
PLTR AI SOUN BBAI PATH SNOW MDB NET DDOG CRWD ROKU U RBLX SHOP RDDT DJT GME AMC
COIN MSTR RIOT MARA CLSK HUT CIFR CORZ APLD BTDR
RGTI QUBT QBTS ASTS RKLB LUNR ACHR JOBY SMR OKLO NNE VST CEG TLN GEV
ENPH SEDG PLUG FSLR RIVN LCID NIO UPST AFRM SOFI CVNA
CLS FN MOD POWL NVMI CAMT TER ENTG MPWR SNPS CDNS SMTC MTSI LSCC RMBS CRUS AMBA WOLF INDI MRVL""".split()
POOL = sorted(set(POOL) - set(WATCH) - set(CONTROL))
ALL = WATCH + BENCH + CONTROL + POOL
def pull(names):
    raw = yf.download(names, start="2017-01-01", end="2026-10-16", auto_adjust=True, progress=False, group_by="ticker", threads=True)
    for t in names:
        try:
            df = raw[t].dropna(how="all")
        except Exception as ex:
            print("miss", t, str(ex)[:60]); continue
        if len(df) == 0: print("empty", t); continue
        df.to_csv(f"data/long/{t.replace('^','')}.csv")
        print(t, len(df), df.index[0].date(), df.index[-1].date(), round(float(df.Close.iloc[-1]), 2))
for i in range(0, len(ALL), 40):
    pull(ALL[i:i+40]); time.sleep(2)
if "noearn" not in sys.argv:
    earn = json.load(open("data/earnings.json"))
    for t in POOL:
        if t in earn and earn[t]: continue
        try:
            e = yf.Ticker(t).get_earnings_dates(limit=100)
            earn[t] = sorted({str(d.date()) for d in e.index}) if e is not None else []
        except Exception as ex:
            earn[t] = []; print("earnings fail", t, str(ex)[:80])
        time.sleep(0.5)
    json.dump(earn, open("data/long/earnings_all.json", "w"), indent=1)
    print("earnings:", {t: len(v) for t, v in earn.items() if t in POOL})
