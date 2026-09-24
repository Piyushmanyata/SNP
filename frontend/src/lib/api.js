import axios from "axios";

function isLoopback(host) {
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]" || host === "::1";
}

export function backendOrigin(loc = window.location) {
  const env = process.env.REACT_APP_BACKEND_URL || "";
  const pageHost = loc.hostname;

  let envHost = "";
  try {
    if (env) envHost = new URL(env).hostname;
  } catch {
    envHost = "";
  }

  if (pageHost && !isLoopback(pageHost) && (!envHost || isLoopback(envHost))) {
    return loc.origin;
  }
  if (env) return env;
  return loc.origin;
}

const api = axios.create({
  baseURL: `${backendOrigin()}/api`,
  withCredentials: true,
  timeout: 30000,
});

api.interceptors.response.use(undefined, (err) => {
  if (err?.response?.status === 401 && err.config?.url !== "/auth/login") {
    window.dispatchEvent(new Event("snp:unauthorized"));
  }
  return Promise.reject(err);
});

export function formatApiError(err) {
  const detail = err?.response?.data?.detail;
  if (detail == null) return err?.message || "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail === "object") {
    const text = detail.message
      || (detail.fields ? Object.values(detail.fields).filter(Boolean).join(" ") : "")
      || detail.code
      || JSON.stringify(detail);
    return detail.request_id ? `${text} (ref ${detail.request_id})` : text;
  }
  return String(detail);
}

export function errorPayload(err) {
  return err?.response?.data?.detail;
}

export default api;
