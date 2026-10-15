"""Pull daily adjusted OHLC for the watchlist, benchmarks, control basket; save CSVs + earnings dates."""
import yfinance as yf, pandas as pd, json, sys, time
WATCH = "AAOI BE IREN LITE NBIS INFQ CRWV AXTI SPCX GGLL SNDK MU ARM AMD NVDA IONQ WULF WDC STX UAMY".split()
BENCH = ["SPY", "QQQ", "HOOD"]
CONTROL = "AAPL MSFT GOOGL AMZN META AVGO TSLA ORCL CRM NFLX".split()
ALL = WATCH + BENCH + CONTROL
raw = yf.download(ALL, start="2023-01-01", end="2026-10-15", auto_adjust=True, progress=False, group_by="ticker", threads=True)
for t in ALL:
    df = raw[t].dropna(how="all")
    df.to_csv(f"data/{t}.csv")
    print(t, len(df), df.index[0].date(), df.index[-1].date(), round(float(df.Close.iloc[-1]),2))
earn = {}
for t in WATCH + ["HOOD"] + CONTROL:
    try:
        e = yf.Ticker(t).get_earnings_dates(limit=60)
        earn[t] = sorted({str(d.date()) for d in e.index}) if e is not None else []
    except Exception as ex:
        earn[t] = []; print("earnings fail", t, str(ex)[:80])
    time.sleep(0.3)
json.dump(earn, open("data/earnings.json", "w"), indent=1)
print({t: (len(v), v[:1], v[-1:]) for t, v in earn.items()})
