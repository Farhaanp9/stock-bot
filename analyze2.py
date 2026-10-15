import pandas as pd, sys
pd.set_option("display.width", 250)
w = pd.read_csv("data/sweep2_watch.csv"); c = pd.read_csv("data/sweep2_control.csv")
def piv(df, keys):
    p = df.pivot_table(index=keys, columns="window", values="ret"); dd = df[df.window == "full"].set_index(keys)["max_dd"]
    p["dd_full"] = dd; return p
print("=== DIP-family sweep (watch): median return by signal family across regimes/exits")
pw = piv(w, ["sig", "regime", "exit"])
print(pw.groupby("sig").median().round(2).to_string())
print("\n=== by regime filter (median over sig/exit)"); print(pw.groupby("regime").median().round(2).to_string())
print("\n=== by exit (median over sig/regime)"); print(pw.groupby("exit").median().round(2).to_string())
print("\n=== share of combos positive, by window"); print((pw[["before", "golden", "bad", "recovery", "full"]] > 0).mean().round(2).to_string())
print("\n=== dip1.5 family only: regime x exit, golden / bad / recovery / full / dd")
sub = pw.loc["dip1.5"]; print(sub[["before", "golden", "bad", "recovery", "full", "dd_full"]].round(2).to_string())
print("\n=== CONTROL basket: median by sig"); pc = piv(c, ["sig", "regime", "exit"]); print(pc.groupby("sig").median().round(2).to_string())
print("\n=== LEADER sweep (watch): 240 combos")
l = pd.read_csv("data/lsweep_watch.csv"); pl = piv(l, ["top", "rsi", "trail", "S", "N"])
print("share positive by window:"); print((pl[["before", "golden", "bad", "recovery", "full"]] > 0).mean().round(2).to_string())
print("median:"); print(pl[["before", "golden", "bad", "recovery", "full", "dd_full"]].median().round(2).to_string())
for k in ["top", "rsi", "trail", "S", "N"]:
    print(f"\n-- by {k}"); print(pl.groupby(level=k)[["before", "golden", "bad", "recovery", "full", "dd_full"]].median().round(2).to_string())
print("\n-- top-5 rsi10 rows"); print(pl.loc[(5, 10)][["before", "golden", "bad", "recovery", "full", "dd_full"]].round(2).to_string())
print("\n=== LEADER sweep (control basket)")
lc = pd.read_csv("data/lsweep_control.csv"); plc = piv(lc, ["top", "rsi", "trail", "S", "N"])
print("share positive:"); print((plc[["before", "golden", "bad", "recovery", "full"]] > 0).mean().round(2).to_string())
print("median:"); print(plc[["before", "golden", "bad", "recovery", "full", "dd_full"]].median().round(2).to_string())
