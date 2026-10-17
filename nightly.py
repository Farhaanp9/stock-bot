"""The nightly job. Fetch daily prices → apply the round-3 rules → write three markdown files for Muse.
Every number here comes from a data feed; no model writes anything in this file. Nothing here can reach a brokerage.

Usage: python nightly.py --out stocks [--cache cache] [--positions stocks/positions.md] [--screen] [--date YYYY-MM-DD]
Writes: <out>/brief.md (phone-length, Muse pushes this), <out>/latest.md (the full board), <out>/YYYY-MM-DD.md (copy of the board).
Rules: projects/stock-bot/PLAN.md round 3 (2026-10-17). Engine code: engine2.py. Names: universe.py.
"""
import argparse, json, re, sys, time, datetime as dt, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd, yfinance as yf
import engine2 as E
from universe import WATCH, NAMES, BENCH, POOL, CONTROL, LOCKUPS, MACRO, NEWS_FLAGS, ALIASES, NOISE, NOISE_SOURCES

RULES = dict(top=6, rsi=15, D=0.15, k=1.5, gap=0.20, earn=(3, 5), void=0.03, slots_above=3, slots_below=1, lockup_days=10,
             exits={"L": dict(trail=0.10, S=0.10, N=40), "D": dict(trail=0.08, S=0.10, N=20)})
PT = ZoneInfo("America/Los_Angeles")
RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def pct(x, nd=1):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:+.{nd}f}%"


def num(x, nd=1):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------- data ----------
def download(tickers, start, tries=3):
    for k in range(tries):
        try:
            raw = yf.download(tickers, start=start, auto_adjust=True, progress=False, group_by="ticker", threads=True)
            if len(raw):
                return raw
        except Exception as ex:
            log("download failed", k, str(ex)[:120])
        time.sleep(10 * (k + 1))
    raise SystemExit("price download failed three times")


def panel(raw, tickers, cal):
    P = {k: {} for k in ["Open", "High", "Low", "Close", "Volume"]}
    for t in tickers:
        key = t.replace("^", "")
        try:
            df = raw[t].dropna(how="all").reindex(cal)
        except Exception:
            df = pd.DataFrame(index=cal)
        for k in P:
            P[k][key] = df[k] if k in df else pd.Series(np.nan, index=cal)
    return {k: pd.DataFrame(v).sort_index() for k, v in P.items()}


def cached(cache, name, max_age_days, fetch):
    """Return (data, asof). Refresh when older than max_age_days; fall back to the cache if the fetch fails."""
    f = cache / f"{name}.json"
    old = json.load(open(f)) if f.exists() else None
    today = dt.date.today().isoformat()
    if old and (dt.date.today() - dt.date.fromisoformat(old["asof"])).days < max_age_days:
        return old["data"], old["asof"]
    try:
        data = fetch()
        if data:
            json.dump({"asof": today, "data": data}, open(f, "w"), indent=0, default=str)
            return data, today
    except Exception as ex:
        log(name, "fetch failed:", str(ex)[:120])
    if old:
        return old["data"], old["asof"]
    return {}, None


def fetch_earnings():
    out = {}
    for t in WATCH:
        try:
            e = yf.Ticker(t).get_earnings_dates(limit=12)
            out[t] = sorted({str(d.date()) for d in e.index}) if e is not None and len(e) else []
        except Exception as ex:
            log("earnings", t, str(ex)[:80]); out[t] = None
        time.sleep(0.3)
    if sum(v is None for v in out.values()) > len(WATCH) // 2:
        raise RuntimeError("most earnings calls failed")
    return {t: v for t, v in out.items() if v is not None}


def fetch_fundamentals():
    keys = ["marketCap", "shortPercentOfFloat", "targetMeanPrice", "recommendationMean", "numberOfAnalystOpinions", "longName", "industry"]
    out = {}
    for t in WATCH:
        try:
            i = yf.Ticker(t).info; out[t] = {k: i.get(k) for k in keys}
        except Exception as ex:
            log("info", t, str(ex)[:80])
        time.sleep(0.4)
    if len(out) < len(WATCH) // 2:
        raise RuntimeError("most info calls failed")
    return out


