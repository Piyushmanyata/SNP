module.exports = {
  roots: ["<rootDir>/src"],
  testEnvironment: "jsdom",
  setupFiles: ["<rootDir>/scripts/jest-setup.cjs"],
  transform: {
    "^.+\\.[jt]sx?$": "babel-jest",
    "\\.(png|jpe?g|gif|webp|avif|ico|svg)$": "<rootDir>/scripts/asset-transform.cjs",
  },
  moduleNameMapper: { "\\.css$": "<rootDir>/scripts/style-mock.cjs" },
  clearMocks: true,
  collectCoverageFrom: ["src/**/*.{js,jsx}", "!src/**/*.test.{js,jsx}"],
  coverageThreshold: {
    global: { statements: 87, branches: 82, functions: 85, lines: 90 },
  },
};
