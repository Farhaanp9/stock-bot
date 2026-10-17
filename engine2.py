"""Round-2 engine: indicators, signal families, regime filters, trailing exits, vol sizing. Rules only.
Signal families (p["sig"], list, OR-ed):
  dip      close <= (1 - max(D, k*vol21)) * prior-21d-high                      (round-1 rule)
  pullback close > SMA50 and (RSI2 < rsi  or close <= SMA20 - a*ATR14)           (dip inside an uptrend)
  resid    5-day residual return vs SMH <= -X (own move minus beta*sector move)  (idiosyncratic dip, no sector news)
Filters: gap (no >=G one-day drop in last 5), earn (E1 before/E2 after), regime in {qqq50, smh50, qqq200, vix25, vix30}, trend50 (close > SMA50), trend200.
Exits (first hit at close, executed next open): T target, S stop, N days, trail (close < (1-trail)*highest close since entry), atr_trail (close < highest - k*ATR).
Sizing: equal (equity/maxpos) or vol (risk R of equity per trade over stop distance; cap per position).
"""
import json, sys, itertools
from pathlib import Path
import numpy as np, pandas as pd
DATA = Path(__file__).parent / "data"
WATCH = "AAOI BE IREN LITE NBIS INFQ CRWV AXTI SPCX SNDK MU ARM AMD NVDA IONQ WULF WDC STX".split()
CONTROL = "AAPL MSFT GOOGL AMZN META AVGO TSLA ORCL CRM NFLX".split()
EARN = json.load(open(DATA / "earnings.json")) if (DATA / "earnings.json").exists() else {}  # the nightly job sets E.EARN itself
BENCH = ["SPY", "QQQ", "SMH", "VIX", "IWM"]

def load_panel(names):
    cal = pd.read_csv(DATA / "SPY.csv", index_col=0, parse_dates=True).index
    P = {k: {} for k in ["Open", "High", "Low", "Close", "Volume"]}
    for t in names + BENCH:
        df = pd.read_csv(DATA / f"{t}.csv", index_col=0, parse_dates=True).reindex(cal)
        for k in P: P[k][t] = df[k] if k in df else np.nan
    return {k: pd.DataFrame(v).sort_index() for k, v in P.items()}

def rsi(C, n):
    d = C.diff(); up = d.clip(lower=0); dn = -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False).mean(); ad = dn.ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + au / ad.replace(0, np.nan))

def indicators(P, names):
    C, H, L, V = P["Close"][names], P["High"][names], P["Low"][names], P["Volume"][names]
    I = {}
    I["hi21"] = C.shift(1).rolling(21).max(); I["depth21"] = 1 - C / I["hi21"]
    I["hi63"] = C.shift(1).rolling(63).max(); I["hi252"] = C.shift(1).rolling(252, min_periods=60).max()
    r = C / C.shift(1) - 1
    I["vol21"] = r.rolling(21).std() * np.sqrt(21)
    I["vol21d"] = r.rolling(21).std()
    tr = pd.concat([H - L, (H - C.shift(1)).abs(), (L - C.shift(1)).abs()]).groupby(level=0).max()
    I["atr"] = tr.rolling(14).mean(); I["atrp"] = I["atr"] / C
    I["rsi2"] = rsi(C, 2); I["rsi14"] = rsi(C, 14)
    for n in (20, 50, 200): I[f"sma{n}"] = C.rolling(n).mean()
    I["volratio"] = V / V.rolling(20).mean().shift(1)
    I["ret1"] = r; I["ret5"] = C / C.shift(5) - 1; I["ret21"] = C / C.shift(21) - 1; I["ret63"] = C / C.shift(63) - 1
    smh = P["Close"]["SMH"]; rs = smh / smh.shift(1) - 1
    cov = r.rolling(120, min_periods=60).cov(rs); var = rs.rolling(120, min_periods=60).var()
    I["beta"] = cov.div(var, axis=0)
    I["resid5"] = I["ret5"] - I["beta"].mul(smh / smh.shift(5) - 1, axis=0)
    I["z20"] = (C - I["sma20"]) / I["atr"]
    I["rank63"] = I["ret63"].rank(axis=1, ascending=False)
    I["rs63"] = I["ret63"].sub(smh / smh.shift(63) - 1, axis=0)
    I["off252"] = 1 - C / I["hi252"]
    I["worst5"] = r.rolling(5).min()
    qqq = P["Close"]["QQQ"]; vix = P["Close"]["VIX"].ffill()
    I["qqq50"] = qqq > qqq.rolling(50).mean(); I["qqq200"] = qqq > qqq.rolling(200).mean()
    I["smh50"] = smh > smh.rolling(50).mean(); I["smh20"] = smh > smh.rolling(20).mean()
    I["vix"] = vix; I["smh5"] = smh / smh.shift(5) - 1; I["qqq5"] = qqq / qqq.shift(5) - 1
    I["C"] = C
    return I

