"""Confirm the void rule + slippage on the no-hindsight universe; count SMH 200-day whipsaws; round-3 baseline on his 18."""
import json, numpy as np, pandas as pd
from stress3 import *
from s3_long import rolling_universe, LONG, POOL
E.EARN = json.load(open("data/long/earnings_all.json"))
P, I = prep(POOL, LONG); smh = P["Close"]["SMH"]; smh200 = smh > smh.rolling(200).mean(); ms = smh200.map(lambda x: 3 if x else 1)
U = rolling_universe(P, POOL, lookback=126, freq="MS"); I["rank63"] = I["ret63"].where(U).rank(axis=1, ascending=False); sig, rank, eng = plan_signals(I, POOL, U=U)
print("rolling 6m-monthly universe, 2018-07..2026-10, slots 3/1 on SMH 200d:")
for void in (None, 0.03, 0.05):
    for slip in (0.001, 0.003):
        tr, eq, _ = run3(P, I, POOL, PLAN, "2018-07-02", "2026-10-15", sig, rank, eng, maxpos_series=ms, void=void, slip=slip)
        s = summ(tr, eq); print(f"   void {str(void):5s} slip {slip}: ret x{1+s['ret']:.1f} dd {s['dd']:.2f} n {s['n']} win {s['win']} avg {s['avg']:.4f} fixed$ {s['fixed$']:,.0f}")
x = smh200.loc["2018-07-02":].astype(int).diff().abs().sum(); below = (~smh200.loc["2018-07-02":]).mean()
print(f"SMH 200-day crossings 2018-07..2026-10: {int(x)} ; share of days below: {below:.2f} ; today above200: {bool(smh200.iloc[-1])} (SMH {smh.iloc[-1]:.0f} vs 200d {smh.rolling(200).mean().iloc[-1]:.0f})")
# round-3 baseline on his 18, sample windows
P2, I2 = prep(WATCH, LONG); smh2 = P2["Close"]["SMH"]; ms2 = (smh2 > smh2.rolling(200).mean()).map(lambda x: 3 if x else 1)
sig2, rank2, eng2 = plan_signals(I2, WATCH)
print("his 18, round-3 rules (slots 3/1, void 3%, slip 0.3%) vs round-2 as written (slip 0.1%):")
for w, (s, e) in {"sample": ("2023-10-02", "2026-10-15"), "golden": ("2025-10-08", "2026-01-29"), "bad": ("2026-01-30", "2026-03-31"), "recovery": ("2026-04-01", "2026-10-15")}.items():
    a = summ(*run3(P2, I2, WATCH, PLAN, s, e, sig2, rank2, eng2, maxpos_series=ms2, void=0.03, slip=0.003)[:2]); b = summ(*run3(P2, I2, WATCH, PLAN, s, e, sig2, rank2, eng2)[:2])
    print(f"   {w:9s} r3: ret {a['ret']:+.2f} dd {a['dd']:.2f} n {a['n']} fixed$ {a['fixed$']:,.0f} | r2: ret {b['ret']:+.2f} dd {b['dd']:.2f} n {b['n']} fixed$ {b['fixed$']:,.0f}")
tr, eq, op = run3(P2, I2, WATCH, PLAN, "2023-10-02", "2026-10-15", sig2, rank2, eng2, maxpos_series=ms2, void=0.03, slip=0.003)
T = pd.DataFrame(tr); T["yr"] = pd.to_datetime(T.exit).dt.year; print("   r3 fixed$ by year:", (T.groupby("yr").ret.sum() * 1800).round(0).to_dict(), "open:", [(o["name"], round(o["ret"], 3)) for o in op])
T.to_csv("data/trades3_r3.csv", index=False)
