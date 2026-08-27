import axios from "axios";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({
  baseURL: `${BACKEND}/api`,
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
