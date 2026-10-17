"""Names and static facts the nightly job needs. Edit here, nowhere else. No prices, no judgment."""
# His list, round 3 (R1 screen of 2026-10-15). Added or dropped only at the quarterly screen or when he names one.
WATCH = "AAOI BE IREN LITE NBIS INFQ CRWV AXTI SPCX SNDK MU ARM AMD NVDA IONQ WULF WDC STX".split()
# Company names, used only to build news searches.
NAMES = {"AAOI": "Applied Optoelectronics", "BE": "Bloom Energy", "IREN": "IREN", "LITE": "Lumentum", "NBIS": "Nebius",
         "INFQ": "Infleqtion", "CRWV": "CoreWeave", "AXTI": "AXT Inc", "SPCX": "SpaceX", "SNDK": "Sandisk", "MU": "Micron",
         "ARM": "Arm Holdings", "AMD": "AMD", "NVDA": "Nvidia", "IONQ": "IonQ", "WULF": "TeraWulf", "WDC": "Western Digital", "STX": "Seagate"}
BENCH = ["SPY", "QQQ", "SMH", "IWM", "^VIX", "^TNX"]
CONTROL = "AAPL MSFT GOOGL AMZN META AVGO TSLA ORCL CRM NFLX HOOD".split()
# The 100-name pool for the monthly mechanical screen (round 3). Winners and busts alike; no hindsight on who won after.
POOL = sorted(set("""SMCI INTC MRVL TSM ASML AMAT LRCX KLAC QCOM TXN ADI NXPI ON MCHP SWKS QRVO SITM CRDO ALAB COHR CIEN ANET DELL HPE VRT ONTO ACLS AEHR
PLTR AI SOUN BBAI PATH SNOW MDB NET DDOG CRWD ROKU U RBLX SHOP RDDT DJT GME AMC
COIN MSTR RIOT MARA CLSK HUT CIFR CORZ APLD BTDR
RGTI QUBT QBTS ASTS RKLB LUNR ACHR JOBY SMR OKLO NNE VST CEG TLN GEV
ENPH SEDG PLUG FSLR RIVN LCID NIO UPST AFRM SOFI CVNA
CLS FN MOD POWL NVMI CAMT TER ENTG MPWR SNPS CDNS SMTC MTSI LSCC RMBS CRUS AMBA WOLF INDI""".split()))
# Lock-up expiries (R4 skip 4): within 10 trading days → skip.
LOCKUPS = {"SPCX": "2026-12-09"}
# Macro dates the brief prints (next one or two). Add as they are known; stale ones fall off automatically.
MACRO = [("2026-10-28", "FOMC decision"), ("2026-11-06", "jobs report"), ("2026-11-10", "CPI")]
# News flag (R4 skip 3): a headline in the last 3 days matching one of these marks the name SKIP (he can disagree in the morning).
NEWS_FLAGS = [r"\boffering\b", r"\bsecondary\b", r"\bconvertible\b", r"guidance (cut|lower)", r"(cuts|lowers|slashes) (its )?(guidance|outlook|forecast)",
              r"\binvestigat", r"\bsubpoena", r"\bdelist", r"going concern", r"\brestat", r"CEO (resign|steps down|departs|exits|out)",
              r"SEC (probe|charges)", r"short[- ]seller report", r"Hindenburg", r"Muddy Waters", r"\bfraud\b"]
# News relevance: a headline counts for a name only if it matches one of these (the bare ticker, case-sensitive, is always tried too).
ALIASES = {"AAOI": ["Applied Optoelectronics", "Applied Opto"], "BE": ["Bloom Energy", r"\bBloom\b"], "IREN": ["Iris Energy", r"\bIREN\b"],
           "LITE": ["Lumentum"], "NBIS": ["Nebius"], "INFQ": ["Infleqtion"], "CRWV": ["CoreWeave"], "AXTI": [r"\bAXT\b"], "SPCX": ["SpaceX"],
           "SNDK": ["Sandisk"], "MU": ["Micron"], "ARM": [r"\bArm Holdings\b", r"\bArm\b"], "AMD": ["Advanced Micro"], "NVDA": ["Nvidia"],
           "IONQ": ["IonQ"], "WULF": ["TeraWulf"], "WDC": ["Western Digital"], "STX": ["Seagate"]}
# Headlines dropped as noise (options-chain pages, 13F filler, chart pages).
NOISE = [r"\d+\.\d+ (call|put)\b", r"Stock Price, News, Quote", r"[Ii]nteractive [Ss]tock [Cc]hart", r"Shares (Sold|Bought|Purchased|Acquired) by",
         r"(Boosts|Grows|Raises|Trims|Cuts|Lowers|Increases|Reduces|Acquires|Sells|Buys|Purchases|Has|Takes|Makes) (Position|Stake|Holdings|New (Position|Stake)|\$?[\d,.]+ ?[MKB]? (Shares|Stake|Position))",
         r"Stock Position|Holdings in|Stake in .* (Lifted|Lowered|Raised|Reduced|Boosted|Cut)"]
NOISE_SOURCES = {"MarketBeat", "Defense World", "ETF Daily News", "Ticker Report", "The Markets Daily"}
