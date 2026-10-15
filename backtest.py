"""Dip-buy backtest for Farhaan's watchlist. Rules only; no judgment inside.

Signal at close of day t:  close_t <= (1 - D) * max(close[t-21 .. t-1])         (month drop)
                     or    close_t <= (1 - W) * close[t-5]  (week drop, optional)
Disqualifiers (each optional): below N-day SMA · a single-day close drop >= G in the last 5 days ·
                               an earnings date within the last E1 or next E2 trading days · SPY below its 200-day SMA
Entry: next day's open (he reads at night, acts in the morning).  Slippage per side: SLIP.
Exit (first hit, evaluated at close, executed next open): target +T · stop -S · time N days.
Portfolio: start CAPITAL, max MAXPOS positions, each = equity/MAXPOS at entry, one per name, never add to a loser.
"""
import json, sys, itertools
from pathlib import Path
import numpy as np, pandas as pd

DATA = Path(__file__).parent / "data"
WATCH = "AAOI BE IREN LITE NBIS INFQ CRWV AXTI SPCX GGLL SNDK MU ARM AMD NVDA IONQ WULF WDC STX UAMY".split()
CONTROL = "AAPL MSFT GOOGL AMZN META AVGO TSLA ORCL CRM NFLX".split()
EARN = json.load(open(DATA / "earnings.json"))


def load(names):
    closes, opens = {}, {}
    for t in names:
        df = pd.read_csv(DATA / f"{t}.csv", index_col=0, parse_dates=True)
        closes[t], opens[t] = df["Close"], df["Open"]
    C = pd.DataFrame(closes).sort_index()
    O = pd.DataFrame(opens).reindex(C.index)
    return C, O


def earnings_mask(C, names, before, after):
    """True on days within `before` trading days after an earnings date or `after` trading days before one."""
    M = pd.DataFrame(False, index=C.index, columns=names)
    pos = {d: i for i, d in enumerate(C.index)}
    idx = C.index
    for t in names:
        for ds in EARN.get(t, []):
            d = pd.Timestamp(ds)
            if d > idx[-1]:  # future date: count business days from the last bar; mark only if within `after`
                gap_days = len(pd.bdate_range(idx[-1], d)) - 1
                if gap_days <= after:
                    M.iloc[len(idx) - (after - gap_days) - 1:, M.columns.get_loc(t)] = True
                continue
            if d < idx[0]:
                continue
            i = idx.searchsorted(d)
            lo, hi = max(0, i - after), min(len(idx), i + before + 1)
            M.iloc[lo:hi, M.columns.get_loc(t)] = True
    return M


def signals(C, O, names, p, spy):
    hi21 = C.shift(1).rolling(21).max()
    D = p["D"]
    if p.get("k"):
        vol = (C / C.shift(1) - 1).rolling(21).std() * np.sqrt(21)
        D = np.maximum(p["D"], p["k"] * vol)
    sig = C <= (1 - D) * hi21
    if p.get("W"):
        sig |= C <= (1 - p["W"]) * C.shift(5)
    if p.get("trend"):
        sig &= C > C.rolling(p["trend"]).mean()
    if p.get("gap"):
        day = C / C.shift(1) - 1
        sig &= ~(day <= -p["gap"]).rolling(5).max().astype(bool)
    if p.get("earn"):
        sig &= ~earnings_mask(C, names, *p["earn"])
    if p.get("mkt"):
        sig = sig.mul(spy > spy.rolling(p["mkt"]).mean(), axis=0)
    if p.get("breadth"):
        sig = sig.mul(sig.sum(axis=1) <= p["breadth"], axis=0)
    depth = 1 - C / hi21  # how far below the 21-day high, for ranking
    return sig.fillna(False), depth


