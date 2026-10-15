import pandas as pd, numpy as np
from backtest import load, WATCH
names = [t for t in WATCH if t not in ("GGLL","UAMY")]
C, O = load(names + ["SPY","QQQ","SMH","HOOD","VIX","TNX","IWM"])
def ret(s, a, b):
    s = s.loc[a:b].dropna(); return (s.iloc[-1]/s.iloc[0]-1) if len(s) > 1 else np.nan
print("== golden 2025-10-08 .. 2026-01-29: total return, max run-up (low->high within window), green-day share")
rows=[]
for t in names + ["SPY","QQQ","SMH","HOOD"]:
    s = C[t].loc["2025-10-08":"2026-01-29"].dropna()
    if len(s) < 10: continue
    runup = (s.cummax()/s.cummin().iloc[0]).max()  # crude; better: max over i<j of s[j]/s[i]
    best = max(s.iloc[j]/s.iloc[:j+1].min() for j in range(len(s)))-1
    green = (s.pct_change().dropna() > 0).mean()
    rows.append(dict(name=t, ret=round(s.iloc[-1]/s.iloc[0]-1,2), best_runup=round(best,2), green=round(green,2), maxdd=round((s/s.cummax()-1).min(),2)))
print(pd.DataFrame(rows).sort_values("ret", ascending=False).to_string(index=False))
print("\n== 2026-01-29 .. 2026-03-30 (the bad stretch)")
rows=[]
for t in names + ["SPY","QQQ","SMH","HOOD","IWM"]:
    s = C[t].loc["2026-01-29":"2026-03-31"].dropna()
    if len(s) < 10: continue
    rows.append(dict(name=t, ret=round(s.iloc[-1]/s.iloc[0]-1,2), low=str(s.idxmin().date()), maxdd=round((s/s.cummax()-1).min(),2)))
print(pd.DataFrame(rows).sort_values("ret").to_string(index=False))
print("\n== QQQ / SMH / VIX key levels")
q, m, v = C["QQQ"], C["SMH"], C["VIX"]
for d in ["2025-10-08","2025-11-20","2025-12-31","2026-01-29","2026-02-05","2026-02-27","2026-03-13","2026-03-30","2026-04-30","2026-06-25","2026-08-31","2026-09-30","2026-10-14"]:
    i = q.index.searchsorted(pd.Timestamp(d)); dd = q.index[min(i, len(q)-1)]
    print(dd.date(), "QQQ", round(q[dd],1), "vs50", round(q[dd]/q.rolling(50).mean()[dd]-1,3), "vs200", round(q[dd]/q.rolling(200).mean()[dd]-1,3), "| SMH", round(m[dd],1), "vs50", round(m[dd]/m.rolling(50).mean()[dd]-1,3), "| VIX", round(v.get(dd, np.nan),1))
print("\n== QQQ drawdowns > 8% since 2023-10 (peak date, trough date, depth)")
dd = q/q.cummax()-1
in_dd=False
for d, x in dd.items():
    if x < -0.08 and not in_dd:
        in_dd=True; start=d; trough=d; depth=x
    elif in_dd:
        if x < depth: depth=x; trough=d
        if x == 0:
            print(" peak->", start.date(), "trough", trough.date(), round(depth,3), "recovered", d.date()); in_dd=False
if in_dd: print(" ongoing from", start.date(), "trough", trough.date(), round(depth,3))
print("\n== SMH drawdowns > 10%")
dd = m/m.cummax()-1; in_dd=False
for d, x in dd.items():
    if x < -0.10 and not in_dd: in_dd=True; start=d; trough=d; depth=x
    elif in_dd:
        if x < depth: depth=x; trough=d
        if x == 0: print(" peak->", start.date(), "trough", trough.date(), round(depth,3), "recovered", d.date()); in_dd=False
if in_dd: print(" ongoing from", start.date(), "trough", trough.date(), round(depth,3))
print("\n== beta to SMH (daily, last 250d) and correlation; avg pairwise corr of the list")
R = C[names].pct_change().iloc[-250:]; rm = C["SMH"].pct_change().iloc[-250:]
b = {t: round(float(R[t].cov(rm)/rm.var()),2) for t in names if R[t].notna().sum()>100}
print("beta:", b)
cc = R.dropna(axis=1, thresh=100).corr(); print("avg pairwise corr:", round(float((cc.values[np.triu_indices(len(cc),1)]).mean()),2))
print("corr to SMH:", {t: round(float(R[t].corr(rm)),2) for t in names if R[t].notna().sum()>100})
