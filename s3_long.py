"""Long-history and no-hindsight tests: semi bear 2022, Q4 2018, 2017-2023 pre-sample; static 2023 retail lists; rolling mechanical universe;
flag stability on the pool; SMH -10%/6-session analogs; data sanity; walk-forward."""
import sys, json, glob, numpy as np, pandas as pd
from stress3 import *
E.EARN = json.load(open("data/long/earnings_all.json"))
LONG = "data/long"
BENCH = {"SPY", "QQQ", "SMH", "IWM", "VIX"}
POOL = sorted(set(Path(f).stem for f in glob.glob(f"{LONG}/*.csv")) - BENCH)
which = (sys.argv[1] if len(sys.argv) > 1 else "all") if __name__ == "__main__" else "none"

def report(label, names, P, I, sig, rank, eng, windows):
    for w, (s, e) in windows.items():
        tr, eq, op = run3(P, I, names, PLAN, s, e, sig, rank, eng)
        h, n = hold(I["C"], names, s, e); smh = P["Close"]["SMH"]; smhr = round(float(smh.loc[s:e].iloc[-1] / smh.loc[s:e].iloc[0] - 1), 3)
        print(f"{label:28s} {w:12s} {s}..{e}  {summ(tr, eq)}  hold({n})={h}  SMH={smhr}")
        if w in ("semi-bear-2022", "q4-2018") and len(tr):
            T = pd.DataFrame(tr); print("      by engine:", T.groupby("eng").ret.agg(["size", "mean", "sum"]).round(3).to_dict("index"), "reasons", T.reason.value_counts().to_dict())

if which in ("all", "bear"):
    names = [t for t in WATCH if t not in ("NBIS", "INFQ", "CRWV", "SPCX", "SNDK", "ARM")]  # the twelve with pre-2023 history
    P, I = prep(names, LONG); sig, rank, eng = plan_signals(I, names)
    Wb = {"pre-sample": ("2017-07-03", "2023-09-29"), "q4-2018": ("2018-09-04", "2018-12-31"), "covid-2020": ("2020-02-03", "2020-06-30"),
          "semi-bear-2022": ("2021-11-15", "2022-12-30"), "2023-run": ("2023-01-03", "2023-09-29"), "sample": ("2023-10-02", "2026-10-15")}
    report("12 names w/ history", names, P, I, sig, rank, eng, Wb)
    # per-year on the pre-sample
    tr, eq, _ = run3(P, I, names, PLAN, "2017-07-03", "2026-10-15", sig, rank, eng)
    yr = eq.resample("YE").last(); yr0 = eq.resample("YE").first()
    print("   by year 12-name list:", {str(k.year): round(float(v / yr0[k] - 1), 2) for k, v in yr.items()})
    T = pd.DataFrame(tr); T["yr"] = pd.to_datetime(T.exit).dt.year
    print("   fixed $1800 by year:", (T.groupby("yr").ret.sum() * 1800).round(0).to_dict())
    print("   trades/yr:", T.groupby("yr").size().to_dict())
    cn = CONTROL; Pc, Ic = prep(cn, LONG); sc, rc, ec = plan_signals(Ic, cn)
    report("control big tech", cn, Pc, Ic, sc, rc, ec, Wb)

STATIC = {"U1 2023 retail AI/semi": "NVDA AMD SMCI INTC MRVL MU TSM AMAT PLTR AI SOUN IONQ COIN MSTR RIOT MARA ENPH TSLA".split(),
          "U2 2023 retail growth": "PLTR AI SOUN PATH SNOW UPST AFRM SOFI CVNA ROKU U RBLX SHOP RIVN NIO PLUG SEDG HOOD".split(),
          "U3 semicap/mature": "TSM ASML AMAT LRCX KLAC QCOM TXN ADI NXPI ON MCHP SWKS MPWR TER ENTG SNPS CDNS AVGO".split()}
if which in ("all", "static"):
    Ws = {"sample": ("2023-10-02", "2026-10-15"), "golden": ("2025-10-08", "2026-01-29"), "bad": ("2026-01-30", "2026-03-31"),
          "recovery": ("2026-04-01", "2026-10-15"), "8yr": ("2018-07-02", "2026-10-15"), "semi-bear-2022": ("2021-11-15", "2022-12-30")}
    for lab, names in STATIC.items():
        P, I = prep(names, LONG); sig, rank, eng = plan_signals(I, names)
        report(lab, names, P, I, sig, rank, eng, Ws)
        tr, eq, _ = run3(P, I, names, PLAN, "2018-07-02", "2026-10-15", sig, rank, eng)
        yr = eq.resample("YE").last(); yr0 = eq.resample("YE").first()
        print("   by year:", {str(k.year): round(float(v / yr0[k] - 1), 2) for k, v in yr.items()})