def run(C, O, names, p, start, end, spy, capital=5400, maxpos=3, slip=0.001):
    sig, depth = signals(C, O, names, p, spy)
    dates = C.index[(C.index >= start) & (C.index <= end)]
    cash, pos, trades, equity = capital, {}, [], []
    pending_entry, pending_exit = [], {}
    locked = {}  # name -> date until which it may not be re-entered (wash-sale cooldown after a loss)
    for d in dates:
        o, c = O.loc[d], C.loc[d]
        # exits at today's open
        for t, why in pending_exit.items():
            if t in pos and not np.isnan(o[t]):
                sh, px0, d0 = pos.pop(t)
                px = o[t] * (1 - slip)
                cash += sh * px
                trades.append(dict(name=t, entry=d0, exit=d, entry_px=px0, exit_px=px, reason=why,
                                   pnl=sh * (px - px0), ret=px / px0 - 1, days=int(C.index.get_loc(d) - C.index.get_loc(d0))))
                if p.get("cooldown") and px < px0:
                    locked[t] = d + pd.Timedelta(days=p["cooldown"])
        pending_exit = {}
        # entries at today's open
        eq = cash + sum(sh * c[t] for t, (sh, _, _) in pos.items())
        for t in pending_entry:
            if t in pos or len(pos) >= maxpos or np.isnan(o[t]):
                continue
            size = min(eq / maxpos, cash)
            if size < 100:
                continue
            px = o[t] * (1 + slip)
            sh = size / px
            cash -= size
            pos[t] = (sh, px, d)
        pending_entry = []
        # evaluate at close
        for t, (sh, px0, d0) in list(pos.items()):
            r = c[t] / px0 - 1
            held = C.index.get_loc(d) - C.index.get_loc(d0)
            if p.get("T") is not None and r >= p["T"]:
                pending_exit[t] = "target"
            elif p.get("S") is not None and r <= -p["S"]:
                pending_exit[t] = "stop"
            elif p.get("N") is not None and held >= p["N"]:
                pending_exit[t] = "time"
        cands = [t for t in names if sig.at[d, t] and t not in pos and not (t in locked and d <= locked[t])]
        cands.sort(key=lambda t: -depth.at[d, t])
        pending_entry = cands[: max(0, maxpos - len(pos) + len(pending_exit))]
        equity.append((d, cash + sum(sh * c[t] for t, (sh, _, _) in pos.items())))
    # mark open positions to market at the end
    open_pos = [dict(name=t, entry=d0, entry_px=px0, last=C.loc[dates[-1], t], ret=C.loc[dates[-1], t] / px0 - 1) for t, (sh, px0, d0) in pos.items()]
    eqs = pd.Series(dict(equity))
    return trades, eqs, open_pos


def summarize(trades, eqs, capital=5400):
    tr = pd.DataFrame(trades)
    out = dict(trades=len(tr), end_equity=round(float(eqs.iloc[-1]), 0), ret=round(float(eqs.iloc[-1] / capital - 1), 3))
    dd = (eqs / eqs.cummax() - 1).min()
    out["max_dd"] = round(float(dd), 3)
    if len(tr):
        w = tr[tr.pnl > 0]; l = tr[tr.pnl <= 0]
        out.update(win_rate=round(len(w) / len(tr), 2), avg_win=round(float(w.ret.mean()), 3) if len(w) else 0,
                   avg_loss=round(float(l.ret.mean()), 3) if len(l) else 0, avg_days=round(float(tr.days.mean()), 1),
                   profit_factor=round(float(w.pnl.sum() / -l.pnl.sum()), 2) if len(l) and l.pnl.sum() < 0 else None,
                   by_reason=tr.reason.value_counts().to_dict())
    return out


def costs(trades, rate=0.12):
    """Short-term tax by calendar year on net gains; wash-sale count: a loss sale with a rebuy of the same name within 30 days after."""
    tr = pd.DataFrame(trades)
    if not len(tr):
        return dict(tax=0, wash=0, wash_deferred=0)
    tr["year"] = pd.to_datetime(tr["exit"]).dt.year
    tax = sum(max(0, g) * rate for g in tr.groupby("year").pnl.sum())
    wash, deferred = 0, 0.0
    for _, t in tr[tr.pnl < 0].iterrows():
        later = tr[(tr.name == t["name"]) & (tr.entry > t["exit"]) & (tr.entry <= t["exit"] + pd.Timedelta(days=30))]
        if len(later):
            wash += 1; deferred += -t.pnl
    return dict(tax=round(tax, 0), wash=wash, wash_deferred=round(deferred, 0), by_year=tr.groupby("year").pnl.sum().round(0).to_dict())