def earnings_mask(idx, names, before, after):
    M = pd.DataFrame(False, index=idx, columns=names)
    for t in names:
        for ds in EARN.get(t, []):
            d = pd.Timestamp(ds)
            if d > idx[-1]:
                gap_days = len(pd.bdate_range(idx[-1], d)) - 1
                if gap_days <= after: M.iloc[len(idx) - (after - gap_days) - 1:, M.columns.get_loc(t)] = True
                continue
            if d < idx[0]: continue
            i = idx.searchsorted(d); lo, hi = max(0, i - after), min(len(idx), i + before + 1)
            M.iloc[lo:hi, M.columns.get_loc(t)] = True
    return M

def signals(I, names, p, fam=None, tag=False):
    """tag=True returns (sig, rank, engine) where engine is a frame of 'L'/'D' labels (L wins ties)."""
    C = I["C"]; sig = pd.DataFrame(False, index=C.index, columns=names)
    fam = fam or p.get("sig", ["dip"])
    if tag:
        sL, rL = signals(I, names, dict(p, regime=p.get("regimeL", [])), fam=[f for f in fam if f == "leader"] or ["none"])
        sD, rD = signals(I, names, dict(p, regime=p.get("regimeD", [])), fam=[f for f in fam if f != "leader"] or ["none"])
        eng = pd.DataFrame(np.where(sL, "L", np.where(sD, "D", "")), index=C.index, columns=names)
        rank = rL.where(sL, rD); rank = rank.where(sL | sD, 0)
        return (sL | sD), rank, eng
    if "dip" in fam:
        D = np.maximum(p.get("D", 0.15), p.get("k", 1.5) * I["vol21"]) if p.get("k") else p.get("D", 0.15)
        sig |= C <= (1 - D) * I["hi21"]
    if "pullback" in fam:
        cond = C > I["sma50"]
        sub = pd.DataFrame(False, index=C.index, columns=names)
        if p.get("rsi"): sub |= I["rsi2"] < p["rsi"]
        if p.get("a"): sub |= I["z20"] <= -p["a"]
        sig |= cond & sub
    if "leader" in fam:  # pullback in a leader: above 50-day, top-N 63-day return on the list, short-term oversold
        cond = (C > I["sma50"]) & (I["rank63"] <= p.get("top", 5)) & (I["rs63"] > 0)
        sub = pd.DataFrame(False, index=C.index, columns=names)
        if p.get("rsi"): sub |= I["rsi2"] < p["rsi"]
        if p.get("a"): sub |= I["z20"] <= -p["a"]
        sig |= cond & sub
    if "resid" in fam:
        sig |= (I["resid5"] <= -p.get("X", 0.10)) & (I["smh5"] >= -p.get("Y", 0.05))
    if p.get("gap"): sig &= ~(I["worst5"] <= -p["gap"])
    if p.get("earn"): sig &= ~earnings_mask(C.index, names, *p["earn"])
    if p.get("trend50"): sig &= C > I["sma50"]
    if p.get("trend200"): sig &= C > I["sma200"]
    for rg in p.get("regime", []):
        if rg.startswith("vix"): sig = sig.mul(I["vix"] < float(rg[3:]), axis=0)
        else: sig = sig.mul(I[rg], axis=0)
    rank = (I["depth21"] / I["vol21"]).fillna(0)  # drop measured in monthly-vol units
    if fam == ["leader"]: rank = I["ret63"].fillna(0)  # leaders: strongest first
    return sig.fillna(False).astype(bool), rank

