"""Round-3 stress harness. Reuses engine2 indicators/signals; adds entry-price modes, slippage, universe masks,
random-timing controls, bootstrap, trade-removal, long-history windows, no-hindsight universes."""
import json, sys, itertools, time
from pathlib import Path
import numpy as np, pandas as pd
import engine2 as E

PLAN = dict(sig=["leader", "dip"], top=6, rsi=15, D=0.15, k=1.5, gap=0.20, earn=(3, 5),
            exits={"L": dict(trail=0.10, S=0.10, N=40), "D": dict(trail=0.08, S=0.10, N=20)})
WATCH = E.WATCH; CONTROL = E.CONTROL

def load_panel(names, d="data", bench=("SPY", "QQQ", "SMH", "VIX", "IWM")):
    D = Path(__file__).parent / d
    cal = pd.read_csv(D / "SPY.csv", index_col=0, parse_dates=True).index
    P = {k: {} for k in ["Open", "High", "Low", "Close", "Volume"]}
    for t in list(names) + list(bench):
        f = D / f"{t}.csv"
        if not f.exists():
            for k in P: P[k][t] = pd.Series(np.nan, index=cal)
            continue
        df = pd.read_csv(f, index_col=0, parse_dates=True).reindex(cal)
        for k in P: P[k][t] = df[k] if k in df else pd.Series(np.nan, index=cal)
    return {k: pd.DataFrame(v).sort_index() for k, v in P.items()}

def prep(names, d="data", U=None):
    P = load_panel(names, d); I = E.indicators(P, names)
    if U is not None:  # universe mask: leaders ranked only inside the universe
        I["rank63"] = I["ret63"].where(U).rank(axis=1, ascending=False)
    return P, I

def plan_signals(I, names, p=PLAN, U=None):
    sig, rank, eng = E.signals(I, names, p, tag=True)
    if U is not None: sig &= U.reindex(index=sig.index, columns=names).fillna(False)
    return sig, rank, eng

