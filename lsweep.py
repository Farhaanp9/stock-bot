"""Robustness sweep for the leader-pullback family on watch and control baskets."""
import itertools, sys, pandas as pd
from engine2 import load_panel, indicators, run, summarize, WINDOWS, WATCH, CONTROL
which = sys.argv[1]; names = WATCH if which == "watch" else CONTROL
P = load_panel(names); I = indicators(P, names)
rows = []
for top, rsi, trail, S, N in itertools.product([4, 5, 6, 8, 10], [10, 15, 20], [0.08, 0.10, 0.12, 0.15], [0.08, 0.10], [40, 60]):
    p = dict(sig=["leader"], top=top, rsi=rsi, trail=trail, S=S, N=N, gap=0.20, earn=(3, 5))
    for w, (s, e) in WINDOWS.items():
        tr, eq, op, ex = run(P, I, names, p, s, e)
        sm = summarize(tr, eq, ex); sm.update(window=w, top=top, rsi=rsi, trail=trail, S=S, N=N); rows.append(sm)
df = pd.DataFrame(rows); df.to_csv(f"data/lsweep_{which}.csv", index=False); print("rows", len(df))
