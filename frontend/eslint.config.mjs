import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import hooks from "eslint-plugin-react-hooks";
import accessibility from "eslint-plugin-jsx-a11y";

export default [{
  files: ["src/**/*.{js,jsx}"],
  languageOptions: {
    globals: { ...globals.browser, ...globals.node, ...globals.jest },
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
  plugins: { react, "react-hooks": hooks, "jsx-a11y": accessibility },
  settings: {
    react: { version: "detect" },
    "jsx-a11y": { components: { Input: "input", Select: "select", Textarea: "textarea" } },
  },
  rules: {
    ...js.configs.recommended.rules,
    ...accessibility.configs.recommended.rules,
    "jsx-a11y/no-autofocus": "off",
    "no-unused-vars": ["warn", { args: "none", caughtErrors: "none" }],
    "no-empty": ["error", { allowEmptyCatch: true }],
    "react/jsx-uses-react": "error",
    "react/jsx-uses-vars": "error",
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",
  },
}];
