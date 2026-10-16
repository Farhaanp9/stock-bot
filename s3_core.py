"""Tests on the existing 2023-10 .. 2026-10 data: baseline, fixed-size $, trade removal, bootstrap, random-timing control,
slippage/fill sensitivity, stop realism, cluster risk, parabolic leaders, tax brackets."""
import sys, json, numpy as np, pandas as pd
from stress3 import *
rng = np.random.default_rng(7)
names = WATCH; P, I = prep(names); sig, rank, eng = plan_signals(I, names)
S, Efull = "2023-10-02", "2026-10-14"
W = dict(E.WINDOWS)
t0 = time.time()
tr, eq, op = run3(P, I, names, PLAN, S, Efull, sig, rank, eng)
print("baseline", summ(tr, eq), "secs", round(time.time() - t0, 1))
T = pd.DataFrame(tr); T.to_csv("data/trades3.csv", index=False)
# --- T4 fixed-size dollars per year and per engine
T["yr"] = pd.to_datetime(T.exit).dt.year
print("fixed $1800/trade by year:", (T.groupby("yr").ret.sum() * 1800).round(0).to_dict())
print("fixed by engine:", (T.groupby("eng").ret.agg(["size", "sum", "mean"]).round(3)).to_dict("index"))
# --- T3 remove top trades (fixed-size and approx compounded)
srt = T.sort_values("ret", ascending=False)
for k in (0, 1, 3, 5, 10):
    rest = srt.iloc[k:]
    comp = float(np.prod(1 + rest.ret.values / 3))  # sequential approximation of thirds compounding
    print(f"drop top {k}: fixed$={rest.ret.sum()*1800:.0f}  approx compounded x{comp:.1f}  (all-trades approx x{np.prod(1+T.ret.values/3):.1f})")
# --- T5 bootstrap trade sequence
rets = T.ret.values; n = len(rets); ends, dds = [], []
for _ in range(5000):
    s = rng.choice(rets, n, replace=True); path = np.cumprod(1 + s / 3)
    ends.append(path[-1]); dds.append((path / np.maximum.accumulate(path) - 1).min())
ends, dds = np.array(ends), np.array(dds)
print("bootstrap 3y multiple: p5 %.2f p25 %.2f p50 %.2f p75 %.2f p95 %.2f  P(loss)=%.3f  P(DD<-30%%)=%.2f P(DD<-50%%)=%.2f  medianDD %.2f"
      % (*np.percentile(ends, [5, 25, 50, 75, 95]), (ends < 1).mean(), (dds < -0.3).mean(), (dds < -0.5).mean(), np.median(dds)))
# one-year bootstrap (43 trades)
ends1 = np.array([np.prod(1 + rng.choice(rets, 43) / 3) for _ in range(5000)])
print("bootstrap 1y multiple: p5 %.2f p25 %.2f p50 %.2f p95 %.2f P(loss)=%.3f" % (*np.percentile(ends1, [5, 25, 50, 95]), (ends1 < 1).mean()))
# --- T2 random-timing control: same per-name, per-engine signal counts, random days with data
def shuffle_sig(sig, eng):
    sR = pd.DataFrame(False, index=sig.index, columns=sig.columns); eR = pd.DataFrame("", index=sig.index, columns=sig.columns)
    for t in sig.columns:
        valid = np.where(I["C"][t].notna().values & (sig.index >= pd.Timestamp(S)))[0]
        for lab in ("L", "D"):
            kk = int(((eng[t] == lab) & sig[t]).sum())
            if kk == 0 or len(valid) == 0: continue
            pick = rng.choice(valid, min(kk, len(valid)), replace=False)
            sR.iloc[pick, sR.columns.get_loc(t)] = True; eR.iloc[pick, eR.columns.get_loc(t)] = lab
    return sR, eR
res = []
for i in range(200):
    sR, eR = shuffle_sig(sig, eng); rR = pd.DataFrame(rng.random(sig.shape), index=sig.index, columns=sig.columns)
    trR, eqR, _ = run3(P, I, names, PLAN, S, Efull, sR, rR, eR)
    sm = summ(trR, eqR); res.append((sm["ret"], sm["dd"], sm["fixed$"], sm["avg"]))
