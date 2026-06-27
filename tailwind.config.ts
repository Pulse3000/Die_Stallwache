import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        stall: {
          bg: "#0b1120",
          card: "#111a2e",
          accent: "#22c55e",
        },
      },
    },
  },
  plugins: [],
};

export default config;
