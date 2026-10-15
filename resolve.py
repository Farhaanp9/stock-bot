import yfinance as yf, json, sys
tickers = "AAOI BE IREN LITE NBIS GPTS INFQ CRWV AXTI SPCX GGLL SNDK MU ARM AMD NVDA IONQ WULF WDC STX UAMY HOOD SPY QQQ".split()
out = {}
for t in tickers:
    try:
        i = yf.Ticker(t).info
        h = yf.Ticker(t).history(period="max", auto_adjust=True)
        out[t] = dict(name=i.get("shortName") or i.get("longName"), type=i.get("quoteType"), cap=i.get("marketCap"),
                      price=i.get("currentPrice") or i.get("regularMarketPrice"), rec=i.get("recommendationMean"), nanal=i.get("numberOfAnalystOpinions"),
                      target=i.get("targetMeanPrice"), revg=i.get("revenueGrowth"), opm=i.get("operatingMargins"), fpe=i.get("forwardPE"),
                      first=str(h.index[0].date()) if len(h) else None, rows=len(h), advol=float((h.Close*h.Volume).tail(60).mean()) if len(h) else None)
    except Exception as e:
        out[t] = dict(error=str(e)[:120])
    print(t, out[t], flush=True)
json.dump(out, open("data/universe_info.json","w"), indent=1, default=str)