def news(t, days=5):
    """Headlines from Google News RSS for the last `days` days: list of (date, source, title, link). Empty list on any failure."""
    q = urllib.parse.quote(f'"{t}" OR "{NAMES.get(t, t)}" stock when:{days}d')
    try:
        req = urllib.request.Request(RSS.format(q=q), headers={"User-Agent": "Mozilla/5.0"})
        xml = urllib.request.urlopen(req, timeout=20).read()
        items, seen = [], set()
        for it in ET.fromstring(xml).findall(".//item"):
            pub = it.findtext("pubDate"); src = it.find("source")
            try:
                d = dt.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").date()
            except Exception:
                d = None
            title = (it.findtext("title") or "").rsplit(" - ", 1)[0].strip()
            source = src.text if src is not None else "?"
            if not relevant(t, title) or source in NOISE_SOURCES or any(re.search(n, title) for n in NOISE):
                continue
            key = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
            if key in seen:
                continue
            seen.add(key); items.append((d, source, title, it.findtext("link") or ""))
        items.sort(key=lambda x: x[0] or dt.date.min, reverse=True)
        return items
    except Exception as ex:
        log("news", t, str(ex)[:80]); return []


def relevant(t, title):
    """The headline names the ticker (exact, upper-case) or the company."""
    if re.search(rf"\b{re.escape(t)}\b", title):
        return True
    return any(re.search(a, title, re.I) if a.startswith("\\b") or a.startswith("(") else a.lower() in title.lower() for a in ALIASES.get(t, [NAMES.get(t, t)]))


def news_flag(items, asof, days=3):
    hits = []
    for d, src, title, link in items:
        if d is None or (asof - d).days > days:
            continue
        for pat in NEWS_FLAGS:
            if re.search(pat, title, re.I):
                hits.append((d, src, title)); break
    return hits