def rolling_universe(P, pool, n=18, lookback=252, freq="QS", adv=50e6, px=5.0):
    C, V = P["Close"][pool], P["Volume"][pool]
    advs = (C * V).rolling(60).mean(); hist = C.notna().cumsum(); r = C / C.shift(lookback) - 1
    U = pd.DataFrame(False, index=C.index, columns=pool)
    starts = [d for d in pd.date_range(C.index[0], C.index[-1], freq=freq)]
    bounds = [C.index[C.index.searchsorted(d)] for d in starts if C.index.searchsorted(d) < len(C.index)]
    for i, d in enumerate(bounds):
        j = C.index.get_loc(d); prev = C.index[j - 1] if j > 0 else d
        ok = (C.loc[prev] >= px) & (advs.loc[prev] >= adv) & (hist.loc[prev] >= lookback + 5) & r.loc[prev].notna()
        pick = r.loc[prev][ok].sort_values(ascending=False).index[:n]
        e = bounds[i + 1] if i + 1 < len(bounds) else C.index[-1]
        U.loc[d:e, pick] = True
    return U

if which in ("all", "rolling"):
    P, I = prep(POOL, LONG)
    for lab, kw in {"roll top18 by 12m, quarterly": dict(), "roll top18 by 6m, monthly": dict(lookback=126, freq="MS"), "roll top30 by 12m, quarterly": dict(n=30)}.items():
        U = rolling_universe(P, POOL, **kw)
        I["rank63"] = I["ret63"].where(U).rank(axis=1, ascending=False)
        sig, rank, eng = plan_signals(I, POOL, U=U)
        Wr = {"8yr": ("2018-07-02", "2026-10-15"), "sample": ("2023-10-02", "2026-10-15"), "golden": ("2025-10-08", "2026-01-29"), "bad": ("2026-01-30", "2026-03-31"),
              "recovery": ("2026-04-01", "2026-10-15"), "semi-bear-2022": ("2021-11-15", "2022-12-30"), "covid-2020": ("2020-02-03", "2020-06-30"), "q4-2018": ("2018-09-04", "2018-12-31")}
        for w, (s, e) in Wr.items():
            tr, eq, op = run3(P, I, POOL, PLAN, s, e, sig, rank, eng)
            # universe hold: equal-weight of each quarter's picks, rebalanced at picks (approx: mean daily return of members)
            rets = (I["C"] / I["C"].shift(1) - 1).where(U.shift(1).fillna(False)).loc[s:e].mean(axis=1).fillna(0)
            uh = round(float((1 + rets).prod() - 1), 3); smh = P["Close"]["SMH"]
            print(f"{lab:30s} {w:14s} {summ(tr, eq)}  universe-hold={uh}  SMH={round(float(smh.loc[s:e].iloc[-1]/smh.loc[s:e].iloc[0]-1),3)}")
            if w == "8yr":
                yr = eq.resample("YE").last(); yr0 = eq.resample("YE").first(); print("   by year:", {str(k.year): round(float(v / yr0[k] - 1), 2) for k, v in yr.items()})
                T = pd.DataFrame(tr); T["yr"] = pd.to_datetime(T.exit).dt.year; print("   fixed$ by year:", (T.groupby("yr").ret.sum() * 1800).round(0).to_dict())
                print("   by engine:", T.groupby("eng").ret.agg(["size", "mean"]).round(3).to_dict("index"))
                print("   signals/day (mean, p90):", round(float(sig.loc[s:e].sum(axis=1).mean()), 2), int(sig.loc[s:e].sum(axis=1).quantile(.9)))
        if lab.startswith("roll top18 by 12m"):
            print("   universe on 2026-10-01:", sorted(U.loc["2026-10-01":].iloc[0][lambda x: x].index.tolist()))
            print("   universe on 2025-10-01:", sorted(U.loc["2025-10-01":].iloc[0][lambda x: x].index.tolist()))
            print("   universe on 2023-10-02:", sorted(U.loc["2023-10-02":].iloc[0][lambda x: x].index.tolist()))

