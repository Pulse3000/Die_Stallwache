# Archiv – Legacy-Bridge (nicht mehr im Einsatz)

Stallblick lief früher über eine **Bridge**: ein Gerät im Stall (oder ein VPS)
holte den RTSP-Stream der Kameras ab und wandelte ihn in browser-taugliches
WebRTC/HLS um. Seit der Umstellung auf die **Tuya-Cloud** braucht es das nicht
mehr — die Kameras schicken ihr Bild selbst in die Cloud, und die Web-App holt
sich pro Zugriff eine kurzlebige HLS-URL (`lib/tuya.ts`,
`app/api/<kamera>/stream`). Kein Gerät im Stall, keine Portfreigabe, kein
Cloudflare-Tunnel.

Der Code hier ist **nicht mehr Teil des aktiven Systems**. Er bleibt erhalten,
weil er für andere Betriebe weiter nützlich sein kann — etwa wenn dort
RTSP-Kameras ohne Cloud-Anbindung hängen.

| Ordner | Was es war |
| --- | --- |
| [`bridge/`](bridge/README.md) | go2rtc bzw. MediaMTX auf einem Gerät im Stall, öffentlich per Cloudflare Tunnel. Enthält auch die Termux-Variante (Android-Handy statt Raspberry Pi). |
| [`cloud-transcoder/`](cloud-transcoder/README.md) | go2rtc auf einem kleinen VPS, der den RTSP-Stream über eine Router-Portfreigabe direkt von der Kamera holte — die Variante ohne Gerät im Stall. |

## Wann das hier wieder relevant wird

Nur, wenn eine Kamera eingebunden werden soll, die **nicht** Tuya-fähig ist
(z. B. die früher genutzte Tapo TCA72). Dann braucht es wieder einen Umwandler,
denn eine RTSP-Kamera lässt sich weder direkt in ein `<video>`-Tag stecken noch
aus dem Internet erreichen. Für den aktiven Weg siehe stattdessen die
Tuya-Anbindung im Haupt-README.

> Achtung: Die Frontend-Anbindung dieser Bridge (go2rtc-/MediaMTX-URLs,
> WebRTC-Signaling, Snapshot-Polling) wurde aus `lib/config.ts` und
> `components/CameraStream.tsx` entfernt. Ein Reaktivieren erfordert also auch
> Frontend-Arbeit, nicht nur das Starten der Container hier.
