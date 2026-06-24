/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: { ink: "#16221b", paper: "#f4f1e9", moss: "#285943", gold: "#bf8a3d" },
      fontFamily: { sans: ["Inter", "Noto Sans SC", "system-ui", "sans-serif"] },
      boxShadow: { card: "0 18px 50px rgba(22,34,27,.09)" },
    },
  },
  plugins: [],
};
