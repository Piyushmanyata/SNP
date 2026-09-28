import axios from "axios";
import { setOffline } from "./connection";

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

function answeredByApi(response) {
  return Boolean(response) && !(response.status >= 502 && response.status <= 504 && !response.data?.detail);
}

const sequence = new WeakMap();
let sent = 0;
let newestAnswered = 0;

function answered(config) {
  newestAnswered = Math.max(newestAnswered, sequence.get(config) ?? 0);
  setOffline(false);
}

api.interceptors.request.use((config) => {
  sent += 1;
  sequence.set(config, sent);
  return config;
});

api.interceptors.response.use((response) => {
  answered(response.config);
  return response;
}, (err) => {
  if (answeredByApi(err?.response)) answered(err.config);
  else if (!axios.isCancel(err) && (sequence.get(err?.config) ?? Infinity) > newestAnswered) setOffline(true);
  if (err?.response?.status === 401 && err.config?.url !== "/auth/login") {
    window.dispatchEvent(new Event("snp:unauthorized"));
  }
  return Promise.reject(err);
});

const NO_ANSWER = {
  ERR_NETWORK: "No connection to the server. Check the internet, then try again.",
  ECONNABORTED: "The server did not answer in time. Check the internet, then try again.",
};

export function formatApiError(err) {
  const detail = err?.response?.data?.detail;
  if (detail == null) return NO_ANSWER[err?.code] || err?.message || "Something went wrong. Please try again.";
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
