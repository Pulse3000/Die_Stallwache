import type { CameraId } from "@/lib/config";

/** Kamera-State laut Stallblick-Zustandsmodell. */
export type CameraState = "online" | "offline" | "laedt" | "instabil";

export const CAMERA_STATE_LABEL: Record<CameraState, string> = {
  online: "Online",
  offline: "Offline",
  laedt: "Lädt…",
  instabil: "Instabil",
};

/**
 * Feature-State pro Kamera. Reiner UI-State – bewusst vom Device-State
 * entkoppelt: Schaltvorgaenge wirken sofort in der UI und werden spaeter
 * asynchron mit der Kamera synchronisiert (Stufe 2 der Roadmap).
 */
export type FeatureState = {
  nachtsicht: boolean;
  privatsphaere: boolean;
  bewegung: boolean;
  sirene: boolean;
  aufnahme: boolean;
};

export const DEFAULT_FEATURES: FeatureState = {
  nachtsicht: false,
  privatsphaere: false,
  bewegung: true,
  sirene: false,
  aufnahme: true,
};

export type FeaturesByCamera = Record<CameraId, FeatureState>;

/** Eintrag der Ereignisliste (nachgelagert geladen). */
export type StallEvent = {
  id: string;
  /** z.B. "Bewegung erkannt" */
  title: string;
  camera: CameraId;
  /** Relative Zeitangabe, z.B. "vor 2 Min" */
  when: string;
  kind: "bewegung" | "geraeusch" | "warnung" | "aufnahme";
};
