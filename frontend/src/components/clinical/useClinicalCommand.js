import { useCallback, useEffect, useMemo, useRef } from "react";
import api, { errorPayload, formatApiError } from "../../lib/api";
import { v4 } from "../../lib/uuid";

const ENDPOINTS = {
  complete: "/clinical/transcription/complete",
  undo: "/clinical/transcription/undo",
  correct: "/clinical/correction",
  issue: "/clinical/fulfilment",
};

const RELOAD_CODES = new Set([
  "STALE_GENERATION",
  "DRAFT_VERSION_CONFLICT",
  "OPERATION_SUPERSEDED",
  "STALE_REVIEW",
  "OPERATION_CONFLICT",
]);

export function clinicalGeneration(patient) {
  return patient?.clinical_generation ?? patient?.registration?.clinical_generation ?? 0;
}

export function classifyClinicalError(err) {
  return {
    kind: RELOAD_CODES.has(errorPayload(err)?.code) ? "reload" : "error",
    message: formatApiError(err),
  };
}

export function useClinicalCommand(kind, patient) {
  const operation = useRef(null);
  const patientId = patient?.registration?.id;
  const generation = clinicalGeneration(patient);

  const reset = useCallback(() => { operation.current = null; }, []);

  useEffect(reset, [patientId, reset]);

  const send = useCallback(async (payload) => {
    const generationField = kind === "issue" ? "reviewed_generation" : "expected_generation";
    const request = { ...payload, [generationField]: generation };
    const key = JSON.stringify(request);
    if (operation.current?.key !== key) operation.current = { key, id: v4() };
    try {
      const { data } = await api.post(ENDPOINTS[kind], { ...request, operation_id: operation.current.id });
      operation.current = null;
      return data;
    } catch (err) {
      const failure = classifyClinicalError(err);
      if (failure.kind === "reload") operation.current = null;
      throw failure;
    }
  }, [kind, generation]);

  return useMemo(() => ({ send, reset }), [send, reset]);
}
