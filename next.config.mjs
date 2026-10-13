/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Kein X-Powered-By-Header (verraet Framework/Version unnoetig).
  poweredByHeader: false,
  // Nur genutzte Module aus grossen Paketen buendeln (kleinere Bundles
  // im Stall-WLAN/Mobilfunk).
  experimental: {
    optimizePackageImports: ["three", "firebase"],
  },
  // Der Preview-Proxy reicht den Browser-Origin an den Dev-Server durch.
  // Next.js prueft diesen Origin ab 15.2 gegen eine Allowlist und blockiert
  // sonst Dev-Assets/HMR, obwohl die Seite selbst laedt. BASE44_* sind
  // umgebungsspezifisch, deshalb nur per Variable referenziert.
  allowedDevOrigins: [
    process.env.BASE44_PUBLIC_HOST_SUFFIX
      ? `3000-${process.env.BASE44_PUBLIC_HOST_SUFFIX}`
      : null,
    process.env.BASE44_SANDBOX_HOST_DOMAIN
      ? `*.${process.env.BASE44_SANDBOX_HOST_DOMAIN}`
      : null,
  ].filter(Boolean),
};

export default nextConfig;
