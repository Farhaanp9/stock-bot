"""Year-one expectations without hindsight: bootstrap trade outcomes from the rolling universes (2018-2026); what the mechanical screen proposes today."""
import json, numpy as np, pandas as pd
from stress3 import *
from s3_long import rolling_universe, LONG, POOL
E.EARN = json.load(open("data/long/earnings_all.json")); rng = np.random.default_rng(3)
P, I = prep(POOL, LONG); smh = P["Close"]["SMH"]; smh200 = smh > smh.rolling(200).mean()
for lab, kw in {"12m quarterly": dict(), "6m monthly": dict(lookback=126, freq="MS")}.items():
    U = rolling_universe(P, POOL, **kw); I["rank63"] = I["ret63"].where(U).rank(axis=1, ascending=False)
    sig, rank, eng = plan_signals(I, POOL, U=U)
    for vn, ms in {"plan": None, "slots 3/1 on SMH 200d": smh200.map(lambda x: 3 if x else 1)}.items():
        tr, eq, _ = run3(P, I, POOL, PLAN, "2018-07-02", "2026-10-15", sig, rank, eng, maxpos_series=ms)
        T = pd.DataFrame(tr); r = T.ret.values; n_yr = len(r) / 8.3
        m1 = np.array([np.prod(1 + rng.choice(r, int(n_yr)) / 3) for _ in range(5000)]); f1 = np.array([rng.choice(r, int(n_yr)).sum() * 1800 for _ in range(5000)])
        print(f"{lab:14s} {vn:24s} trades {len(T)} ({n_yr:.0f}/yr) avg {r.mean():+.3f} win {(r>0).mean():.2f} | year-1 multiple p5 {np.percentile(m1,5):.2f} p25 {np.percentile(m1,25):.2f} p50 {np.percentile(m1,50):.2f} p95 {np.percentile(m1,95):.2f} P(loss) {(m1<1).mean():.2f} | fixed $1800: p5 {np.percentile(f1,5):,.0f} p50 {np.percentile(f1,50):,.0f} p95 {np.percentile(f1,95):,.0f}")
        if lab == "6m monthly": T.to_csv(f"data/trades3_roll6m_{vn.split()[0]}.csv", index=False)
    if lab == "6m monthly":
        for d in ("2025-10-01", "2026-10-01"):
            print(f"   6m-monthly screen on {d}:", sorted(U.loc[d:].iloc[0][lambda x: x].index.tolist()))
# worst 12-month windows, plan on 6m monthly
U = rolling_universe(P, POOL, lookback=126, freq="MS"); I["rank63"] = I["ret63"].where(U).rank(axis=1, ascending=False); sig, rank, eng = plan_signals(I, POOL, U=U)
for vn, ms in {"plan": None, "slots 3/1": smh200.map(lambda x: 3 if x else 1)}.items():
    tr, eq, _ = run3(P, I, POOL, PLAN, "2018-07-02", "2026-10-15", sig, rank, eng, maxpos_series=ms)
    r12 = eq / eq.shift(252) - 1
    print(f"   {vn}: rolling 12-month return p5 {r12.quantile(.05):+.2f} p25 {r12.quantile(.25):+.2f} median {r12.median():+.2f} ; share of 12-month windows negative {(r12<0).mean():.2f} ; worst {r12.min():+.2f} ending {r12.idxmin().date()}")
