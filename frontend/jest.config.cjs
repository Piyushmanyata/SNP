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
};
