import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";

window.addEventListener("vite:preloadError", () => window.location.reload());

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
