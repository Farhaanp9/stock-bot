"""Event study: forward returns after a dip signal, split by the conditions the literature says matter.
Not a portfolio; every signal-day counts (overlapping), so this measures the edge per condition, not P&L."""
import numpy as np, pandas as pd
from engine2 import load_panel, indicators, signals, earnings_mask, WATCH, buy_hold
P = load_panel(WATCH); I = indicators(P, WATCH); C = I["C"]
sig, rank = signals(I, WATCH, dict(sig=["dip"], D=0.15, k=1.5, gap=0.20, earn=(3, 5)))
O = P["Open"][WATCH]
fwd = {h: (C.shift(-h) / O.shift(-1) - 1) for h in (5, 10, 20)}   # buy next open, hold h closes
ev = []
for t in WATCH:
    for d in C.index[sig[t]]:
        if d < pd.Timestamp("2023-10-02") or d > pd.Timestamp("2026-09-15"): continue
        ev.append(dict(name=t, date=d, f5=fwd[5].at[d, t], f10=fwd[10].at[d, t], f20=fwd[20].at[d, t],
                       resid=I["resid5"].at[d, t], smh5=I["smh5"][d], vr=I["volratio"].at[d, t], qqq50=bool(I["qqq50"][d]), smh50=bool(I["smh50"][d]),
                       vix=I["vix"][d], above50=bool(C.at[d, t] > I["sma50"].at[d, t]), above200=bool(C.at[d, t] > I["sma200"].at[d, t]) if not np.isnan(I["sma200"].at[d, t]) else None,
                       rsi2=I["rsi2"].at[d, t], dvol=I["depth21"].at[d, t] / I["vol21"].at[d, t], depth=I["depth21"].at[d, t]))
E = pd.DataFrame(ev).dropna(subset=["f10"])
E["win"] = pd.cut(E.date, [pd.Timestamp(x) for x in ["2023-10-01", "2025-10-07", "2026-01-29", "2026-03-31", "2026-12-31"]], labels=["before", "golden", "bad", "recovery"])
def tab(key, grp):
    g = E.groupby(grp, observed=True)
    out = g.agg(n=("f10", "size"), f5=("f5", "mean"), f10=("f10", "mean"), f20=("f20", "mean"), hit10=("f10", lambda x: (x > 0).mean()), med10=("f10", "median"))
    print(f"\n== {key}"); print(out.round(3).to_string())
print("signal-days:", len(E), "names:", E.name.nunique())
print("ALL  f5 %.3f f10 %.3f f20 %.3f hit10 %.2f" % (E.f5.mean(), E.f10.mean(), E.f20.mean(), (E.f10 > 0).mean()))
tab("by window", "win")
E["idio"] = np.where(E.resid <= -0.10, "idiosyncratic (resid<=-10%)", np.where(E.smh5 <= -0.05, "sector-driven (SMH 5d<=-5%)", "mixed"))
tab("idiosyncratic vs sector-driven", "idio")
E["volbin"] = pd.cut(E.vr, [0, 1.0, 1.5, 2.5, 100], labels=["<1x", "1-1.5x", "1.5-2.5x", ">2.5x"])
tab("volume ratio on signal day", "volbin")
tab("QQQ above 50-day", "qqq50"); tab("SMH above 50-day", "smh50")
E["vixbin"] = pd.cut(E.vix, [0, 18, 25, 30, 100], labels=["<18", "18-25", "25-30", ">30"]); tab("VIX", "vixbin")
tab("name above its 50-day", "above50"); tab("name above its 200-day", "above200")
E["dvbin"] = pd.cut(E.dvol, [0, 1.75, 2.0, 2.5, 10], labels=["1.5-1.75σ", "1.75-2σ", "2-2.5σ", ">2.5σ"]); tab("drop in vol units", "dvbin")
E["rsibin"] = pd.cut(E.rsi2, [0, 5, 15, 100], labels=["rsi2<5", "5-15", ">15"]); tab("RSI(2)", "rsibin")
# combined: green regime + not sector-driven
E["combo"] = np.where(E.qqq50 & (E.smh5 > -0.05), "QQQ up & sector not down", np.where(~E.qqq50, "QQQ down", "QQQ up but sector down"))
tab("combined", "combo")
# memory subset in golden window
MEM = ["SNDK", "MU", "WDC", "STX", "LITE"]
for s, e in [("2025-10-08", "2026-01-29"), ("2025-10-08", "2025-12-08"), ("2025-11-01", "2026-01-01"), ("2025-12-01", "2026-01-29")]:
    print("hold memory-5", s, e, buy_hold(C, MEM, s, e))
E.to_csv("data/events.csv", index=False)
