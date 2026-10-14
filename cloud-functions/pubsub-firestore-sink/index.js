/**
 * Pub/Sub → Firestore-Sink für Stall-Ereignisse.
 *
 * Schreibt jede Nachricht aus dem Topic `PUBSUB_TOPIC` (siehe lib/pubsub.ts
 * der Webapp) in die Firestore-Collection `stall_ereignisse`. Zweck: ein
 * dauerhaft abfragbarer Lese-Speicher für Status-Routinen (z. B. den
 * zweimal täglichen KuhWatch-Tagesreport), die keinen Zugriff auf den
 * In-Memory-Ringpuffer der Webapp haben.
 *
 * Diese Function ist ein zusätzlicher Pub/Sub-Abonnent, kein Ersatz für die
 * bestehende Archiv-/BigQuery-Nachanalyse — mehrere Abos am selben Topic
 * sind in Pub/Sub der Normalfall.
 *
 * Deploy: siehe README.md in diesem Ordner.
 */

const { Firestore } = require("@google-cloud/firestore");

const firestore = new Firestore();
const COLLECTION = process.env.FIRESTORE_COLLECTION || "stall_ereignisse";

/**
 * Cloud Functions (2nd gen) Pub/Sub-Handler.
 * `message.data` ist Base64-kodiertes JSON, `message.attributes` enthält
 * typ/kamera/kuhId (siehe lib/pubsub.ts — dort gesetzt, damit Filter ohne
 * Payload-Parsing möglich sind).
 */
exports.pubsubFirestoreSink = async (message, context) => {
  let ereignis;
  try {
    const roh = Buffer.from(message.data || "", "base64").toString("utf8");
    ereignis = JSON.parse(roh);
  } catch (e) {
    console.error("Nutzlast ist kein gültiges JSON, verwerfe Nachricht:", e);
    return;
  }

  const attribute = message.attributes || {};
  const dokument = {
    ...ereignis,
    typ: attribute.typ ?? ereignis.typ ?? null,
    kamera: attribute.kamera ?? ereignis.kamera ?? null,
    kuhId: attribute.kuhId ?? ereignis.kuhId ?? null,
    empfangenAm: Firestore.Timestamp.now(),
    pubsubMessageId: context?.eventId ?? null,
  };

  // ID aus dem Ereignis übernehmen, wenn vorhanden — macht den Sink
  // idempotent gegen Pub/Sub-At-least-once-Zustellung (doppelte Nachricht
  // überschreibt statt zu duplizieren).
  const docId = ereignis.id ? String(ereignis.id) : undefined;
  const ref = docId
    ? firestore.collection(COLLECTION).doc(docId)
    : firestore.collection(COLLECTION).doc();

  await ref.set(dokument, { merge: true });
};
