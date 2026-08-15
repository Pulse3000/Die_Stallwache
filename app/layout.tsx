import type { Metadata, Viewport } from "next";
import PwaLaufzeit from "@/components/PwaLaufzeit";
import TabLeiste from "@/components/TabLeiste";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stallwache",
  description:
    "KI-gestuetzte Brunst- und Kalbeueberwachung im Stall: Livebild der Kameras, Alarme mit Bild, Geraetesteuerung — offlinefaehig.",
  manifest: "/manifest.webmanifest",
  applicationName: "Stallwache",
  icons: {
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/logo-mark.svg", type: "image/svg+xml" },
    ],
    apple: "/icon-192.png",
  },
  appleWebApp: {
    capable: true,
    title: "Stallwache",
    // Statusleiste transparent, damit die App auf iOS bis nach oben laeuft.
    statusBarStyle: "black-translucent",
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: "#0b1120",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  // Inhalt bis in die Display-Aussparungen ziehen; die Innenabstaende unten
  // arbeiten mit den safe-area-Variablen.
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="de">
      {/* Unterer Innenabstand = Hoehe der Tab-Leiste + Home-Indicator. */}
      <body className="min-h-dvh pb-[calc(3.25rem+env(safe-area-inset-bottom))] antialiased">
        {children}
        <PwaLaufzeit />
        <TabLeiste />
      </body>
    </html>
  );
}
