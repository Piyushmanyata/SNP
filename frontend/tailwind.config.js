module.exports = {
  content: ["./src/**/*.{js,jsx}", "./index.html"],
  theme: {
    extend: {
      colors: {
        emerald: {
          50: "#ecfdf5", 100: "#d1fae5", 500: "#059669", 600: "#047857", 700: "#065f46",
        },
      },
      fontFamily: {
      sans: ["system-ui", "sans-serif"],
      display: ["system-ui", "sans-serif"],
      mono: ["ui-monospace", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
