#!/usr/bin/env python3
"""
Stallwache API Server — stall_api.py
Liest aus Die_Stallwache/data/dauerlauf.db
Endpunkte: /health, /status, /events, /statistics
"""
import json, sqlite3, datetime, subprocess, re, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

DB = os.environ.get(
    "STALLWACHE_DB",
    os.path.join(os.path.expanduser("~"), "Die_Stallwache", "data", "dauerlauf.db")
)
PID_FILE = os.path.join(os.path.expanduser("~"), "Die_Stallwache", "logs", "dauerlauf.pid")

def q(sql, args=()):
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    rows = db.execute(sql, args).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_temp():
    try:
        out = subprocess.run(["sensors"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"temp1:\s+\+([\d.]+)", out)
        return float(m.group(1)) if m else None
    except Exception:
        return None

def pid_active():
    try:
        pid = int(open(PID_FILE).read().strip())
        subprocess.run(["kill", "-0", str(pid)], check=True)
        return pid
    except Exception:
        return None

class H(BaseHTTPRequestHandler):
    def j(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        args = parse_qs(u.query)
        try:
            if p == "/health":
                letzte = q("SELECT ts, bild, helligkeit, anzahl, klassen FROM detektionen ORDER BY id DESC LIMIT 1")
                pid = pid_active()
                self.j({
                    "status": "ok" if pid else "WARNUNG: Dauerlauf nicht aktiv",
                    "dauerlauf_pid": pid,
                    "cpu_temp": get_temp(),
                    "letzte_analyse": letzte[0] if letzte else None,
                    "zeit": datetime.datetime.now().isoformat(timespec="seconds"),
                    "db": DB
                })
            elif p == "/status":
                rows = q("SELECT ts, bild, helligkeit, anzahl, klassen FROM detektionen ORDER BY id DESC LIMIT ?",
                         (int(args.get("n", ["10"])[0]),))
                self.j({"zyklen": rows})
            elif p == "/events":
                hours = int(args.get("hours", ["24"])[0])
                rows = q("SELECT ts, bild, helligkeit, anzahl, klassen, det_json FROM detektionen WHERE anzahl > 0 AND ts >= datetime('now','localtime', ?) ORDER BY id DESC LIMIT 500",
                         (f"-{hours} hours",))
                self.j({"fenster_stunden": hours, "tier_ereignisse": rows})
            elif p == "/statistics":
                days = int(args.get("days", ["1"])[0])
                rows = q("SELECT COUNT(*) total, COALESCE(SUM(anzahl>0),0) mit_tier, ROUND(AVG(helligkeit),1) h_avg, MIN(helligkeit) h_min, MAX(helligkeit) h_max FROM detektionen WHERE ts >= datetime('now','localtime', ?)",
                         (f"-{days} days",))
                self.j({"fenster_tage": days, "statistik": rows[0]})
            else:
                self.j({"endpunkte": ["/health", "/status?n=10", "/events?hours=24", "/statistics?days=1"]}, 404)
        except Exception as e:
            self.j({"fehler": str(e)}, 500)

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print(f"Stallwache API auf :8123 — DB: {DB}")
    HTTPServer(("0.0.0.0", 8123), H).serve_forever()