def run3(P, I, names, p, start, end, sig, rank, eng, capital=5400, maxpos=3, slip=0.001, entry="open", void=None, exit_mode="open", maxpos_series=None, cooldown=0, breaker=None):
    """entry: open | close | mid | high | low. void: skip entry if open > (1+void)*prev close. exit_mode: open | close."""
    O, H, L, C, ATR = P["Open"][names], P["High"][names], P["Low"][names], I["C"], I["atr"]
    MID = (O + H + L + C) / 4
    EP = {"open": O, "close": C, "mid": MID, "high": H, "low": L}[entry]
    XP = O if exit_mode == "open" else C
    dates = C.index[(C.index >= start) & (C.index <= end)]
    cash, pos, trades, equity = capital, {}, [], []
    pending_entry, pending_exit, entry_eng, prevc = [], {}, {}, None
    locked, pause_until, eqhist = {}, None, []
    for d in dates:
        o, c, ep, xp, lo = O.loc[d], C.loc[d], EP.loc[d], XP.loc[d], L.loc[d]
        for t, why in pending_exit.items():
            if t in pos and not np.isnan(xp[t]):
                st = pos.pop(t); px = xp[t] * (1 - slip); cash += st["sh"] * px
                if cooldown and px < st["px0"]: locked[t] = C.index[min(C.index.get_loc(d) + cooldown, len(C.index) - 1)]
                trades.append(dict(name=t, entry=st["d0"], exit=d, entry_px=st["px0"], exit_px=px, reason=why, size=st["size"], eng=st["eng"],
                                   pnl=st["sh"] * (px - st["px0"]), ret=px / st["px0"] - 1, mae=st["mae"] / st["px0"] - 1, ret63=st["r63"],
                                   stop_level=-(p["exits"][st["eng"]]["S"]) if why == "stop" else np.nan,
                                   days=int(C.index.get_loc(d) - C.index.get_loc(st["d0"]))))
        pending_exit = {}
        eq = cash + sum(st["sh"] * c[t] for t, st in pos.items())
        mp = int(maxpos_series[d]) if maxpos_series is not None else maxpos
        if breaker and pause_until is not None and d <= pause_until: mp = 0
        for t in pending_entry:
            if t in pos or len(pos) >= mp or np.isnan(ep[t]): continue
            if void is not None and prevc is not None and o[t] > (1 + void) * prevc[t]: continue
            px = ep[t] * (1 + slip); size = min(eq / maxpos, cash)
            if size < 100: continue
            sh = size / px; cash -= size
            pos[t] = dict(sh=sh, px0=px, d0=d, hi=px, size=size, eng=entry_eng.get(t, "D"), mae=px, r63=I["ret63"].at[d, t])
        pending_entry = []
        for t, st in list(pos.items()):
            st["hi"] = max(st["hi"], c[t]); st["mae"] = min(st["mae"], lo[t]) if not np.isnan(lo[t]) else st["mae"]
            r = c[t] / st["px0"] - 1; held = C.index.get_loc(d) - C.index.get_loc(st["d0"])
            x = p["exits"][st["eng"]]
            if x.get("S") is not None and r <= -x["S"]: pending_exit[t] = "stop"
            elif x.get("trail") is not None and c[t] <= st["hi"] * (1 - x["trail"]) and st["hi"] > st["px0"]: pending_exit[t] = "trail"
            elif x.get("N") is not None and held >= x["N"]: pending_exit[t] = "time"
        eqnow = cash + sum(st["sh"] * c[t] for t, st in pos.items()); eqhist.append(eqnow)
        if breaker and len(eqhist) > 21 and eqnow < (1 - breaker[0]) * max(eqhist[-22:]) and (pause_until is None or d > pause_until):
            pause_until = C.index[min(C.index.get_loc(d) + breaker[1], len(C.index) - 1)]
        cands = [t for t in names if sig.at[d, t] and t not in pos and not (t in locked and d <= locked[t])]
        cands.sort(key=lambda t: -rank.at[d, t])
        pending_entry = cands[: max(0, mp - len(pos) + len(pending_exit))]
        entry_eng = {t: (eng.at[d, t] or "D") for t in pending_entry}
        prevc = c
        equity.append((d, cash + sum(st["sh"] * c[t] for t, st in pos.items())))
    eqs = pd.Series(dict(equity))
    open_pos = [dict(name=t, entry=st["d0"], ret=C.loc[dates[-1], t] / st["px0"] - 1, eng=st["eng"]) for t, st in pos.items()]
    return trades, eqs, open_pos

def summ(trades, eqs, capital=5400, fixed=1800):
    tr = pd.DataFrame(trades)
    out = dict(n=len(tr), ret=round(float(eqs.iloc[-1] / capital - 1), 3), dd=round(float((eqs / eqs.cummax() - 1).min()), 3))
    if len(tr):
        out["fixed$"] = round(float((tr.ret * fixed).sum()), 0)
        out["win"] = round(float((tr.ret > 0).mean()), 2); out["avg"] = round(float(tr.ret.mean()), 4)
        w, l = tr[tr.ret > 0], tr[tr.ret <= 0]
        out["pf"] = round(float((w.ret.sum()) / -(l.ret.sum())), 2) if len(l) and l.ret.sum() < 0 else None
    # drawdown duration (trading days from peak to recovery), worst 21-day
    cm = eqs.cummax(); under = eqs < cm; longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0; longest = max(longest, cur)
    out["dd_days"] = int(longest); out["worst21"] = round(float((eqs / eqs.shift(21) - 1).min()), 3)
    return out

def hold(C, names, start, end):
    sub = C.loc[start:end, names]; avail = [t for t in names if sub[t].first_valid_index() == sub.index[0]]
    if not avail: return None, 0
    first = sub[avail].iloc[0]; curve = sum(sub[t] / first[t] for t in avail) / len(avail)
    return round(float(curve.iloc[-1] - 1), 3), len(avail)
