"use client";

import { useCallback, useEffect, useState } from "react";
import { useEinstellungen } from "@/lib/einstellungen";
import { ALARM_TYPEN, type EreignisTyp } from "@/lib/ereignis-modell";
import { TYP_ERKLAERUNG, TYP_LABEL } from "@/lib/darstellung";

/**
 * An-/Abmeldung fuer Push-Benachrichtigungen (Firebase Cloud Messaging).
 *
 * Der Ablauf hat mehr Fallstricke als der Knopf vermuten laesst, deshalb
 * benennt die Oberflaeche jeden davon konkret statt „Fehler":
 *   - Der Server muss senden koennen (Service Account + Firebase-Projekt).
 *   - Der Browser muss die Erlaubnis geben — auf iOS erst, wenn die App zum
 *     Home-Bildschirm hinzugefuegt wurde. Im Safari-Tab gibt es keinen Push.
 *   - Das Geraete-Token muss beim Server ankommen und dort bleiben.
 *
 * Das Firebase-SDK wird erst beim Anmelden geladen (dynamischer Import) — es
 * ist der groesste Brocken der App und im Normalbetrieb nicht noetig.
 */

interface KonfigAntwort {
  aktiv: boolean;
  versandBereit: boolean;
  konfig: {
    apiKey: string;
    authDomain: string;
    projectId: string;
    messagingSenderId: string;
    appId: string;
    vapidKey: string;
  } | null;
}

const TOKEN_SCHLUESSEL = "stallwache:push-token";