R = pd.DataFrame(res, columns=["ret", "dd", "fixed", "avg"])
base = summ(tr, eq)
print("random-timing control (200): ret p5/50/95 = %.2f / %.2f / %.2f  fixed$ p50 %.0f  avg/trade p50 %.4f ;  real: ret %.2f fixed$ %.0f avg %.4f ; pct of randoms beaten: ret %.2f fixed %.2f avg %.2f"
      % (*R.ret.quantile([.05, .5, .95]), R.fixed.median(), R.avg.median(), base["ret"], base["fixed$"], base["avg"], (R.ret < base["ret"]).mean(), (R.fixed < base["fixed$"]).mean(), (R.avg < base["avg"]).mean()))
R.to_csv("data/random_control.csv", index=False)
# per-window random control vs real
for w in ("golden", "bad", "recovery"):
    s, e = W[w]; real = summ(*run3(P, I, names, PLAN, s, e, sig, rank, eng)[:2])
    rr = []
    for i in range(60):
        sR, eR = shuffle_sig(sig, eng); rR = pd.DataFrame(rng.random(sig.shape), index=sig.index, columns=sig.columns)
        rr.append(summ(*run3(P, I, names, PLAN, s, e, sR, rR, eR)[:2])["ret"])
    rr = np.array(rr); print(f"  {w}: real {real['ret']:.2f} vs random p50 {np.median(rr):.2f} (p5 {np.percentile(rr,5):.2f}, p95 {np.percentile(rr,95):.2f}); beats {(rr<real['ret']).mean():.2f}")
# --- T6/T7 slippage and fills
for slip in (0.001, 0.003, 0.005, 0.01):
    print("slip", slip, summ(*run3(P, I, names, PLAN, S, Efull, sig, rank, eng, slip=slip)[:2]))
for mode in ("open", "close", "mid", "high", "low"):
    print("entry", mode, summ(*run3(P, I, names, PLAN, S, Efull, sig, rank, eng, entry=mode)[:2]))
print("entry open, void if open>+5%:", summ(*run3(P, I, names, PLAN, S, Efull, sig, rank, eng, void=0.05)[:2]))
print("entry open, void>+3%:", summ(*run3(P, I, names, PLAN, S, Efull, sig, rank, eng, void=0.03)[:2]))
print("exit at close (no overnight wait):", summ(*run3(P, I, names, PLAN, S, Efull, sig, rank, eng, exit_mode="close")[:2]))
# --- T8 stop realism
st = T[T.reason == "stop"]
print(f"stops: n={len(st)} mean {st.ret.mean():.3f} median {st.ret.median():.3f}  <-15%: {(st.ret<-0.15).sum()}  <-20%: {(st.ret<-0.2).sum()}  worst {st.ret.min():.3f} ({st.loc[st.ret.idxmin(),'name']} {st.loc[st.ret.idxmin(),'exit'].date()})")
print("all-trade MAE (intraday low vs entry): median %.3f, <-15%%: %d, <-25%%: %d" % (T.mae.median(), (T.mae < -0.15).sum(), (T.mae < -0.25).sum()))
print("by reason:", T.groupby("reason").ret.agg(["size", "mean"]).round(3).to_dict("index"))
# --- T9 cluster risk
ex = T[T.reason == "stop"].sort_values("exit"); cl = 0
exd = list(ex.exit)
for i, d in enumerate(exd):
    if sum((abs((x - d).days) <= 7) for x in exd) >= 2: cl += 1
print("stop exits with another stop within 7 calendar days:", cl, "of", len(exd))
print("worst 5-day equity move: %.3f, worst 21-day: %.3f, longest underwater: %d trading days" % ((eq / eq.shift(5) - 1).min(), (eq / eq.shift(21) - 1).min(), summ(tr, eq)["dd_days"]))
# --- T18 parabolic leaders
Lt = T[T.eng == "L"]
for lo, hi in ((0, .5), (.5, 1), (1, 2), (2, 99)):
    sub = Lt[(Lt.ret63 >= lo) & (Lt.ret63 < hi)]
    if len(sub): print(f"  leader trades with 63d return {lo:.0%}-{hi:.0%}: n={len(sub)} avg {sub.ret.mean():.3f} win {(sub.ret>0).mean():.2f}")
# --- T17 taxes at brackets, fixed-size
g = (T.groupby("yr").ret.sum() * 1800)
print("fixed-size gains by year", g.round(0).to_dict(), "tax@12%", round(float(g.clip(lower=0).sum() * .12)), "@22%", round(float(g.clip(lower=0).sum() * .22)))
# --- how often all 3 slots full / idle cash
print("done core")
