"""Nightly analyst board: every number from data files, printed as markdown. No model, no judgment.
Usage: python board.py [YYYY-MM-DD]  → markdown on stdout.
Two engines. L = leaders (pullback in a name leading the list, ride with a trailing stop).
             D = deep dips (a drop unusual for the name, bounce, fixed target)."""
import json, sys
import numpy as np, pandas as pd
from engine2 import load_panel, indicators, signals, earnings_mask, WATCH, EARN, DATA
L_RULE = dict(sig=["leader"], top=6, rsi=15, gap=0.20, earn=(3, 5))
D_RULE = dict(sig=["dip"], D=0.15, k=1.5, gap=0.20, earn=(3, 5))
L_EXIT = dict(trail=0.10, S=0.10, N=40); D_EXIT = dict(trail=0.08, S=0.10, N=20)
P = load_panel(WATCH); I = indicators(P, WATCH)
F = json.load(open(DATA / "fundamentals.json"))
d = pd.Timestamp(sys.argv[1]) if len(sys.argv) > 1 else I["C"].index[-1]
C = I["C"]; i = C.index.get_loc(d)
def pct(x, nd=1): return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:+.{nd}f}%"
def num(x, nd=1): return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"
sigL, _ = signals(I, WATCH, L_RULE); sigD, rankD = signals(I, WATCH, D_RULE)
sigR, _ = signals(I, WATCH, dict(sig=["resid"], X=0.10, Y=0.05, gap=0.20, earn=(3, 5)))
emask = earnings_mask(C.index, WATCH, 3, 5)
vix = P["Close"]["VIX"].ffill(); tnx = pd.read_csv(DATA / "TNX.csv", index_col=0, parse_dates=True)["Close"].reindex(C.index).ffill()
qqq_up, smh_up = bool(I["qqq50"][d]), bool(I["smh50"][d])
out = [f"# Stock board — close of {d.date()}\n", "## Market (computed)\n", "| Index | Close | 1d | 5d | 21d | vs 50-day | vs 200-day |", "|---|---|---|---|---|---|---|"]
for t in ["SPY", "QQQ", "SMH", "IWM"]:
    s = P["Close"][t]
    out.append(f"| {t} | {s[d]:.1f} | {pct(s[d]/s.iloc[i-1]-1)} | {pct(s[d]/s.iloc[i-5]-1)} | {pct(s[d]/s.iloc[i-21]-1)} | {pct(s[d]/s.rolling(50).mean()[d]-1)} | {pct(s[d]/s.rolling(200).mean()[d]-1)} |")
out.append(f"\nVIX **{vix[d]:.1f}** (a week ago {vix.iloc[i-5]:.1f}) · 10-yr **{tnx[d]:.2f}%** ({tnx[d]-tnx.iloc[i-5]:+.2f} on the week)")
out.append(f"\n**Regime:** QQQ {'above' if qqq_up else 'BELOW'} its 50-day, SMH {'above' if smh_up else 'BELOW'} its 50-day. "
           + ("" if qqq_up else "**Caution:** momentum historically fails after index declines (the rules keep running; the backtest kept running too, and it was the memory names that carried it). ")
           + ("" if vix[d] < 25 else "VIX ≥ 25: dips on this list bounced hardest in this zone, and missed hardest.") + "\n")
