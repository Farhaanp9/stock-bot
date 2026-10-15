import pandas as pd, numpy as np, json
from backtest import load, WATCH, EARN
C, O = load(WATCH + ["SPY", "QQQ", "HOOD"])
d = C.index[-1]
print("as of", d.date())
rows = []
for t in WATCH:
    s = C[t].dropna()
    if len(s) < 6: continue
    hi21 = s.iloc[-22:-1].max(); depth = 1 - s.iloc[-1] / hi21
    wk = s.iloc[-1] / s.iloc[-6] - 1
    sma200 = s.rolling(200).mean().iloc[-1] if len(s) >= 200 else np.nan
    sma50 = s.rolling(50).mean().iloc[-1] if len(s) >= 50 else np.nan
    worst5 = (s / s.shift(1) - 1).iloc[-5:].min()
    nxt = [e for e in EARN.get(t, []) if e >= str(d.date())][:1]
    rows.append(dict(name=t, close=round(s.iloc[-1], 2), off_21d_high=round(depth, 3), week=round(wk, 3),
                     vs200=round(s.iloc[-1] / sma200 - 1, 3) if sma200 == sma200 else None, vs50=round(s.iloc[-1] / sma50 - 1, 3) if sma50 == sma50 else None,
                     worst_day_5=round(worst5, 3), next_earn=nxt[0] if nxt else None))
df = pd.DataFrame(rows).sort_values("off_21d_high", ascending=False)
print(df.to_string(index=False))
print("\n=== HOOD late Jan 2026 and after ===")
h = C["HOOD"]
print(h.loc["2026-01-20":"2026-03-15"].round(2).to_string())
print("HOOD low after Jan 29:", round(h.loc["2026-01-30":].min(), 2), "on", h.loc["2026-01-30":].idxmin().date(), "| now", round(h.iloc[-1], 2))
print("\n=== SNDK: days it closed within 3% of a price 14% above today's close (his likely entry zone) ===")
s = C["SNDK"]; tgt = s.iloc[-1] / 0.86
print("implied entry ~", round(tgt, 0))
print(s[(s > tgt * 0.97) & (s < tgt * 1.03)].loc["2026-06-01":].round(0).to_string())
print("SNDK 21d high", round(s.iloc[-22:-1].max(), 0), "today", round(s.iloc[-1], 0), "all-time high", round(s.max(), 0), s.idxmax().date())
print("\n=== basket, SPY, QQQ since 2026-01-30 and since 2025-10-08 ===")
for s0 in ["2025-10-08", "2026-01-30"]:
    sub = C.loc[s0:]
    avail = [t for t in WATCH if sub[t].first_valid_index() == sub.index[0]]
    ew = np.mean([sub[t].iloc[-1] / sub[t].iloc[0] - 1 for t in avail])
    print(s0, "eq-wt basket", round(ew, 3), f"({len(avail)} names)", "SPY", round(sub.SPY.iloc[-1] / sub.SPY.iloc[0] - 1, 3), "QQQ", round(sub.QQQ.iloc[-1] / sub.QQQ.iloc[0] - 1, 3))
    print("   per name:", {t: round(sub[t].iloc[-1] / sub[t].iloc[0] - 1, 2) for t in avail})
# realized vol ranking
print("\n=== 60-day daily vol, annualized ===")
print({t: round(float(C[t].pct_change().iloc[-60:].std() * np.sqrt(252)), 2) for t in WATCH})
