import { defineConfig, loadEnv, transformWithEsbuild } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "REACT_APP_");
  return {
    plugins: [{
      name: "source-jsx",
      enforce: "pre",
      transform(code, id) {
        if (/\/src\/.*\.js$/.test(id)) {
          return transformWithEsbuild(code, id, { loader: "jsx", jsx: "automatic" });
        }
      },
    }],
    define: {
      "process.env.REACT_APP_BACKEND_URL": JSON.stringify(env.REACT_APP_BACKEND_URL || ""),
      "process.env.PUBLIC_URL": JSON.stringify(""),
    },
    optimizeDeps: { esbuildOptions: { loader: { ".js": "jsx" } } },
    server: { proxy: { "/api": "http://localhost:8000" } },
    build: {
      outDir: "build",
      target: ["chrome80", "firefox78", "safari13.1"],
      assetsDir: "static",
      sourcemap: false,
    },
  };
});