# list
out += ["## The list (daily data; fundamentals snapshot dated in the file)\n",
        "| Name | Close | 1d | 5d | 5d vs sector | 21d | 63d (rank) | Off 21d hi | Off 52w hi | RSI2 | RSI14 | z20 (ATR) | vs 50d | vs 200d | ATR% | Vol ratio | Short % | Analyst tgt (upside, n) | Earnings |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
rows = {}
for t in WATCH:
    s = C[t]
    if np.isnan(s[d]): continue
    f = F.get(t, {}); nxt = [e for e in EARN.get(t, []) if e >= str(d.date())][:1]
    days_to = (len(pd.bdate_range(d, pd.Timestamp(nxt[0]))) - 1) if nxt else None
    tgt = f.get("targetMeanPrice"); n = f.get("numberOfAnalystOpinions")
    r = dict(close=s[d], d1=I["ret1"].at[d, t], d5=I["ret5"].at[d, t], res=I["resid5"].at[d, t], d21=I["ret21"].at[d, t], d63=I["ret63"].at[d, t], rk63=I["rank63"].at[d, t], rs63=I["rs63"].at[d, t],
             off21=I["depth21"].at[d, t], off52=I["off252"].at[d, t], rsi2=I["rsi2"].at[d, t], rsi14=I["rsi14"].at[d, t], z=I["z20"].at[d, t],
             v50=s[d] / I["sma50"].at[d, t] - 1, v200=s[d] / I["sma200"].at[d, t] - 1, atrp=I["atrp"].at[d, t], atr=I["atr"].at[d, t], vr=I["volratio"].at[d, t],
             short=f.get("shortPercentOfFloat"), tgt=tgt, n=n, earn=nxt[0] if nxt else None, days_to=days_to, vol21=I["vol21"].at[d, t],
             thresh=max(0.15, 1.5 * I["vol21"].at[d, t]), worst5=I["worst5"].at[d, t], eskip=bool(emask.at[d, t]), gskip=bool(I["worst5"].at[d, t] <= -0.20))
    rows[t] = r
    out.append(f"| **{t}** | {s[d]:.2f} | {pct(r['d1'])} | {pct(r['d5'])} | {pct(r['res'])} | {pct(r['d21'])} | {pct(r['d63'])} (#{int(r['rk63']) if not np.isnan(r['rk63']) else '—'}) | {pct(-r['off21'])} | {pct(-r['off52'])} | {num(r['rsi2'],0)} | {num(r['rsi14'],0)} | {num(r['z'])} | {pct(r['v50'])} | {pct(r['v200'])} | {pct(r['atrp'])} | {num(r['vr'])}× | {pct(r['short'],0) if r['short'] else '—'} | {f'{tgt:.0f} ({pct(tgt/s[d]-1,0)}, {n})' if tgt else '—'} | {r['earn'] or '—'}{f' ({days_to}d)' if days_to is not None else ''} |")
# engine L
out += ["\n## Engine L — leaders (ride the wave)\n",
        f"A name is a **leader** when it is in the top {L_RULE['top']} of the list by 63-day return, has beaten SMH over 63 days, and is above its 50-day average. A leader is a **buy signal** on a night its RSI(2) is under {L_RULE['rsi']}: a short pullback inside an uptrend. Exit: {int(L_EXIT['trail']*100)}% off the highest close since entry, or −{int(L_EXIT['S']*100)}% from entry, or {L_EXIT['N']} trading days. Skips: earnings within 3 back / 5 ahead, any ≥20% one-day drop in the last 5.\n",
        "| Rank | Name | 63d | vs SMH 63d | Above 50d | RSI2 | z20 | Off 21d hi | Signal | Skip |", "|---|---|---|---|---|---|---|---|---|---|"]
leaders = sorted([t for t in rows if not np.isnan(rows[t]["rk63"])], key=lambda t: rows[t]["rk63"])[:8]
for t in leaders:
    r = rows[t]; is_leader = r["rk63"] <= L_RULE["top"] and r["rs63"] > 0 and r["v50"] > 0
    sig = bool(sigL.at[d, t])
    out.append(f"| {int(r['rk63'])} | **{t}** | {pct(r['d63'],0)} | {pct(r['rs63'],0)} | {'yes' if r['v50'] > 0 else 'no'} | {num(r['rsi2'],0)} | {num(r['z'])} | {pct(-r['off21'],0)} | {'**BUY SIGNAL**' if sig else ('leader, no pullback' if is_leader else ('not a leader: ' + ('below 50d' if r['v50'] <= 0 else 'lagging SMH' if r['rs63'] <= 0 else 'rank')))} | {('earnings ' + str(r['earn'])) if r['eskip'] else ('gap' if r['gskip'] else '—')} |")
# engine D
out += ["\n## Engine D — deep dips (buy the fear, sell the bounce)\n",
        "Signal: close at least max(15%, 1.5× its own monthly volatility) below the prior 21-day high. **Idio** = the 5-day move is ≥10 pts worse than its beta to SMH explains while SMH itself is not down 5%: the drop is the name's own, which is the kind that bounces. Exit: sell when 8% off the highest close since entry, or −10% from entry, or 20 trading days. Ranked by drop ÷ monthly vol. Flags (information, not gates): **Idio**, volume ratio, and whether the name is still above its 200-day (dips from above the 200-day bounced worst in the data).\n",
        "| Name | Signal | Idio | Above 200d | Threshold | Drop | Drop ÷ vol | 5d own vs sector-explained | Vol ratio | Skip |", "|---|---|---|---|---|---|---|---|---|---|"]
cands = []
for t, r in rows.items():
    a, c_ = bool(sigD.at[d, t]), bool(sigR.at[d, t]); near = (not a) and r["off21"] >= r["thresh"] - 0.05
    if a or near: cands.append((t, a, c_, near, rankD.at[d, t]))
cands.sort(key=lambda x: -x[4])
for t, a, c_, near, rk in cands:
    r = rows[t]
    out.append(f"| **{t}** | {'**SIGNAL**' if a else 'close'} | {'yes' if c_ else '—'} | {'yes (flag)' if r['v200'] > 0 else 'no'} | {pct(-r['thresh'],0)} | {pct(-r['off21'],0)} | {num(rk)} | {pct(r['d5'],0)} vs {pct(r['d5']-r['res'],0)} | {num(r['vr'])}× | {('earnings ' + str(r['earn'])) if r['eskip'] else ('gap' if r['gskip'] else '—')} |")
if not cands: out.append("| — | no name meets or nears the dip rule tonight | | | | | | | | |")
# levels
out += ["\n## Levels, if bought near tonight's close\n", "| Name | Engine | Entry ref | Stop (−10%) | Trail / target | Time | 2 ATR below (morning line in the sand) |", "|---|---|---|---|---|---|---|"]
for t in leaders:
    r = rows[t]
    if bool(sigL.at[d, t]) and not (r["eskip"] or r["gskip"]):
        out.append(f"| {t} | L | {r['close']:.2f} | {r['close']*0.9:.2f} | sell when 10% off the highest close after entry | 40 days | {r['close']-2*r['atr']:.2f} |")
for t, a, c_, near, rk in cands:
    r = rows[t]
    if a and not (r["eskip"] or r["gskip"]):
        out.append(f"| {t} | D | {r['close']:.2f} | {r['close']*0.9:.2f} | sell when 8% off the highest close after entry | 20 days | {r['close']-2*r['atr']:.2f} |")
# research prompts
out.append("\n## What to find out before acting (Muse researches these; he reads)\n")
asked = False
for t in leaders:
    r = rows[t]
    if bool(sigL.at[d, t]) and not (r["eskip"] or r["gskip"]):
        asked = True; out.append(f"- **{t} (L):** what pulled it back {pct(-r['off21'],0)} from its 21-day high in the last 5 days ({pct(r['d5'],0)}, sector-explained {pct(r['d5']-r['res'],0)}); any downgrade, offering, lock-up, or guidance change; whether the sector story (memory pricing, AI capex) changed this week. Volume ratio {num(r['vr'])}×.")
for t, a, c_, near, rk in cands:
    r = rows[t]
    if a and not (r["eskip"] or r["gskip"]):
        asked = True; out.append(f"- **{t} (D):** the stated reason for the drop (last 5 days); offering / guidance cut / downgrade / investigation / lock-up expiry; did peers fall the same way (if yes, it's sector, and sector dips bounce less). Volume ratio {num(r['vr'])}× ({'heavy: capitulation-type selling, which historically bounced harder on this list' if r['vr'] and r['vr'] > 1.5 else 'normal'}).")
if not asked: out.append("- No name meets a rule tonight without a skip. Nothing to research; the board is for context.")
print("\n".join(out))
