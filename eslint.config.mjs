import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// Next 16 hat `next lint` entfernt — ESLint laeuft direkt (npm run lint);
// eslint-config-next v16 liefert native Flat-Configs.
const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "edge-agent/**", // Python-Projekt
      "bridge/**", // Shell/Docker, kein JS
    ],
  },
];

export default eslintConfig;
