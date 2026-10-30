# CLAUDE.md

## Session-Grenzen (Stand 30.10.2026 · Session Bauleiter)

- `npm run build` und Smoke-Test nur gegen laufenden Dev-Server; Docker-Daemon nicht in Cloud-Session verfügbar → Vercel-Preview übernimmt die Build-Prüfung.
- `REPORT_READ_TOKEN` muss der Betreiber in Vercel (Production) und als Secret der Report-Routine setzen — nicht im Repo.
- Punkt 4 (Trainer/kuhwatch): Datensatz-Inventur-Skripte liegen im goalpaket; Ausführung auf dem stallwache-Computer ist Betreiber-Sache (kein Remote-Control-Zugriff aus Cloud-Session).