def run(P, I, names, p, start, end, capital=5400, maxpos=3, slip=0.001):
    tagged = "exits" in p
    if tagged: sig, rank, eng = signals(I, names, p, tag=True)
    else: sig, rank = signals(I, names, p)
    O, C, ATR = P["Open"][names], I["C"], I["atr"]
    dates = C.index[(C.index >= start) & (C.index <= end)]
    cash, pos, trades, equity = capital, {}, [], []
    entry_eng = {}
    pending_entry, pending_exit, locked = [], {}, {}
    days_in = 0
    for d in dates:
        o, c = O.loc[d], C.loc[d]
        for t, why in pending_exit.items():
            if t in pos and not np.isnan(o[t]):
                st = pos.pop(t); px = o[t] * (1 - slip); cash += st["sh"] * px
                trades.append(dict(name=t, entry=st["d0"], exit=d, entry_px=st["px0"], exit_px=px, reason=why, size=st["size"], eng=st["eng"],
                                   pnl=st["sh"] * (px - st["px0"]), ret=px / st["px0"] - 1, days=int(C.index.get_loc(d) - C.index.get_loc(st["d0"]))))
                if p.get("cooldown") and px < st["px0"]: locked[t] = d + pd.Timedelta(days=p["cooldown"])
        pending_exit = {}
        eq = cash + sum(st["sh"] * c[t] for t, st in pos.items())
        for t in pending_entry:
            if t in pos or len(pos) >= maxpos or np.isnan(o[t]): continue
            px = o[t] * (1 + slip)
            if p.get("sizing") == "vol":
                stop_frac = max(p.get("S") or 0.0, p.get("atr_k", 2.0) * ATR.at[d, t] / px) if p.get("atr_stop") else (p.get("S") or 0.10)
                size = min(p.get("risk", 0.03) * eq / stop_frac, p.get("cap", 0.5) * eq, cash)
            else:
                size = min(eq / maxpos, cash)
            if size < 100: continue
            sh = size / px; cash -= size
            pos[t] = dict(sh=sh, px0=px, d0=d, hi=px, size=size, eng=(entry_eng.get(t, "") if tagged else ""))
        pending_entry = []
        for t, st in list(pos.items()):
            st["hi"] = max(st["hi"], c[t]); r = c[t] / st["px0"] - 1
            held = C.index.get_loc(d) - C.index.get_loc(st["d0"])
            x = p["exits"][st["eng"]] if tagged else p
            if x.get("T") is not None and r >= x["T"]: pending_exit[t] = "target"
            elif x.get("S") is not None and r <= -x["S"]: pending_exit[t] = "stop"
            elif x.get("trail") is not None and c[t] <= st["hi"] * (1 - x["trail"]) and st["hi"] > st["px0"] * (1 + x.get("trail_after", 0.0)): pending_exit[t] = "trail"
            elif x.get("atr_trail") is not None and c[t] <= st["hi"] - x["atr_trail"] * ATR.at[d, t]: pending_exit[t] = "trail"
            elif x.get("N") is not None and held >= x["N"]: pending_exit[t] = "time"
        if pos: days_in += 1
        cands = [t for t in names if sig.at[d, t] and t not in pos and not (t in locked and d <= locked[t])]
        cands.sort(key=lambda t: -rank.at[d, t])
        pending_entry = cands[: max(0, maxpos - len(pos) + len(pending_exit))]
        if tagged: entry_eng = {t: eng.at[d, t] for t in pending_entry}
        equity.append((d, cash + sum(st["sh"] * c[t] for t, st in pos.items())))
    open_pos = [dict(name=t, entry=st["d0"], entry_px=st["px0"], last=C.loc[dates[-1], t], ret=C.loc[dates[-1], t] / st["px0"] - 1) for t, st in pos.items()]
    eqs = pd.Series(dict(equity))
    return trades, eqs, open_pos, days_in / len(dates)

def summarize(trades, eqs, exposure, capital=5400):
    tr = pd.DataFrame(trades)
    out = dict(trades=len(tr), ret=round(float(eqs.iloc[-1] / capital - 1), 3), max_dd=round(float((eqs / eqs.cummax() - 1).min()), 3), exposure=round(exposure, 2))
    if len(tr):
        w = tr[tr.pnl > 0]; l = tr[tr.pnl <= 0]
        out.update(win=round(len(w) / len(tr), 2), avg_win=round(float(w.ret.mean()), 3) if len(w) else 0, avg_loss=round(float(l.ret.mean()), 3) if len(l) else 0,
                   avg_days=round(float(tr.days.mean()), 1), pf=round(float(w.pnl.sum() / -l.pnl.sum()), 2) if len(l) and l.pnl.sum() < 0 else None,
                   by=tr.reason.value_counts().to_dict())
    return out

def costs(trades, rate=0.12):
    tr = pd.DataFrame(trades)
    if not len(tr): return dict(tax=0, wash=0, wash_deferred=0)
    tr["year"] = pd.to_datetime(tr["exit"]).dt.year
    tax = sum(max(0, g) * rate for g in tr.groupby("year").pnl.sum())
    wash, deferred = 0, 0.0
    for _, t in tr[tr.pnl < 0].iterrows():
        later = tr[(tr.name == t["name"]) & (tr.entry > t["exit"]) & (tr.entry <= t["exit"] + pd.Timedelta(days=30))]
        if len(later): wash += 1; deferred += -t.pnl
    return dict(tax=round(tax, 0), wash=wash, wash_deferred=round(deferred, 0), by_year=tr.groupby("year").pnl.sum().round(0).to_dict())

WINDOWS = {"full": ("2023-10-02", "2026-10-14"), "before": ("2023-10-02", "2025-10-07"), "golden": ("2025-10-08", "2026-01-29"),
           "bad": ("2026-01-30", "2026-03-31"), "recovery": ("2026-04-01", "2026-10-14")}

