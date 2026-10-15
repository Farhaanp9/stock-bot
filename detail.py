"""Stress-test detail for one rule set: year by year, worst trades, streaks, dollar lows, taxes, wash sales, today's signals."""
import json, sys, numpy as np, pandas as pd
from backtest import load, run, summarize, costs, buy_hold, WATCH, signals, EARN
p = json.loads(sys.argv[1]); names = [t for t in WATCH if t not in p.get("exclude", [])]
C, O = load(names + ["SPY"]); spy = C.SPY; C = C.drop(columns="SPY"); O = O.drop(columns="SPY")
s, e = "2023-10-02", "2026-10-14"
tr, eq, op = run(C, O, names, p, s, e, spy)
T = pd.DataFrame(tr); T["year"] = pd.to_datetime(T.exit).dt.year
print("rules:", p); print(summarize(tr, eq)); print(costs(tr))
print("\nper year: trades / net pnl / win rate / end equity")
for y, g in T.groupby("year"):
    print(y, len(g), round(g.pnl.sum()), round((g.ret > 0).mean(), 2), round(float(eq[eq.index.year == y].iloc[-1])))
print("\ntrades per week:", round(len(T) / (len(eq) / 5), 2), "| median hold days:", T.days.median(), "| max hold:", T.days.max())
# losing streaks
r = (T.sort_values("exit").ret > 0).astype(int).values
streak = mx = 0
for x in r:
    streak = streak + 1 if x == 0 else 0; mx = max(mx, streak)
print("longest losing streak:", mx)
print("\nworst 8 trades:"); print(T.nsmallest(8, "ret")[["name", "entry", "exit", "ret", "reason", "days"]].assign(entry=lambda d: d.entry.dt.date, exit=lambda d: d.exit.dt.date).round(3).to_string(index=False))
print("\nbest 5 trades:"); print(T.nlargest(5, "ret")[["name", "entry", "exit", "ret", "reason", "days"]].assign(entry=lambda d: d.entry.dt.date, exit=lambda d: d.exit.dt.date).round(3).to_string(index=False))
# dollar drawdowns, at $5,400 and not compounding beyond: equity curve lows per year
dd = eq / eq.cummax() - 1
print("\nmax drawdown:", round(float(dd.min()), 3), "on", dd.idxmin().date(), "| equity then", round(float(eq[dd.idxmin()])), "| peak before", round(float(eq.cummax()[dd.idxmin()])))
print("equity by quarter end:", {str(k.date()): round(float(v)) for k, v in eq.resample("QE").last().items()})
print("\nper name:"); print(T.groupby("name").agg(n=("pnl", "size"), pnl=("pnl", "sum"), win=("ret", lambda r: round((r > 0).mean(), 2)), avg_ret=("ret", "mean")).round(2).sort_values("pnl").to_string())
# today
sig, depth = signals(C, O, names, p, spy)
d = C.index[-1]; print("\nTODAY", d.date(), "signals:", [t for t in names if sig.at[d, t]])
hi21 = C.shift(1).rolling(21).max(); vol = (C / C.shift(1) - 1).rolling(21).std() * np.sqrt(21)
print("name close off21dhigh need(k*vol) above200sma? gap5d? earn-window?")
em = None
if p.get("earn"):
    from backtest import earnings_mask; em = earnings_mask(C, names, *p["earn"])
for t in names:
    c = C[t].dropna()
    if len(c) < 25: continue
    need = max(p["D"], p["k"] * vol.at[d, t]) if p.get("k") else p["D"]
    sma = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else np.nan
    gap = bool(((C[t] / C[t].shift(1) - 1) <= -0.2).iloc[-5:].any())
    print(f"{t:5} {c.iloc[-1]:9.2f} {depth.at[d,t]:6.3f} {need:6.3f} {'yes' if c.iloc[-1] > sma else ('no' if sma == sma else 'n/a'):4} {'GAP' if gap else '-':4} {'EARN' if (em is not None and em.at[d,t]) else '-'}")
print("open at end:", [(o["name"], str(o["entry"].date()), round(o["ret"], 3)) for o in op])
