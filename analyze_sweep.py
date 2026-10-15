"""Rank sweep results: robust = good across windows, low drawdown, not a hindsight pick."""
import pandas as pd, sys
which = sys.argv[1] if len(sys.argv) > 1 else "watch"
mode = sys.argv[2] if len(sys.argv) > 2 else "sweep"
df = pd.read_csv(f"data/{mode}_{which}.csv")
if "k" not in df: df["k"] = "off"
keys0 = ["D","k","T","S","N","trend","gap","earn"]; df[keys0] = df[keys0].fillna("off")
keys = keys0
w = df.pivot_table(index=keys, columns="window", values=["ret","max_dd","trades","win_rate"], aggfunc="first")
w.columns = [f"{a}_{b}" for a,b in w.columns]
w = w.reset_index()
# score: return per unit of drawdown on the full window, penalize few trades and any window that lost money
w["calmar"] = w["ret_full"] / (-w["max_dd_full"]).clip(lower=0.05)
w["min_win_ret"] = w[["ret_before","ret_golden","ret_after"]].min(axis=1)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
cols = keys + ["trades_full","ret_full","max_dd_full","win_rate_full","ret_before","ret_golden","ret_after","min_win_ret","calmar"]
print("=== top by calmar (full) ===");   print(w.sort_values("calmar", ascending=False)[cols].head(15).round(3).to_string(index=False))
print("\n=== top by worst-window return ==="); print(w.sort_values("min_win_ret", ascending=False)[cols].head(10).round(3).to_string(index=False))
print("\n=== effect of each knob (median full ret / median full max_dd / median trades) ===")
for k in keys:
    g = w.groupby(k).agg(ret=("ret_full","median"), dd=("max_dd_full","median"), n=("trades_full","median"), golden=("ret_golden","median"), after=("ret_after","median")).round(3)
    print(k); print(g.to_string()); print()
print("=== share of combos losing money, by window ===")
for win in ["full","before","golden","after"]:
    print(win, round(float((w[f"ret_{win}"] < 0).mean()), 2))