def buy_hold(C, names, start, end, capital=5400):
    sub = C.loc[start:end, names]
    avail = [t for t in names if sub[t].first_valid_index() == sub.index[0]]
    first = sub[avail].iloc[0]; curve = sum(capital / len(avail) * sub[t] / first[t] for t in avail)
    return round(float(curve.iloc[-1] / capital - 1), 3), len(avail)

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "watch"
    names = WATCH if which == "watch" else CONTROL
    P = load_panel(names); I = indicators(P, names)
    mode = sys.argv[2] if len(sys.argv) > 2 else "sweep"
    base = dict(gap=0.20, earn=(3, 5))
    if mode == "sweep":
        SIGS = {"dip1.5": dict(sig=["dip"], D=0.15, k=1.5), "dip1.0": dict(sig=["dip"], D=0.10, k=1.0),
                "pb_rsi10": dict(sig=["pullback"], rsi=10), "pb_rsi5": dict(sig=["pullback"], rsi=5), "pb_atr2": dict(sig=["pullback"], a=2.0),
                "resid10": dict(sig=["resid"], X=0.10, Y=0.05), "dip+pb": dict(sig=["dip", "pullback"], D=0.15, k=1.5, rsi=10),
                "dip_t50": dict(sig=["dip"], D=0.15, k=1.5, trend50=True)}
        REG = {"none": [], "qqq50": ["qqq50"], "smh50": ["smh50"], "smh20": ["smh20"], "qqq50+vix25": ["qqq50", "vix25"], "vix30": ["vix30"]}
        EX = {"T10S10N20": dict(T=0.10, S=0.10, N=20), "T15S10N20": dict(T=0.15, S=0.10, N=20), "tr8S10N20": dict(trail=0.08, S=0.10, N=20),
              "tr10S10N40": dict(trail=0.10, S=0.10, N=40), "tr15S12N60": dict(trail=0.15, S=0.12, N=60), "atr3S10N40": dict(atr_trail=3.0, S=0.10, N=40),
              "tr10a5S10N40": dict(trail=0.10, trail_after=0.05, S=0.10, N=40), "T20tr8S10N40": dict(T=0.20, trail=0.08, S=0.10, N=40)}
        rows = []
        for (sn, sp), (rn, rp), (en, ep) in itertools.product(SIGS.items(), REG.items(), EX.items()):
            p = dict(base); p.update(sp); p["regime"] = rp; p.update(ep)
            for w, (s, e) in WINDOWS.items():
                tr, eq, op, ex = run(P, I, names, p, s, e)
                sm = summarize(tr, eq, ex); sm.update(window=w, sig=sn, regime=rn, exit=en); rows.append(sm)
        df = pd.DataFrame(rows); df.to_csv(DATA / f"sweep2_{which}.csv", index=False); print("rows", len(df))
    else:
        p = dict(base); p.update(json.loads(mode))
        for w, (s, e) in WINDOWS.items():
            tr, eq, op, ex = run(P, I, names, p, s, e)
            bh, n = buy_hold(I["C"], names, s, e)
            print(f"\n== {w} {s}..{e}  hold({n})={bh}  QQQ={round(float(P['Close']['QQQ'].loc[s:e].iloc[-1]/P['Close']['QQQ'].loc[s:e].iloc[0]-1),3)}")
            print(json.dumps(summarize(tr, eq, ex))); print("open:", [(o['name'], str(o['entry'].date()), round(o['ret'], 3)) for o in op])
            if w == "full":
                print("costs:", costs(tr)); t = pd.DataFrame(tr)
                if "eng" in t: print("by engine:", t.groupby("eng").agg(n=("pnl", "size"), pnl=("pnl", "sum"), win=("ret", lambda r: (r > 0).mean()), avg=("ret", "mean")).round(3).to_dict("index"))
                yr = eq.resample("YE").last(); yr0 = eq.resample("YE").first(); print("by year:", {str(k.year): round(float(v / yr0[k] - 1), 2) for k, v in yr.items()})
                ddc = eq / eq.cummax() - 1; print("worst drawdown trough:", ddc.idxmin().date(), round(float(ddc.min()), 3))
            if w in ("full",) and len(sys.argv) > 3:
                pd.DataFrame(tr).to_csv(DATA / f"trades2_{which}.csv", index=False)
                t = pd.DataFrame(tr); print(t.groupby("name").agg(n=("pnl", "size"), pnl=("pnl", "sum"), win=("ret", lambda r: (r > 0).mean())).round(2).sort_values("pnl").to_string())
            if w == "bad" and len(tr):
                print(pd.DataFrame(tr)[["name", "entry", "exit", "ret", "reason"]].to_string(index=False))
