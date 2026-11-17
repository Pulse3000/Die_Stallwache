# Hinweis: Dauerlauf-Prozess neu starten

Der Dauerlauf-Prozess läuft noch mit dem alten Script (`~/dauerlauf.sh`) 
und schreibt Logs/PID nach `~/dauerlauf.log` und `~/dauerlauf.pid`.

**Nach dem nächsten Neustart / manuellen Stopp:**

```bash
# Alten Prozess stoppen
kill $(cat ~/dauerlauf.pid) 2>/dev/null

# Neues Script starten
nohup ~/Die_Stallwache/scripts/dauerlauf.sh &
```

Das neue Script schreibt nach:
- Logs:  ~/Die_Stallwache/logs/dauerlauf.log
- PID:   ~/Die_Stallwache/logs/dauerlauf.pid
- DB:    ~/Die_Stallwache/data/dauerlauf.db

**stall_api.py** ebenfalls mit neuem Pfad starten:
```bash
python3 ~/Die_Stallwache/scripts/stall_api.py
```
