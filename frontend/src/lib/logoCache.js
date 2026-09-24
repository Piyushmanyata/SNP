import api from "./api";

const REFRESH_MS = 10 * 60 * 1000;
const cache = new Map();

export function loadLogos(campId) {
  const hit = cache.get(campId);
  if (hit && (!hit.fetchedAt || Date.now() - hit.fetchedAt < REFRESH_MS)) return hit.promise;
  const entry = { fetchedAt: 0, promise: null };
  entry.promise = api.get(`/templates/logos?camp_id=${campId}`).then(
    ({ data }) => {
      entry.fetchedAt = Date.now();
      return data.logos || [];
    },
    (err) => {
      if (hit) {
        cache.set(campId, hit);
        return hit.promise;
      }
      cache.delete(campId);
      throw err;
    },
  );
  cache.set(campId, entry);
  return entry.promise;
}

export function forgetLogos(campId) {
  cache.delete(campId);
}