if which in ("all", "flags"):
    P, I = prep(POOL, LONG); U = rolling_universe(P, POOL, n=30)
    sD, rD = E.signals(I, POOL, dict(PLAN, regime=[]), fam=["dip"]); sD &= U
    O, C = P["Open"][POOL], I["C"]
    fwd = (C.shift(-10) / O.shift(-1) - 1)  # next open -> close 10 days later
    rows = []
    for t in POOL:
        for d in sD.index[sD[t]]:
            if pd.isna(fwd.at[d, t]): continue
            rows.append(dict(name=t, date=d, fwd=fwd.at[d, t], above200=C.at[d, t] > I["sma200"].at[d, t], vol=I["volratio"].at[d, t], vix=I["vix"].at[d],
                             idio=(I["resid5"].at[d, t] <= -0.10) & (I["smh5"].at[d] >= -0.05), smh5=I["smh5"].at[d], yr=d.year))
    F = pd.DataFrame(rows); print("dip events on rolling top-30 universe 2018-2026:", len(F), "mean fwd10 %.3f hit %.2f" % (F.fwd.mean(), (F.fwd > 0).mean()))
    for col, cond in [("above200", F.above200), ("below200", ~F.above200), ("vol>=1.5", F.vol >= 1.5), ("vol<1", F.vol < 1), ("idio", F.idio), ("sector", ~F.idio),
                      ("vix<20", F.vix < 20), ("vix20-25", (F.vix >= 20) & (F.vix < 25)), ("vix25-30", (F.vix >= 25) & (F.vix < 30)), ("vix>30", F.vix >= 30)]:
        s = F[cond]; print(f"   {col:10s} n={len(s):4d} fwd10 {s.fwd.mean():+.3f} hit {(s.fwd>0).mean():.2f}")
    print("   by year:", F.groupby("yr").fwd.agg(["size", "mean"]).round(3).to_dict("index"))
    print("   above200 by period:", F.assign(pre=F.date < "2023-10-01").groupby(["pre", "above200"]).fwd.agg(["size", "mean"]).round(3).to_dict("index"))

if which in ("all", "analog"):
    smh = pd.read_csv(f"{LONG}/SMH.csv", index_col=0, parse_dates=True).Close
    r6 = smh / smh.shift(6) - 1; trig = r6[r6 <= -0.10]
    ev = []; last = None
    for d in trig.index:
        if last is not None and (d - last).days < 15: continue
        last = d; i = smh.index.get_loc(d)
        ev.append(dict(date=d.date(), drop6=round(float(r6[d]), 3), f10=round(float(smh.iloc[min(i + 10, len(smh) - 1)] / smh.iloc[i] - 1), 3),
                       f21=round(float(smh.iloc[min(i + 21, len(smh) - 1)] / smh.iloc[i] - 1), 3), f63=round(float(smh.iloc[min(i + 63, len(smh) - 1)] / smh.iloc[i] - 1), 3),
                       above200=bool(smh.iloc[i] > smh.iloc[max(0, i - 200):i].mean())))
    A = pd.DataFrame(ev); print("SMH -10% in 6 sessions, distinct events since 2017:", len(A)); print(A.to_string(index=False))
    print("   mean f10 %.3f f21 %.3f f63 %.3f ; hit21 %.2f ; above200: f21 %.3f (n=%d) below200: f21 %.3f (n=%d)" % (A.f10.mean(), A.f21.mean(), A.f63.mean(), (A.f21 > 0).mean(),
          A[A.above200].f21.mean(), A.above200.sum(), A[~A.above200].f21.mean(), (~A.above200).sum()))

if which in ("all", "sanity"):
    bad = []
    for f in glob.glob(f"{LONG}/*.csv"):
        df = pd.read_csv(f, index_col=0, parse_dates=True); r = df.Close.pct_change()
        for d, x in r[r.abs() > 0.5].items(): bad.append((Path(f).stem, d.date(), round(float(x), 2), round(float(df.Volume[d]), 0)))
    print("daily |move| > 50%:", len(bad)); print(bad)

if which in ("all", "wf"):
    names = WATCH; P, I = prep(names); grid = []
    for top, rsi_, trail, N in itertools.product((4, 6, 8), (10, 15, 20), (.08, .10, .12), (40, 60)):
        p = dict(PLAN, top=top, rsi=rsi_, exits={"L": dict(trail=trail, S=0.10, N=N), "D": PLAN["exits"]["D"]})
        sig, rank, eng = plan_signals(I, names, p)
        a = summ(*run3(P, I, names, p, "2023-10-02", "2025-03-31", sig, rank, eng)[:2]); b = summ(*run3(P, I, names, p, "2025-04-01", "2026-10-15", sig, rank, eng)[:2])
        grid.append(dict(top=top, rsi=rsi_, trail=trail, N=N, IS=a["ret"], OOS=b["ret"], OOSdd=b["dd"], OOSfixed=b["fixed$"]))
    G = pd.DataFrame(grid); G.to_csv("data/wf_watch.csv", index=False)
    print("walk-forward watch list: IS 2023-10..2025-03, OOS 2025-04..2026-10. cells", len(G))
    print("   best-IS cell:", G.sort_values("IS").iloc[-1].to_dict()); print("   plan cell:", G[(G.top == 6) & (G.rsi == 15) & (G.trail == .10) & (G.N == 40)].iloc[0].to_dict())
    print("   OOS: median %.2f  min %.2f  max %.2f  share positive %.2f ; rank corr IS vs OOS %.2f" % (G.OOS.median(), G.OOS.min(), G.OOS.max(), (G.OOS > 0).mean(), G.IS.rank().corr(G.OOS.rank())))
