# Cloud-Transcoder (kein Gerät im Stall)

Bringt den **Tapo TCA72**-Stream ins Web, **ohne einen Rechner vor Ort** zu betreiben –
der Stream kommt direkt von der Kamera, ein kleiner Cloud-VPS packt ihn nur
browser-fertig um.

## Warum so?

Eine RTSP-Kamera lässt sich **nicht** direkt in ein `<video>`-Tag stecken, und ihre
private LAN-Adresse ist aus dem Internet nicht erreichbar. „RTSPtoWeb" / **go2rtc**
ist genau der Umwandler – aber es ist ein **Server**, der laufen muss und die Kamera
erreichen können muss. **Vercel kann das nicht** (serverlos, kein Dauerprozess).

Lösung ohne Stall-Gerät:

```
Tapo TCA72 ──RTSP──▶ Router-Portfreigabe ──Internet──▶ VPS (go2rtc) ──HTTPS/WebRTC──▶ Browser
```

## Voraussetzungen

- Ein kleiner **VPS** (z. B. Hetzner CX22 / 1 vCPU, ~4 €/Monat), Ubuntu 22.04+.
- Eine **Domain** (A-Record auf die VPS-IP) für automatisches HTTPS.
- **DDNS** für deinen Heimanschluss (IP wechselt), z. B. MyFRITZ! oder DuckDNS.
- **Router-Portfreigabe**: externer Port → `192.168.178.117:554`.

## Einrichtung

```bash
ssh root@DEIN_VPS
git clone <dieses-repo> && cd Die_Stallwache/cloud-transcoder
cp .env.example .env && nano .env     # Kamera, DDNS, VPS-IP, Domain eintragen
sudo bash setup.sh
```

Danach in **Vercel** setzen: `NEXT_PUBLIC_GO2RTC_URL = https://stream.deine-domain.de`
→ der Livestream erscheint auf **die-stallwache.vercel.app**.

## ⚠️ Sicherheit (wichtig)

Eine ins Internet geöffnete Kamera wird gescannt. Deshalb:

- **Quelle der Portfreigabe** am Router/Firewall **auf die VPS-IP einschränken**
  (nur der VPS darf auf die Kamera zugreifen).
- **Starkes Kamerapasswort** verwenden.
- Optional **Basic-Auth** in der `Caddyfile` aktivieren (Anleitung dort).
- Nicht den Standardport 554 nach außen veröffentlichen (z. B. 8554 nutzen).

> Wenn dir das Öffnen der Kamera nach außen zu heikel ist, ist die sichere
> Alternative das winzige Stall-Gerät mit Cloudflare-Tunnel im Ordner
> [`/bridge`](../bridge) – dann ist keine Portfreigabe nötig.
