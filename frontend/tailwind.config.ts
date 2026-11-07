import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      screens: {
        xs: "475px",
      },
      colors: {
        "bg-base": "var(--bg-base)",
        "surface-panel": "var(--surface-panel)",
        "surface-elevated": "var(--surface-elevated)",
        "surface-pill": "var(--surface-pill)",
        "surface-pill-hover": "var(--surface-pill-hover)",
        "border-subtle": "var(--border-subtle)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-muted": "var(--text-muted)",
        "accent-blue": "var(--accent-blue)",
      },
    },
  },
  plugins: [],
};

export default config;
