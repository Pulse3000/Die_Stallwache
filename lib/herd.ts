/**
 * Lokale Herden-Daten fuer die 3D-Stall-Ansicht.
 * Eigenstaendig (keine Abhaengigkeit zu externen Projekten); bei Bedarf
 * spaeter durch echte Stalldaten / localStorage ersetzbar.
 */

export type KuhStatus =
  | "Gesund"
  | "Trächtig"
  | "In Behandlung"
  | "Trockengestellt";

export type Kuh = {
  nr: number;
  name: string;
  status: KuhStatus;
  rasse: string;
  alter: number;
  laktation: number;
  milchTagesleistung: number;
  kalbungVoraussichtlich?: string; // ISO-Datum
  notiz?: string;
};

/** Statusfarben (Hex) fuer 3D-Marker, Tooltips und Legende. */
export const STATUS_COLOR: Record<KuhStatus, string> = {
  Gesund: "#4caf84",
  Trächtig: "#e8975e",
  "In Behandlung": "#e05c5c",
  Trockengestellt: "#6ba4e0",
};

export function ohrmarkeFor(nr: number): string {
  return `DE 08 123 4${String(5000 + nr).padStart(4, "0")}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function daysUntil(iso: string): number {
  const d = new Date(iso);
  const now = new Date();
  return Math.round((d.getTime() - now.getTime()) / 86_400_000);
}

const RASSEN = ["Fleckvieh", "Braunvieh", "Holstein", "Grauvieh"];
const NAMEN = [
  "Berta", "Resi", "Linde", "Emma", "Greta", "Frieda", "Hanni", "Lotte",
  "Mira", "Paula", "Senta", "Vroni", "Wanda", "Xenia", "Zita", "Anni",
];

/** Erzeugt eine plausible Beispielherde (Reihe A). */
function makeHerd(count: number): Kuh[] {
  const statuses: KuhStatus[] = [
    "Gesund", "Gesund", "Gesund", "Trächtig", "Trächtig",
    "In Behandlung", "Trockengestellt",
  ];
  const today = new Date();
  return Array.from({ length: count }, (_, i) => {
    const nr = i + 1;
    const status = statuses[i % statuses.length];
    const traechtig = status === "Trächtig";
    const kalbung = new Date(today);
    kalbung.setDate(today.getDate() + 12 + ((i * 17) % 60));
    return {
      nr,
      name: NAMEN[i % NAMEN.length],
      status,
      rasse: RASSEN[i % RASSEN.length],
      alter: 3 + (i % 7),
      laktation: 1 + (i % 5),
      milchTagesleistung:
        status === "Trockengestellt" ? 0 : 22 + ((i * 3) % 14),
      kalbungVoraussichtlich: traechtig ? kalbung.toISOString() : undefined,
      notiz:
        status === "In Behandlung"
          ? "Klauenpflege – Kontrolle in 3 Tagen"
          : traechtig
            ? "Brunst-/Kalbeüberwachung aktiv"
            : undefined,
    };
  });
}

export const initialKuehe: Kuh[] = makeHerd(14);