export default function PushSchalter() {
  const [einstellungen, aendern] = useEinstellungen();
  const [konfig, setKonfig] = useState<KonfigAntwort | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [arbeitet, setArbeitet] = useState(false);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [erlaubnis, setErlaubnis] = useState<NotificationPermission | "nicht-unterstuetzt">(
    "default",
  );
  const [installiert, setInstalliert] = useState(true);

  useEffect(() => {
    let beendet = false;
    // Erst die Serverantwort abwarten, dann den Geraetezustand einlesen: bis
    // dahin zeigt die Karte ohnehin „Wird geprüft …", und alle Zustaende
    // wechseln gemeinsam statt in zwei Schueben.
    const pruefen = async () => {
      let antwort: KonfigAntwort;
      try {
        const res = await fetch("/api/push/konfig", { cache: "no-store" });
        antwort = (await res.json()) as KonfigAntwort;
      } catch {
        antwort = { aktiv: false, versandBereit: false, konfig: null };
      }
      if (beendet) return;

      setToken(localStorage.getItem(TOKEN_SCHLUESSEL));
      setErlaubnis(
        typeof Notification === "undefined" ? "nicht-unterstuetzt" : Notification.permission,
      );
      // iOS erlaubt Web-Push ausschliesslich in der installierten PWA.
      const standalone =
        window.matchMedia("(display-mode: standalone)").matches ||
        (navigator as { standalone?: boolean }).standalone === true;
      const istIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
      setInstalliert(!istIos || standalone);
      setKonfig(antwort);
    };
    void pruefen();
    return () => {
      beendet = true;
    };
  }, []);

  const anmelden = useCallback(async () => {
    if (!konfig?.konfig) return;
    setArbeitet(true);
    setMeldung(null);
    try {
      const erlaubt = await Notification.requestPermission();
      setErlaubnis(erlaubt);
      if (erlaubt !== "granted") {
        setMeldung(
          "Benachrichtigungen wurden abgelehnt. In den Browser-Einstellungen für diese Seite wieder erlauben.",
        );
        return;
      }

      const [{ initializeApp, getApps }, { getMessaging, getToken }] = await Promise.all([
        import("firebase/app"),
        import("firebase/messaging"),
      ]);
      const app = getApps()[0] ?? initializeApp(konfig.konfig);
      const registrierung = await navigator.serviceWorker.ready;
      const neuesToken = await getToken(getMessaging(app), {
        vapidKey: konfig.konfig.vapidKey,
        // Unser eigener Worker nimmt den Push entgegen (siehe public/sw.js) —
        // kein zweiter firebase-messaging-sw.js noetig.
        serviceWorkerRegistration: registrierung,
      });
      if (!neuesToken) throw new Error("Kein Geräte-Token erhalten.");

      const res = await fetch("/api/push/registrieren", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          token: neuesToken,
          typen: einstellungen.pushTypen,
          geraet: geraeteName(),
        }),
      });
      if (!res.ok) throw new Error((await res.json()).fehler ?? `HTTP ${res.status}`);

      localStorage.setItem(TOKEN_SCHLUESSEL, neuesToken);
      setToken(neuesToken);
      setMeldung("Dieses Gerät bekommt jetzt Alarme.");
    } catch (e) {
      setMeldung(e instanceof Error ? e.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setArbeitet(false);
    }
  }, [konfig, einstellungen.pushTypen]);

  const abmelden = useCallback(async () => {
    if (!token) return;
    setArbeitet(true);
    try {
      await fetch(`/api/push/registrieren?token=${encodeURIComponent(token)}`, {
        method: "DELETE",
      });
      try {
        const [{ getApps }, { getMessaging, deleteToken }] = await Promise.all([
          import("firebase/app"),
          import("firebase/messaging"),
        ]);
        const app = getApps()[0];
        if (app) await deleteToken(getMessaging(app));
      } catch {
        // Serverseitig abgemeldet ist das Entscheidende; ein zurueckbleibendes
        // Browser-Token bekommt dann schlicht nichts mehr zugestellt.
      }
      localStorage.removeItem(TOKEN_SCHLUESSEL);
      setToken(null);
      setMeldung("Dieses Gerät bekommt keine Alarme mehr.");
    } finally {
      setArbeitet(false);
    }
  }, [token]);

  /** Auswahl der Alarmarten – wirkt sofort, wenn das Geraet angemeldet ist. */
  const typUmschalten = useCallback(
    async (typ: EreignisTyp) => {
      const vorhanden = einstellungen.pushTypen.includes(typ);
      const neu = vorhanden
        ? einstellungen.pushTypen.filter((t) => t !== typ)
        : [...einstellungen.pushTypen, typ];
      aendern({ pushTypen: neu });
      if (token) {
        await fetch("/api/push/registrieren", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ token, typen: neu, geraet: geraeteName() }),
        }).catch(() => setMeldung("Auswahl konnte nicht übertragen werden."));
      }
    },
    [einstellungen.pushTypen, aendern, token],
  );

  const testen = useCallback(async () => {
    setArbeitet(true);
    setMeldung(null);
    try {
      const res = await fetch("/api/push/test", { method: "POST" });
      const json = await res.json();
      setMeldung(
        res.ok
          ? `Probealarm an ${json.zugestellt} Gerät(e) geschickt.`
          : (json.fehler ?? "Probealarm fehlgeschlagen."),
      );
    } catch {
      setMeldung("Probealarm fehlgeschlagen – keine Verbindung.");
    } finally {
      setArbeitet(false);
    }
  }, []);

  const angemeldet = Boolean(token) && erlaubnis === "granted";

  return (
    <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
      <div className="flex items-center gap-2">
        <span
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${
            angemeldet ? "bg-stall-accent" : "bg-white/25"
          }`}
        />
        <p className="flex-1 text-sm font-semibold">
          {angemeldet ? "Alarme auf diesem Gerät" : "Keine Alarme auf diesem Gerät"}
        </p>
      </div>

      {konfig === null ? (
        <p className="mt-2 text-[11px] text-white/40">Wird geprüft …</p>
      ) : !konfig.konfig ? (
        <p className="mt-2 text-[11px] leading-relaxed text-white/50">
          Push ist noch nicht eingerichtet. Im Firebase-Projekt eine Web-App
          anlegen und <code className="rounded bg-black/40 px-1">FIREBASE_API_KEY</code>,{" "}
          <code className="rounded bg-black/40 px-1">FIREBASE_MESSAGING_SENDER_ID</code>,{" "}
          <code className="rounded bg-black/40 px-1">FIREBASE_APP_ID</code> und{" "}
          <code className="rounded bg-black/40 px-1">FIREBASE_VAPID_KEY</code> setzen.
        </p>
      ) : !konfig.versandBereit ? (
        <p className="mt-2 text-[11px] leading-relaxed text-white/50">
          Der Server kann noch nicht senden –{" "}
          <code className="rounded bg-black/40 px-1">GCP_SERVICE_ACCOUNT_JSON</code> mit
          FCM-Berechtigung fehlt.
        </p>
      ) : erlaubnis === "nicht-unterstuetzt" ? (
        <p className="mt-2 text-[11px] text-white/50">
          Dieser Browser unterstützt keine Benachrichtigungen.
        </p>
      ) : !installiert ? (
        <p className="mt-2 text-[11px] leading-relaxed text-white/50">
          Auf dem iPhone gibt es Push nur in der installierten App: in Safari
          über <strong>Teilen → Zum Home-Bildschirm</strong> hinzufügen und die
          App von dort öffnen.
        </p>
      ) : (
        <>
          <button
            onClick={() => void (angemeldet ? abmelden() : anmelden())}
            disabled={arbeitet}
            className={`mt-2.5 w-full rounded-xl py-2.5 text-sm font-semibold ring-1 disabled:opacity-50 ${
              angemeldet
                ? "bg-white/10 ring-white/10 active:bg-white/25"
                : "bg-stall-accent/20 text-stall-accent ring-stall-accent/30"
            }`}
          >
            {arbeitet ? "Moment …" : angemeldet ? "Alarme abschalten" : "Alarme einschalten"}
          </button>

          {angemeldet && (
            <>
              <fieldset className="mt-3">
                <legend className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
                  Wofür benachrichtigen
                </legend>
                <div className="flex flex-col gap-1.5">
                  {ALARM_TYPEN.map((typ) => (
                    <label
                      key={typ}
                      className="flex items-start gap-2.5 rounded-lg bg-black/20 px-3 py-2"
                    >
                      <input
                        type="checkbox"
                        checked={einstellungen.pushTypen.includes(typ)}
                        onChange={() => void typUmschalten(typ)}
                        className="mt-0.5 h-4 w-4 shrink-0 accent-stall-accent"
                      />
                      <span className="min-w-0">
                        <span className="block text-xs font-semibold">
                          {TYP_LABEL[typ]}
                        </span>
                        <span className="block text-[10px] text-white/40">
                          {TYP_ERKLAERUNG[typ]}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <button
                onClick={() => void testen()}
                disabled={arbeitet}
                className="mt-2 w-full rounded-xl bg-white/5 py-2 text-xs font-semibold text-white/70 ring-1 ring-white/10 active:bg-white/15 disabled:opacity-50"
              >
                Probealarm senden
              </button>
            </>
          )}
        </>
      )}

      {meldung && (
        <p role="status" className="mt-2 rounded-lg bg-white/10 p-2.5 text-[11px] text-white/80">
          {meldung}
        </p>
      )}
    </div>
  );
}

/** Grobe Geraetebezeichnung, damit sich mehrere Anmeldungen unterscheiden lassen. */
function geraeteName(): string {
  const ua = navigator.userAgent;
  if (/iphone|ipad|ipod/i.test(ua)) return "iPhone/iPad";
  if (/android/i.test(ua)) return "Android-Gerät";
  return "Browser";
}
