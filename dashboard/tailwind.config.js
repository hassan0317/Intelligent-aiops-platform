/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        ink: "#0a0a0c",       // page background
        panel: "#111114",     // card surface
        panel2: "#141417",     // nested surface
        edge: "#212126",      // borders
      },
      boxShadow: {
        soft: "0 1px 2px rgba(0,0,0,0.4), 0 8px 24px -12px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(99,102,241,0.25), 0 8px 30px -10px rgba(99,102,241,0.35)",
      },
      keyframes: {
        pulsedot: { "0%,100%": { opacity: 1 }, "50%": { opacity: 0.35 } },
        flow: { "0%": { backgroundPosition: "0% 0" }, "100%": { backgroundPosition: "200% 0" } },
      },
      animation: {
        pulsedot: "pulsedot 1.6s ease-in-out infinite",
        flow: "flow 2.4s linear infinite",
      },
    },
  },
  plugins: [],
};
