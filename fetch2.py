"""Extra series for round 2: sector ETFs, VIX, rates; per-name fundamentals snapshot (analysts, short interest, float, beta)."""
import yfinance as yf, pandas as pd, json, time
EXTRA = ["SMH", "SOXX", "IWM", "XLK", "^VIX", "^TNX", "BITO"]
raw = yf.download(EXTRA, start="2023-01-01", end="2026-10-15", auto_adjust=True, progress=False, group_by="ticker", threads=True)
for t in EXTRA:
    df = raw[t].dropna(how="all"); df.to_csv(f"data/{t.replace('^','')}.csv")
    print(t, len(df), df.index[0].date(), df.index[-1].date(), round(float(df.Close.iloc[-1]), 2))
WATCH = "AAOI BE IREN LITE NBIS INFQ CRWV AXTI SPCX GGLL SNDK MU ARM AMD NVDA IONQ WULF WDC STX UAMY".split()
keys = ["marketCap","beta","shortPercentOfFloat","sharesShort","sharesShortPriorMonth","floatShares","targetMeanPrice","targetMedianPrice","targetLowPrice","targetHighPrice","recommendationMean","recommendationKey","numberOfAnalystOpinions","forwardPE","trailingPE","sector","industry","fiftyTwoWeekHigh","fiftyTwoWeekLow","averageVolume","earningsTimestamp","earningsGrowth","revenueGrowth"]
info = {}
for t in WATCH:
    try:
        i = yf.Ticker(t).info; info[t] = {k: i.get(k) for k in keys}
    except Exception as e:
        info[t] = {"error": str(e)[:100]}
    time.sleep(0.4)
json.dump(info, open("data/fundamentals.json", "w"), indent=1, default=str)
for t, v in info.items(): print(t, v.get("industry"), "short%", v.get("shortPercentOfFloat"), "tgt", v.get("targetMeanPrice"), "rec", v.get("recommendationMean"), "n", v.get("numberOfAnalystOpinions"), "beta", v.get("beta"))
