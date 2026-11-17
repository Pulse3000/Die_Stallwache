import sys, json, sqlite3, datetime, os

bild = sys.argv[1] if len(sys.argv) > 1 else "?"
raw = sys.stdin.read().strip()
try:
    dat = json.loads(raw)
except Exception:
    dat = {"h": None, "d": [], "err": raw[:120] or "keine Ausgabe"}

dets = dat.get("d", [])
h = dat.get("h")
klassen = ",".join(sorted({x["c"] for x in dets}))
ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# DB-Pfad: relativ zum Script oder über Env-Variable
DB_PATH = os.environ.get("STALLWACHE_DB", os.path.join(os.path.expanduser("~"), "Die_Stallwache", "data", "dauerlauf.db"))

db = sqlite3.connect(DB_PATH)
db.execute("CREATE TABLE IF NOT EXISTS detektionen (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, bild TEXT, helligkeit REAL, anzahl INTEGER, klassen TEXT, det_json TEXT)")
db.execute("INSERT INTO detektionen (ts, bild, helligkeit, anzahl, klassen, det_json) VALUES (?,?,?,?,?,?)",
           (ts, bild, h, len(dets), klassen, json.dumps(dets)))
db.commit()
db.close()

if dat.get("err"):
    print(f"{ts[11:]} | ANALYSE_FEHLER: {dat['err']}")
else:
    det = ", ".join(f"{x['c']} {x['k']}" for x in sorted(dets, key=lambda a: a["k"])) if dets else "keine"
    print(f"{ts[11:]} | {bild} | {h if h is not None else '?'} | {det}")