def read_positions(path):
    """Lines like `- SNDK | own | entry 1403.50 | since 2026-09-02 | note`. Engine own/L/D. A line containing `closed` is skipped."""
    out = []
    if not path or not Path(path).exists():
        return out
    for line in Path(path).read_text().splitlines():
        if not line.startswith("- ") or "closed" in line.lower():
            continue
        parts = [p.strip() for p in line[2:].split("|")]
        t = parts[0].split()[0].upper() if parts and parts[0] else None
        if not t or not re.fullmatch(r"[A-Z.\-]{1,6}", t):
            continue
        eng = next((p.upper() if p.upper() in ("L", "D") else "own" for p in parts[1:2]), "own")
        m = re.search(r"entry\s*\$?([0-9]+(?:\.[0-9]+)?)", line, re.I); entry = float(m.group(1)) if m else None
        m = re.search(r"since\s*(\d{4}-\d{2}-\d{2})", line, re.I); since = m.group(1) if m else None
        out.append(dict(name=t, eng=eng, entry=entry, since=since, raw=line[2:]))
    return out


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="stocks"); ap.add_argument("--cache", default="cache")
    ap.add_argument("--positions", default=None); ap.add_argument("--screen", action="store_true")
    ap.add_argument("--date", default=None, help="board for this close instead of the last one")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); cache = Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(PT)

    tickers = sorted(set(WATCH + BENCH + POOL + CONTROL))
    start = (now.date() - dt.timedelta(days=470)).isoformat()
    raw = download(tickers, start)
    cal = raw["SPY"].dropna(how="all").index
    P = panel(raw, tickers, cal)
    C_all = P["Close"]
    d = pd.Timestamp(a.date) if a.date else cal[-1]
    if d not in cal:
        raise SystemExit(f"{d.date()} is not a trading day in the feed")
    i = cal.get_loc(d)
    # expected session: today if a weekday after 1:30 PM PT, else the previous weekday
    exp = now.date() if (now.weekday() < 5 and now.hour * 60 + now.minute >= 13 * 60 + 30) else now.date() - dt.timedelta(days=1)
    while exp.weekday() >= 5:
        exp -= dt.timedelta(days=1)
    stale = (not a.date) and d.date() < exp

    earn, earn_asof = cached(cache, "earnings", 1, fetch_earnings)
    fund, fund_asof = cached(cache, "fundamentals", 7, fetch_fundamentals)
    E.EARN = earn  # the engine reads this module global

    I = E.indicators(P, WATCH); C = I["C"]
    L_RULE = dict(sig=["leader"], top=RULES["top"], rsi=RULES["rsi"], gap=RULES["gap"], earn=RULES["earn"])
    D_RULE = dict(sig=["dip"], D=RULES["D"], k=RULES["k"], gap=RULES["gap"], earn=RULES["earn"])
    sigL, _ = E.signals(I, WATCH, L_RULE); sigD, rankD = E.signals(I, WATCH, D_RULE)
    emask = E.earnings_mask(cal, WATCH, *RULES["earn"])
    vix = C_all["VIX"].ffill(); tnx = C_all["TNX"].ffill()
    smh = C_all["SMH"]; qqq = C_all["QQQ"]
    smh200 = float(smh.rolling(200).mean()[d]); above200 = bool(smh[d] > smh200)
    slots = RULES["slots_above"] if above200 else RULES["slots_below"]

    # sanity
    sanity = []
    for t in WATCH:
        s = C[t]
        if np.isnan(s[d]):
            sanity.append(f"{t}: no close for {d.date()}"); continue
        r1 = s[d] / s.iloc[i - 1] - 1
        if abs(r1) > 0.40: sanity.append(f"{t}: {pct(r1)} in a day; check for a split or a bad print before acting")
        if not (P["Low"][t][d] - 1e-9 <= s[d] <= P["High"][t][d] + 1e-9): sanity.append(f"{t}: close outside the day's range")
    bench_chk = ", ".join(f"{t} {C_all[t][d]:.2f}" for t in ["SPY", "QQQ", "SMH"])

    # per-name rows
    rows = {}
    for t in WATCH:
        s = C[t]
        if np.isnan(s[d]): continue
        f = fund.get(t, {}) or {}; nxt = [e for e in (earn.get(t) or []) if e >= str(d.date())][:1]
        days_to = (len(pd.bdate_range(d, pd.Timestamp(nxt[0]))) - 1) if nxt else None
        lock = LOCKUPS.get(t); lock_days = (len(pd.bdate_range(d, pd.Timestamp(lock))) - 1) if lock and lock >= str(d.date()) else None
        vol21 = float(I["vol21"].at[d, t]); thresh = max(RULES["D"], RULES["k"] * vol21) if not np.isnan(vol21) else RULES["D"]
        r = dict(close=float(s[d]), d1=I["ret1"].at[d, t], d5=I["ret5"].at[d, t], res=I["resid5"].at[d, t], d21=I["ret21"].at[d, t], d63=I["ret63"].at[d, t],
                 rk63=I["rank63"].at[d, t], rs63=I["rs63"].at[d, t], off21=I["depth21"].at[d, t], hi21=I["hi21"].at[d, t], off52=I["off252"].at[d, t],
                 rsi2=I["rsi2"].at[d, t], rsi14=I["rsi14"].at[d, t], z=I["z20"].at[d, t], v50=s[d] / I["sma50"].at[d, t] - 1, v200=s[d] / I["sma200"].at[d, t] - 1,
                 atrp=I["atrp"].at[d, t], atr=float(I["atr"].at[d, t]), vr=I["volratio"].at[d, t], short=f.get("shortPercentOfFloat"), tgt=f.get("targetMeanPrice"),
                 n=f.get("numberOfAnalystOpinions"), earn=nxt[0] if nxt else None, days_to=days_to, thresh=thresh, worst5=I["worst5"].at[d, t],
                 eskip=bool(emask.at[d, t]), gskip=bool(I["worst5"].at[d, t] <= -RULES["gap"]), lock=lock, lock_days=lock_days,
                 lskip=bool(lock_days is not None and lock_days <= RULES["lockup_days"]))
        r["sigL"] = bool(sigL.at[d, t]); r["sigD"] = bool(sigD.at[d, t]); r["rankD"] = float(rankD.at[d, t])
        r["near"] = (not r["sigD"]) and (not np.isnan(r["off21"])) and r["off21"] >= thresh - 0.05
        r["leader"] = (not np.isnan(r["rk63"])) and r["rk63"] <= RULES["top"] and r["rs63"] > 0 and r["v50"] > 0
        rows[t] = r

    # news: for signal names, near names, his positions, and a flag sweep over the whole list
    heads, flags = {}, {}
    for t in WATCH:
        items = news(t, 5)
        heads[t] = items[:3]
        fl = news_flag(items, d.date(), 3)
        if fl: flags[t] = fl
        time.sleep(0.3)
    for t in rows:
        rows[t]["nskip"] = t in flags
        rows[t]["skip"] = rows[t]["eskip"] or rows[t]["gskip"] or rows[t]["nskip"] or rows[t]["lskip"]

    def skipwhy(r):
        w = []
        if r["eskip"]: w.append(f"earnings {r['earn']}" if r["earn"] else "earnings (recent)")
        if r["gskip"]: w.append("20% gap day")
        if r["nskip"]: w.append("news flag")
        if r["lskip"]: w.append(f"lock-up {r['lock']}")
        return ", ".join(w) or "—"

    positions = read_positions(a.positions)
    pos_names = {p["name"] for p in positions}
    sigs = [t for t, r in rows.items() if (r["sigL"] or r["sigD"]) and not r["skip"]]
    sigs.sort(key=lambda t: -(rows[t]["rankD"] if rows[t]["sigD"] else 0) - (rows[t]["d63"] if rows[t]["sigL"] and not rows[t]["sigD"] else 0))
    skipped_sigs = [t for t, r in rows.items() if (r["sigL"] or r["sigD"]) and r["skip"]]
    near_d = sorted([t for t, r in rows.items() if r["near"]], key=lambda t: -rows[t]["rankD"])
    leaders8 = sorted([t for t in rows if not np.isnan(rows[t]["rk63"])], key=lambda t: rows[t]["rk63"])[:8]
    leaders_quiet = [t for t in leaders8 if rows[t]["leader"] and not rows[t]["sigL"]]
    macro = [(dd, w) for dd, w in MACRO if dd >= str(d.date())][:2]
    upcoming = sorted([(r["earn"], t) for t, r in rows.items() if r["days_to"] is not None and r["days_to"] <= 10])

    # monthly screen
    first_of_month = i > 0 and cal[i - 1].month != d.month
    screen = None
    if a.screen or first_of_month:
        U = sorted(set(POOL + WATCH + CONTROL)); Cu = C_all[U]; Vu = P["Volume"][U]
        adv = (Cu * Vu).rolling(60).mean().loc[d]; hist = Cu.notna().cumsum().loc[d]; r126 = (Cu / Cu.shift(126) - 1).loc[d]
        ok = (Cu.loc[d] >= 5) & (adv >= 50e6) & (hist >= 131) & r126.notna()
        top = r126[ok].sort_values(ascending=False)
        screen = dict(picks=top.index[:18].tolist(), ret=top.iloc[:18].to_dict(), n_ok=int(ok.sum()),
                      his_rank={t: (int(top.index.get_loc(t)) + 1 if t in top.index else None) for t in WATCH})

    # ---------- levels helper ----------
    def levels(t, eng):
        r = rows[t]; x = RULES["exits"][eng]; c = r["close"]
        return dict(stop=c * (1 - x["S"]), trail=x["trail"], N=x["N"], line=c - 2 * r["atr"], void=c * (1 + RULES["void"]))

    dname = d.strftime("%a %Y-%m-%d")
    data_line = (f"Data: Yahoo Finance daily bars (single source; a second feed is an open item), last session {d.date()}" +
                 (f" — **today's close ({exp}) is not in the feed yet: holiday or feed delay; this board is for {d.date()}**" if stale else "") +
                 f". Earnings dates as of {earn_asof or 'unknown'}; fundamentals as of {fund_asof or 'unknown'}. Closes: {bench_chk}. " +
                 ("Sanity: OK." if not sanity else "**Sanity flags:** " + "; ".join(sanity)))

    # ---------- brief.md (phone-length) ----------
    B = [f"# Stock brief — close of {dname}", "", data_line, "",
         f"**Regime:** SMH {smh[d]:.1f}, {pct(smh[d]/smh200-1)} vs its 200-day ({smh200:.0f}) → **{slots} slot{'s' if slots != 1 else ''}** for tomorrow's entries"
         + (" (SMH is below its 200-day: one slot, the throttle is on)" if not above200 else "")
         + f". SMH {pct(smh[d]/smh.rolling(50).mean()[d]-1)} vs 50-day, QQQ {pct(qqq[d]/qqq.rolling(50).mean()[d]-1)}. VIX **{vix[d]:.1f}** (week ago {vix.iloc[i-5]:.1f}"
         + ("; over 30: dips bounced least in this zone" if vix[d] > 30 else "") + f"). 10-yr **{tnx[d]:.2f}%**.",
         "SPY " + pct(C_all["SPY"][d]/C_all["SPY"].iloc[i-1]-1) + " / 5d " + pct(C_all["SPY"][d]/C_all["SPY"].iloc[i-5]-1)
         + " · QQQ " + pct(qqq[d]/qqq.iloc[i-1]-1) + " / " + pct(qqq[d]/qqq.iloc[i-5]-1)
         + " · SMH " + pct(smh[d]/smh.iloc[i-1]-1) + " / " + pct(smh[d]/smh.iloc[i-5]-1)
         + " · IWM " + pct(C_all["IWM"][d]/C_all["IWM"].iloc[i-1]-1) + " / " + pct(C_all["IWM"][d]/C_all["IWM"].iloc[i-5]-1)
         + (". Next macro: " + " · ".join(f"{w} {dd}" for dd, w in macro) if macro else ""), ""]
    fresh = [t for t in sigs if t not in pos_names]
    B.append(f"## Signals tonight: {len(sigs)}" + (f" — ranked by the rule's score; {slots} slot{'s' if slots != 1 else ''} by the regime rule, so the top {min(slots, len(fresh))} fill" + (f" ({len(sigs) - len(fresh)} already held: the rules never add to a position)" if len(sigs) > len(fresh) else "") + "; open positions keep their own exits" if sigs else ""))
    if not sigs:
        B.append("- No name meets a rule tonight without a skip. Nothing to buy by the rules; the rest of this is context.")
    for t in sigs:
        r = rows[t]
        held = " **Already held: not a new slot; the rules never add. Its exit levels are under His positions.**" if t in pos_names else ""
        if r["sigD"]:
            lv = levels(t, "D")
            B.append(f"- **{t} — D, deep dip.**{held} Close {r['close']:.2f}, {pct(-r['off21'],0)} off its 21-day high ({r['hi21']:.2f}; threshold {pct(-r['thresh'],0)}), {num(r['rankD'])}× its monthly vol. "
                     f"Above 200-day: **{'yes (the flag that bounced best)' if r['v200'] > 0 else 'no (below: bounced half as much)'}**. 5d {pct(r['d5'],0)} vs sector-explained {pct(r['d5']-r['res'],0)}; volume {num(r['vr'])}×. "
                     f"Levels: hard stop **{lv['stop']:.2f}** · trail: sell when 8% off the highest close after entry · clock 20 sessions · line in the sand {lv['line']:.2f} · **void if it opens above {lv['void']:.2f}**.")
        elif r["sigL"]:
            lv = levels(t, "L")
            B.append(f"- **{t} — L, leader pullback.**{held} Rank {int(r['rk63'])} by 63-day return ({pct(r['d63'],0)}, {pct(r['rs63'],0)} vs SMH), above its 50-day, RSI(2) {num(r['rsi2'],0)}, {pct(-r['off21'],0)} off its 21-day high. "
                     f"Levels: hard stop **{lv['stop']:.2f}** · trail: sell when 10% off the highest close after entry · clock 40 sessions · line in the sand {lv['line']:.2f} · **void if it opens above {lv['void']:.2f}**.")
    if skipped_sigs:
        B.append("- Fired but **skipped**: " + "; ".join(f"{t} ({'D' if rows[t]['sigD'] else 'L'}: {skipwhy(rows[t])})" for t in skipped_sigs) + ".")
    B.append("")
    close_lines = []
    for t in near_d:
        r = rows[t]; close_lines.append(f"{t} {pct(-r['off21'],0)} vs {pct(-r['thresh'],0)} needed" + (" (skip anyway: " + skipwhy(r) + ")" if r["skip"] else ""))
    B.append("## Close, not firing")
    B.append("- Dips near the line: " + ("; ".join(close_lines) if close_lines else "none") + ".")
    B.append("- Leaders without a pullback (top 6, above 50-day, beating SMH): " + (", ".join(f"{t} (RSI2 {num(rows[t]['rsi2'],0)})" for t in leaders_quiet) if leaders_quiet else "none") + ".")
    not_leaders = [t for t in leaders8 if int(rows[t]["rk63"]) <= RULES["top"] and not rows[t]["leader"]]
    if not_leaders:
        B.append("- In the top 6 but not leaders: " + ", ".join(f"{t} ({'below 50-day' if rows[t]['v50'] <= 0 else 'lagging SMH'})" for t in not_leaders) + ".")
    B.append("")
    B.append("## His positions")
    if not positions:
        B.append("- None on file. Tell Muse “bought X at Y” or “sold X at Y” and it lands in stocks/positions.md.")
    for p in positions:
        t = p["name"]
        if t not in rows and t in C_all:
            B.append(f"- **{t}** ({p['eng']}): {C_all[t][d]:.2f}, not on the list, no rule levels."); continue
        if t not in rows: B.append(f"- **{t}**: no data."); continue
        r = rows[t]; c = r["close"]
        line = f"- **{t}** ({p['eng']}{', entry ' + f'{p['entry']:.2f}' if p['entry'] else ', entry not given'}{', since ' + p['since'] if p['since'] else ''}). Close {c:.2f} ({pct(r['d1'])} today, {pct(r['d5'])} on 5 days), {pct(-r['off21'],0)} off its 21-day high {r['hi21']:.2f}, {'above' if r['v50'] > 0 else 'below'} 50-day, {'above' if r['v200'] > 0 else 'below'} 200-day, RSI(2) {num(r['rsi2'],0)}."
        if p["entry"]:
            line += f" From entry {pct(c/p['entry']-1)}."
            since_c = C[t].loc[p["since"]:d] if p["since"] else C[t].loc[:d].iloc[-1:]
            hi = float(since_c.max()) if len(since_c) else c
            held = len(since_c) - 1 if p["since"] else None
            for eng in (["L", "D"] if p["eng"] == "own" else [p["eng"]]):
                x = RULES["exits"][eng]
                line += f" Under {eng} exits: hard stop {p['entry']*(1-x['S']):.2f}, trail exit {hi*(1-x['trail']):.2f} (highest close since entry {hi:.2f})" + (f", clock {held}/{x['N']} sessions" if held is not None else "") + "."
        else:
            line += f" Dip rule for it: threshold {pct(-r['thresh'],0)}, {'FIRING' if r['sigD'] else 'not firing'}. If it were a fresh D trade from here: stop {c*0.9:.2f}, line {c-2*r['atr']:.2f}."
        if r["earn"]: line += f" Earnings {r['earn']} ({r['days_to']} sessions){'; inside the skip window' if r['eskip'] else ''}."
        if t in flags: line += " **News flag** (below)."
        B.append(line)
    B.append("")
    if upcoming or any(rows[t]["lskip"] for t in rows):
        B.append("## Earnings within 10 sessions, and lock-ups")
        B.append("- " + " · ".join(f"{t} {e}" for e, t in upcoming) + (" · lock-ups: " + ", ".join(f"{t} {rows[t]['lock']}" for t in rows if rows[t]["lskip"]) if any(rows[t]["lskip"] for t in rows) else "") + ". A name is skipped from 5 sessions before earnings to 3 after.")
        B.append("")
    if flags:
        B.append("## News flags (SKIP by rule; he can disagree in the morning, the log records it)")
        for t, fl in flags.items():
            for dd, src, title in fl[:2]:
                B.append(f"- **{t}** {dd} · {src}: {title}")
        B.append("")
    research = [t for t in sigs] + [t for t in near_d if t not in sigs][:2] + [t for t in pos_names if t in rows and t not in sigs]
    B.append("## For Muse to research (sources, not causes)")
    if not research:
        B.append("- Nothing fired. One line on the sector day (SMH, memory, AI capex) is enough.")
    for t in research:
        r = rows[t]; why = "signal" if t in sigs else ("near the dip line" if t in near_d else "his position")
        hl = "; ".join(f"{src}: {title}" for dd, src, title, link in heads.get(t, [])[:3]) or "no headlines found"
        B.append(f"- **{t}** ({why}): what moved it in the last 5 days ({pct(r['d5'],0)}; sector-explained {pct(r['d5']-r['res'],0)}); any offering, downgrade, guidance change, lock-up. Recent: {hl}.")
    B.append("")
    if screen:
        B.append(f"## Monthly mechanical screen (top 18 of {screen['n_ok']} names by 6-month return; price ≥ $5, $50M/day). A check on his list, not a rule")
        B.append("- Screen: " + ", ".join(f"{t} {pct(screen['ret'][t],0)}" for t in screen["picks"]) + ".")
        both = [t for t in WATCH if t in screen["picks"]]; only_screen = [t for t in screen["picks"] if t not in WATCH]
        only_his = [f"{t} (#{screen['his_rank'][t]})" if screen["his_rank"][t] else f"{t} (not eligible)" for t in WATCH if t not in screen["picks"]]
        B.append(f"- On both: {', '.join(both) or 'none'}. On the screen, not his list: {', '.join(only_screen) or 'none'}. His list, not on the screen: {', '.join(only_his)}.")
        B.append("- When they disagree for a month or two, the sector call is the thing to re-examine: in his golden window the 6-month screen made +32%, a 12-month screen −8.5%, his list +34–48%.")
        B.append("")
    B.append("Rules in one line: entries next morning only, never before 7:00 AM PT, limit orders cancelled at noon, void on a 3% gap up, one name per slot, never add to a loser, margin off, every exit at the close that hits it. Full board: stocks/latest.md.")
    B.append("")
    B.append("Taps: **Placing orders tomorrow** · **Sitting out** · **Rule question for Claude**")

    # ---------- latest.md (full board) ----------
    O = [f"# Stock board — close of {dname}", "", data_line, "", "## Market", "", "| Index | Close | 1d | 5d | 21d | vs 50-day | vs 200-day |", "|---|---|---|---|---|---|---|"]
    for t in ["SPY", "QQQ", "SMH", "IWM"]:
        s = C_all[t]
        O.append(f"| {t} | {s[d]:.1f} | {pct(s[d]/s.iloc[i-1]-1)} | {pct(s[d]/s.iloc[i-5]-1)} | {pct(s[d]/s.iloc[i-21]-1)} | {pct(s[d]/s.rolling(50).mean()[d]-1)} | {pct(s[d]/s.rolling(200).mean()[d]-1)} |")
    O += ["", B[4], B[5], "", "## The list", "",
          "| Name | Close | 1d | 5d | 5d vs sector | 21d | 63d (rank) | Off 21d hi | Off 52w hi | RSI2 | RSI14 | z20 | vs 50d | vs 200d | ATR% | Vol | Short % | Analyst tgt (upside, n) | Earnings |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in WATCH:
        if t not in rows: O.append(f"| **{t}** | no data | | | | | | | | | | | | | | | | | |"); continue
        r = rows[t]; tgt = r["tgt"]
        O.append(f"| **{t}** | {r['close']:.2f} | {pct(r['d1'])} | {pct(r['d5'])} | {pct(r['res'])} | {pct(r['d21'])} | {pct(r['d63'])} (#{int(r['rk63']) if not np.isnan(r['rk63']) else '—'}) | {pct(-r['off21'])} | {pct(-r['off52'])} | {num(r['rsi2'],0)} | {num(r['rsi14'],0)} | {num(r['z'])} | {pct(r['v50'])} | {pct(r['v200'])} | {pct(r['atrp'])} | {num(r['vr'])}× | {pct(r['short'],0) if r['short'] else '—'} | {f'{tgt:.0f} ({pct(tgt/r['close']-1,0)}, {r['n']})' if tgt else '—'} | {r['earn'] or '—'}{f' ({r['days_to']}d)' if r['days_to'] is not None else ''} |")
    O += ["", "## Engine L — leaders (buy the pullback, ride the wave)", "",
          f"Leader: top {RULES['top']} by 63-day return, beating SMH over 63 days, above its 50-day. Signal: RSI(2) under {RULES['rsi']}. Exit: 10% off the highest close since entry, or −10% from entry, or 40 sessions.", "",
          "| Rank | Name | 63d | vs SMH | Above 50d | RSI2 | z20 | Off 21d hi | Status | Skip |", "|---|---|---|---|---|---|---|---|---|---|"]
    for t in leaders8:
        r = rows[t]
        st = "**BUY SIGNAL**" if r["sigL"] else ("leader, no pullback" if r["leader"] else ("not a leader: " + ("below 50-day" if r["v50"] <= 0 else "lagging SMH" if r["rs63"] <= 0 else "rank")))
        O.append(f"| {int(r['rk63'])} | **{t}** | {pct(r['d63'],0)} | {pct(r['rs63'],0)} | {'yes' if r['v50'] > 0 else 'no'} | {num(r['rsi2'],0)} | {num(r['z'])} | {pct(-r['off21'],0)} | {st} | {skipwhy(r)} |")
    O += ["", "## Engine D — deep dips (buy the panic, sell the bounce)", "",
          "Signal: close at least max(15%, 1.5× its own monthly volatility) below the prior 21-day high. Exit: 8% off the highest close since entry, or −10% from entry, or 20 sessions. Plus: still above its 200-day (+6.2%, 69% positive on 1,669 events vs +2.9%, 58% below). Caution: VIX over 30. Sector-relative move and volume are description, not flags.", "",
          "| Name | Signal | Above 200d | Threshold | Drop | Drop ÷ vol | 5d own vs sector-explained | Vol | Skip |", "|---|---|---|---|---|---|---|---|---|"]
    dcands = sorted([t for t, r in rows.items() if r["sigD"] or r["near"]], key=lambda t: -rows[t]["rankD"])
    for t in dcands:
        r = rows[t]
        O.append(f"| **{t}** | {'**SIGNAL**' if r['sigD'] else 'close'} | {'yes (plus)' if r['v200'] > 0 else 'no'} | {pct(-r['thresh'],0)} | {pct(-r['off21'],0)} | {num(r['rankD'])} | {pct(r['d5'],0)} vs {pct(r['d5']-r['res'],0)} | {num(r['vr'])}× | {skipwhy(r)} |")
    if not dcands: O.append("| — | no name meets or nears the dip rule tonight | | | | | | | |")
    O += ["", f"## Levels for tonight's signals ({slots} slot{'s' if slots != 1 else ''} by the regime rule)", "",
          "| Name | Engine | Entry ref (close) | Hard stop | Trail | Clock | Line in the sand (2 ATR) | Void above |", "|---|---|---|---|---|---|---|---|"]
    for t in sigs:
        eng = "D" if rows[t]["sigD"] else "L"; lv = levels(t, eng)
        O.append(f"| {t} | {eng} | {rows[t]['close']:.2f} | {lv['stop']:.2f} | {int(lv['trail']*100)}% off the highest close | {lv['N']} sessions | {lv['line']:.2f} | {lv['void']:.2f} |")
    if not sigs: O.append("| — | nothing fires without a skip | | | | | | |")
    O += ["", "## His positions", ""] + [l for l in B[B.index("## His positions") + 1:] if l.startswith("- ")][:len(positions) or 1]
    O += ["", "## Headlines, last 5 days (Google News; titles and sources only, nothing claimed as cause)", ""]
    for t in research or []:
        for dd, src, title, link in heads.get(t, [])[:3]:
            O.append(f"- **{t}** {dd} · {src}: [{title}]({link})")
    if flags:
        O += ["", "### News flags (SKIP by rule)"] + [f"- **{t}** {dd} · {src}: {title}" for t, fl in flags.items() for dd, src, title in fl[:3]]
    if screen:
        O += ["", "## Monthly mechanical screen", ""] + [l for l in B if l.startswith("- Screen:") or l.startswith("- On both:")]
    O += ["", "---", f"Generated {now.strftime('%Y-%m-%d %H:%M %Z')} by stock-bot/nightly.py (round-3 rules). Numbers from Yahoo Finance; headlines from Google News RSS. No model wrote this file."]

    (out / "brief.md").write_text("\n".join(B) + "\n")
    (out / "latest.md").write_text("\n".join(O) + "\n")
    (out / f"{d.date()}.md").write_text("\n".join(O) + "\n")
    log(f"wrote {out}/brief.md ({len(B)} lines), latest.md ({len(O)} lines); signals={sigs} skipped={skipped_sigs} slots={slots} stale={stale}")


if __name__ == "__main__":
    main()
