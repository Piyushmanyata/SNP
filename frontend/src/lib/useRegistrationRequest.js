import { useMemo, useRef } from "react";
import { errorPayload } from "./api";
import { v4 } from "./uuid";

export const REQUEST_CONFLICT = "REGISTRATION_REQUEST_CONFLICT";

export function useRegistrationRequest() {
  const held = useRef(null);

  return useMemo(() => ({
    async send(payload, post) {
      const key = JSON.stringify(payload);
      if (held.current?.key !== key) held.current = { key, id: v4() };
      const attempt = held.current;
      const release = () => { if (held.current === attempt) held.current = null; };
      try {
        const result = await post(attempt.id);
        release();
        return result;
      } catch (err) {
        if (errorPayload(err)?.code === REQUEST_CONFLICT) release();
        throw err;
      }
    },
    reset() { held.current = null; },
  }), []);
}
