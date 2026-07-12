# Stallblick-Bridge auf einem Android-Handy (Termux)

Workaround für Betriebe **ohne** Raspberry Pi/Mini-PC/NAS: go2rtc und
cloudflared sind einzelne, abhängigkeitsfreie Linux-Binaries (kein Docker
nötig) und laufen deshalb auch unter **Termux** — einem echten
Linux-Terminal für Android, ohne Root.

> **iPhone/iOS geht nicht.** Apple erlaubt keine dauerhaften
> Hintergrundprozesse für Drittanbieter-Apps — eine Bridge auf iOS ist
> technisch nicht sauber umsetzbar. Dieser Weg funktioniert nur mit einem
> Android-Gerät.

## Einschränkungen (bitte vorher lesen)

- **Weniger zuverlässig als dedizierte Hardware.** Android kann Prozesse
  trotz aller Vorkehrungen unter Speicherdruck oder nach System-Updates
  beenden — dann fällt die Stallwache-Kamera aus, bis das Handy neu
  gestartet/geprüft wird.
- Das Handy muss **dauerhaft an Strom + WLAN** bleiben, und Termux darf
  nicht manuell aus den „Kürzlich verwendete Apps" weggewischt werden
  (das beendet den Hintergrundprozess sofort).
- **Kein offizieller Support** von go2rtc/cloudflared für Android — es
  funktioniert, weil beide als reine Linux-ARM-Binaries vorliegen, die
  Termux ausführen kann.
- Für den dauerhaften 24/7-Betrieb ist eine dedizierte Hardware (z. B.
  Raspberry Pi Zero 2 W, ca. 20 €) langfristig die robustere Lösung — dieser
  Weg ist ein guter, funktionierender Einstieg ohne Zusatzkauf.

## Schnellweg: Ein-Befehl-Installation

Wer die Einzelschritte überspringen will: Nach dem Installieren von **Termux**
(Schritt 1) genügt in Termux ein einziger Befehl — das Skript erkennt die
CPU-Architektur, lädt go2rtc + cloudflared, fragt Kamera-Zugangsdaten und
Tunnel-Token interaktiv ab, richtet den Autostart ein und startet die Bridge:

```bash
pkg install -y curl && \
bash <(curl -fsSL https://raw.githubusercontent.com/Pulse3000/Die_Stallwache/main/bridge/termux/install.sh)
```

Danach nur noch im Cloudflare-Dashboard den Public Hostname auf
`http://localhost:1984` zeigen lassen (Schritt 5) und die Tunnel-Adresse
melden. Wer lieber jeden Schritt selbst nachvollzieht, folgt der Anleitung
unten.

---

## 1. Termux installieren

**Nicht** aus dem Play Store (die dortige Version ist veraltet und wird
nicht mehr gepflegt) — stattdessen:

- [Termux via F-Droid](https://f-droid.org/packages/com.termux/) installieren
- Zusätzlich **Termux:Boot** (gleicher Store, gleicher Entwickler) für
  Autostart nach einem Neustart des Handys

## 2. Android vorbereiten

- *Einstellungen → Apps → Termux → Akku* → **„Uneingeschränkt"**
  (keine Batterieoptimierung für Termux)
- WLAN-Einstellungen: „WLAN im Ruhezustand aktiv lassen" aktivieren
  (Bezeichnung variiert je Android-Version, meist unter
  *Einstellungen → WLAN → Erweitert*)
- Handy dauerhaft ans Ladegerät anschließen

## 3. Binaries herunterladen

In Termux öffnen und ausführen:

```bash
pkg update && pkg install wget git termux-tools -y
uname -m   # meist "aarch64" bei modernen Handys (ab ca. 2016)

git clone https://github.com/Pulse3000/Die_Stallwache.git ~/Die_Stallwache
cd ~/Die_Stallwache/bridge/termux

# go2rtc (ARM64 – bei "armv7l" statt "aarch64" unten arm64 durch arm ersetzen)
wget https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64 -O go2rtc
chmod +x go2rtc

# cloudflared (ARM64 – bei "armv7l" entsprechend cloudflared-linux-arm laden)
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -O cloudflared
chmod +x cloudflared
```

## 4. Konfiguration eintragen

```bash
cp .env.example .env
nano .env   # TAPO_IP, TAPO_USER, TAPO_PASS eintragen (Speichern: Strg+O, Enter, Strg+X)
```

Die go2rtc-Konfiguration (`../go2rtc.yaml`, also
`bridge/go2rtc.yaml` im Repo) wird direkt mitverwendet — keine zweite Kopie
nötig, dieselbe Datei wie beim Docker-Setup.

## 5. Cloudflare Tunnel Token eintragen

Wie im Haupt-Setup ([`../README.md`](../README.md)):

1. [Zero Trust Dashboard](https://one.dash.cloudflare.com) → *Networks →
   Tunnels* → „Create a tunnel" (Typ „Cloudflared")
2. Namen vergeben (z. B. `stallwache-bridge`), **Token kopieren**
3. Token in `.env` bei `CLOUDFLARE_TUNNEL_TOKEN` eintragen
4. Im selben Dashboard unter „Public Hostname": Subdomain wählen (z. B.
   `stallwache.deine-domain.de`), Service → HTTP, URL → `localhost:1984`

## 6. Starten

```bash
bash start-bridge.sh
```

Logs prüfen:

```bash
tail -f logs/go2rtc.log logs/cloudflared.log
```

## 7. Autostart nach Neustart (mit Termux:Boot)

```bash
mkdir -p ~/.termux/boot
cp start-bridge.sh ~/.termux/boot/
```

Termux:Boot einmalig öffnen und die angeforderte Berechtigung erteilen —
danach startet die Bridge automatisch, sobald das Handy neu startet.

## 8. Prüfen & Webapp verbinden

`https://DEIN-HOSTNAME` sollte das go2rtc-Webinterface zeigen und den Stream
`stallwache` auflisten. Danach wie im Haupt-Setup: `NEXT_PUBLIC_BRIDGE_URL`
in Vercel auf diesen Hostname setzen — sag kurz Bescheid, dann übernehme ich
das und verifiziere die Stallwache live.

## Fehlersuche

| Problem | Ursache / Lösung |
| --- | --- |
| Bridge fällt nach einiger Zeit aus | Akku-Optimierung doch aktiv, oder Termux wurde aus „Kürzlich verwendet" entfernt — Schritt 2 erneut prüfen |
| `termux-wake-lock: command not found` | `pkg install termux-tools` (Skript läuft trotzdem weiter, nur ohne Wake-Lock) |
| Falsche Architektur (`Exec format error`) | `uname -m` prüfen; bei `armv7l` die `_arm`- statt `_arm64`-Binaries laden |
| Nach Handy-Neustart offline | Termux:Boot-Berechtigung fehlt oder Schritt 7 nicht ausgeführt |
