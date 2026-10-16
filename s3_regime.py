"""Re-test regime gates and risk controls on long history and no-hindsight universes (round 2 rejected gates in-sample only)."""
import sys, json, glob, numpy as np, pandas as pd
from stress3 import *
from s3_long import rolling_universe, STATIC, LONG, POOL
E.EARN = json.load(open("data/long/earnings_all.json"))
W = {"8yr": ("2018-07-02", "2026-10-15"), "q4-2018": ("2018-09-04", "2018-12-31"), "covid-2020": ("2020-02-03", "2020-06-30"), "semi-bear-2022": ("2021-11-15", "2022-12-30"),
     "sample": ("2023-10-02", "2026-10-15"), "golden": ("2025-10-08", "2026-01-29"), "bad": ("2026-01-30", "2026-03-31"), "recovery": ("2026-04-01", "2026-10-15")}
def add_regimes(P, I):
    smh, qqq = P["Close"]["SMH"], P["Close"]["QQQ"]
    I["smh200"] = smh > smh.rolling(200).mean(); I["smh100"] = smh > smh.rolling(100).mean(); I["qqq200"] = qqq > qqq.rolling(200).mean()
    I["smh200_slope"] = smh.rolling(200).mean() > smh.rolling(200).mean().shift(10)
    I["smh_lowvol"] = (smh / smh.shift(1) - 1).rolling(21).std() * np.sqrt(252) < 0.35
VARIANTS = {
    "plan as written": dict(),
    "L gated SMH>200d": dict(regimeL=["smh200"]),
    "both gated SMH>200d": dict(regimeL=["smh200"], regimeD=["smh200"]),
    "both gated QQQ>200d": dict(regimeL=["qqq200"], regimeD=["qqq200"]),
    "slots 3 if SMH>200d else 1": dict(slots=("smh200", 3, 1)),
    "slots 3 if SMH>200d else 0 (off)": dict(slots=("smh200", 3, 0)),
    "slots 3 if SMH>200d else 2": dict(slots=("smh200", 3, 2)),
    "slots 2 if SMH>200d else 1": dict(slots=("smh200", 2, 1)),
    "slots 3 if QQQ>200d else 1": dict(slots=("qqq200", 3, 1)),
    "slots 3 if SMH 200d rising else 1": dict(slots=("smh200_slope", 3, 1)),
    "slots 3 if SMH 21d vol<35% else 1": dict(slots=("smh_lowvol", 3, 1)),
    "slots 3 if SMH>200d else 1 + breaker": dict(slots=("smh200", 3, 1), breaker=(0.15, 10)),
}
def variant_signals(I, names, v, U=None):
    p = dict(PLAN, regimeL=v.get("regimeL", []), regimeD=v.get("regimeD", []))
    for key in ("regimeL", "regimeD"):  # support "~smh200" = inverse
        for rg in list(p[key]):
            if rg.startswith("~"): I[rg] = ~I[rg[1:]]
    sig, rank, eng = E.signals(I, names, p, tag=True)
    if U is not None: sig &= U.reindex(index=sig.index, columns=names).fillna(False)
    return p, sig, rank, eng
def run_variants(label, names, P, I, U=None, windows=W, years=False):
    add_regimes(P, I)
    for vn, v in VARIANTS.items():
        p, sig, rank, eng = variant_signals(I, names, v, U)
        ms = None
        if "slots" in v: rg, a, b = v["slots"]; ms = I[rg].map(lambda x: a if x else b)
        row = {}
        for w, (s, e) in windows.items():
            tr, eq, op = run3(P, I, names, p, s, e, sig, rank, eng, maxpos_series=ms, cooldown=v.get("cooldown", 0), breaker=v.get("breaker"))
            sm = summ(tr, eq); row[w] = f"{sm['ret']:+.2f}/{sm['dd']:.2f}/{sm['n']}"
            if w == "8yr" and years:
                yr = eq.resample("YE").last(); yr0 = eq.resample("YE").first(); row["years"] = {str(k.year)[2:]: round(float(vv / yr0[k] - 1), 2) for k, vv in yr.items()}
        print(f"{label} | {vn:52s} | " + " | ".join(f"{w} {row[w]}" for w in windows) + (f" | {row.get('years')}" if years else ""))
which = sys.argv[1] if len(sys.argv) > 1 else "all"
print("cells are return/maxDD/trades")
if which in ("all", "twelve"):
    names = [t for t in WATCH if t not in ("NBIS", "INFQ", "CRWV", "SPCX", "SNDK", "ARM")]
    P, I = prep(names, LONG); run_variants("12-name list", names, P, I, years=True)
if which in ("all", "static"):
    for lab in ("U1 2023 retail AI/semi", "U3 semicap/mature"):
        names = STATIC[lab]; P, I = prep(names, LONG); run_variants(lab, names, P, I)
if which in ("all", "watch"):
    P, I = prep(WATCH, LONG); run_variants("his 18 (sample only)", WATCH, P, I, windows={k: W[k] for k in ("sample", "golden", "bad", "recovery")})
if which in ("all", "rolling"):
    P, I = prep(POOL, LONG); U = rolling_universe(P, POOL); I["rank63"] = I["ret63"].where(U).rank(axis=1, ascending=False)
    run_variants("rolling top-18 by 12m", POOL, P, I, U=U, years=True)