def buy_hold(C, names, start, end, capital=5400):
    sub = C.loc[start:end, names]
    first = sub.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
    avail = [t for t in names if not np.isnan(first[t]) and sub[t].first_valid_index() == sub.index[0]]
    w = capital / len(avail)
    curve = sum(w * sub[t] / first[t] for t in avail)
    return round(float(curve.iloc[-1] / capital - 1), 3), avail


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "watch"
    names = WATCH if which == "watch" else CONTROL
    if len(sys.argv) > 2 and sys.argv[2].startswith("{"):
        names = [t for t in names if t not in json.loads(sys.argv[2]).get("exclude", [])]
    C, O = load(names + ["SPY", "QQQ"])
    spy = C["SPY"]; C = C.drop(columns=["SPY", "QQQ"]); O = O.drop(columns=["SPY", "QQQ"])
    windows = {"full": ("2023-10-02", "2026-10-14"), "before": ("2023-10-02", "2025-10-07"),
               "golden": ("2025-10-08", "2026-01-29"), "after": ("2026-01-30", "2026-10-14")}
    base = dict(D=0.15, W=None, T=0.10, S=0.10, N=20, trend=None, gap=None, earn=None, mkt=None)
    grid = dict(D=[0.10, 0.15, 0.20, 0.25], T=[0.10, 0.15, 0.20], S=[0.08, 0.10, 0.15, None], N=[15, 30, None],
                trend=[None, 200], gap=[None, 0.20], earn=[None, (3, 5)])
    if len(sys.argv) > 2 and sys.argv[2] == "ksweep":
        grid = dict(D=[0.10, 0.15], k=[1.0, 1.25, 1.5, 1.75, 2.0], T=[0.10, 0.15, 0.20], S=[0.08, 0.10, 0.15], N=[20],
                    trend=[None], gap=[None, 0.20], earn=[None, (3, 5)])
    mode = sys.argv[2] if len(sys.argv) > 2 else "sweep"
    rows = []
    if mode in ("sweep", "ksweep"):
        keys = list(grid)
        for combo in itertools.product(*grid.values()):
            p = dict(base); p.update(dict(zip(keys, combo)))
            for wname, (s, e) in windows.items():
                tr, eq, op = run(C, O, names, p, s, e, spy)
                sm = summarize(tr, eq); sm.update(window=wname, **{k: str(v) for k, v in p.items()})
                rows.append(sm)
        df = pd.DataFrame(rows)
        df.to_csv(DATA / f"{mode}_{which}.csv", index=False)
        print("sweep rows", len(df))
    else:
        p = json.loads(mode)
        for wname, (s, e) in windows.items():
            tr, eq, op = run(C, O, names, p, s, e, spy)
            sm = summarize(tr, eq); bh, avail = buy_hold(C, names, s, e)
            print(f"\n== {wname} {s}..{e}  buy&hold eq-wt({len(avail)} names)={bh}  SPY={round(float(spy.loc[s:e].iloc[-1]/spy.loc[s:e].iloc[0]-1),3)}")
            print(json.dumps(sm)); print(costs(tr)); print("open:", [(o['name'], str(o['entry'].date()), round(o['ret'],3)) for o in op])
            if wname == "full":
                pd.DataFrame(tr).to_csv(DATA / f"trades_{which}.csv", index=False)
                print(pd.DataFrame(tr).groupby("name").agg(n=("pnl", "size"), pnl=("pnl", "sum"), win=("ret", lambda r: (r > 0).mean())).round(2).sort_values("pnl").to_string())
