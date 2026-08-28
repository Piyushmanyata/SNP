import axios from "axios";

function isLoopback(host) {
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]" || host === "::1";
}

export function backendOrigin() {
  const env = process.env.REACT_APP_BACKEND_URL || "";
  const loc = window.location;
  const pageHost = loc.hostname;

  let envHost = "";
  try {
    if (env) envHost = new URL(env).hostname;
  } catch {
    envHost = "";
  }

  if (pageHost && !isLoopback(pageHost) && (!envHost || isLoopback(envHost))) {
    const u = new URL(loc.origin);
    u.port = "8000";
    return u.origin;
  }
  if (env) return env;
  return "http://localhost:8000";
}

const api = axios.create({
  baseURL: `${backendOrigin()}/api`,
  withCredentials: true,
});

export function formatApiError(err) {
  const detail = err?.response?.data?.detail;
  if (detail == null) return err?.message || "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail === "object")
    return detail.message || detail.code || JSON.stringify(detail);
  return String(detail);
}

export function errorPayload(err) {
  return err?.response?.data?.detail;
}

export default api;
