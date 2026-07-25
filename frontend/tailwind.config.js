/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--canvas) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        elevated: "rgb(var(--elevated) / <alpha-value>)",
        label: "rgb(var(--label) / <alpha-value>)",
        "label-2": "rgb(var(--label-2) / <alpha-value>)",
        "label-3": "rgb(var(--label-3) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        positive: "rgb(var(--green) / <alpha-value>)",
        negative: "rgb(var(--red) / <alpha-value>)",
        caution: "rgb(var(--orange) / <alpha-value>)",
      },
      backgroundColor: {
        fill: "rgb(var(--fill) / var(--fill-opacity))",
      },
      ringColor: {
        separator: "rgb(var(--separator) / var(--separator-opacity))",
      },
      borderColor: {
        separator: "rgb(var(--separator) / var(--separator-opacity))",
      },
      divideColor: {
        separator: "rgb(var(--separator) / var(--separator-opacity))",
      },
      fontFamily: {
        // The system stack resolves to SF Pro on Apple platforms.
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Text",
          "SF Pro Display",
          "Inter",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SF Mono", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        // Anchored on the iOS/macOS type scale.
        caption: ["12px", { lineHeight: "16px", letterSpacing: "0em" }],
        footnote: ["13px", { lineHeight: "18px", letterSpacing: "-0.005em" }],
        subhead: ["15px", { lineHeight: "20px", letterSpacing: "-0.01em" }],
        body: ["17px", { lineHeight: "24px", letterSpacing: "-0.015em" }],
        headline: ["17px", { lineHeight: "22px", letterSpacing: "-0.02em" }],
        title3: ["20px", { lineHeight: "25px", letterSpacing: "-0.02em" }],
        title2: ["24px", { lineHeight: "30px", letterSpacing: "-0.022em" }],
        title1: ["30px", { lineHeight: "36px", letterSpacing: "-0.025em" }],
        display: ["40px", { lineHeight: "44px", letterSpacing: "-0.03em" }],
      },
      borderRadius: {
        xl: "12px",
        "2xl": "18px",
        "3xl": "24px",
      },
      boxShadow: {
        card: "0 1px 2px rgb(var(--shadow-color) / 0.04), 0 4px 16px rgb(var(--shadow-color) / 0.05)",
        lift: "0 2px 6px rgb(var(--shadow-color) / 0.06), 0 12px 32px rgb(var(--shadow-color) / 0.10)",
        toast:
          "0 4px 12px rgb(var(--shadow-color) / 0.10), 0 20px 48px rgb(var(--shadow-color) / 0.18)",
      },
      transitionTimingFunction: {
        // Apple's standard decelerating curve.
        spring: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
    },
  },
  plugins: [],
};
