import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        skyline: {
          50: "#eef6ff",
          100: "#d9eaff",
          500: "#2b7de0",
          600: "#1e63b8",
          700: "#184a8c",
          900: "#0f2c55",
        },
      },
    },
  },
  plugins: [],
};
export default config;
