import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api, { formatApiError } from "../../lib/api";
import { useRegistrationRequest } from "../../lib/useRegistrationRequest";
import { useWedgeBurst } from "../aadhaar";
import { registerPatient, registrationFailure } from "./register";
import { initialRegisterForm, registerForm, registrationView } from "./registerForm";

export function useRegisterForm({ open, atDoor, doorDayId, days, initialPayload, onClose, onDone, onRegistered, setBanner }) {
  const [state, setState] = useState(initialRegisterForm);
  const latest = useRef(initialRegisterForm);
  const inputs = useRef(null);
  inputs.current = { atDoor, doorDayId, days, onClose, onDone, onRegistered, setBanner };
  const wasOpen = useRef(false);
  const request = useRegistrationRequest();

  const dispatch = useCallback((event) => {
    latest.current = registerForm(latest.current, event);
    setState(latest.current);
    return latest.current;
  }, []);

  const readCard = useCallback(async (payload) => {
    const { seq } = dispatch({ type: "readStarted" });
    try {
      const { data } = await api.post("/aadhaar/decode", { payload });
      const current = seq === latest.current.seq;
      dispatch({ type: "readResolved", seq, outcome: data.outcome, data: data.data, payload, message: data.message });
      if (current && data.outcome === "card") request.reset();
    } catch (err) {
      dispatch({ type: "readFailed", seq, message: formatApiError(err) });
    }
  }, [dispatch, request]);

  useEffect(() => {
    dispatch({ type: "contextChanged" });
    return () => { dispatch({ type: "contextChanged" }); };
  }, [open, state.manualMode, dispatch]);

  useEffect(() => {
    if (open && !wasOpen.current) {
      dispatch({ type: "opened", atDoor });
      request.reset();
    }
    wasOpen.current = open;
  }, [open, atDoor, dispatch, request]);

  useEffect(() => {
    if (open && initialPayload) readCard(initialPayload);
  }, [open, initialPayload, readCard]);

  const { receiving } = useWedgeBurst({
    enabled: open && !atDoor && !state.manualMode && !state.busy,
    onBurst: readCard,
    onInterrupted: () => dispatch({ type: "usbInterrupted" }),
  });

  const save = useCallback(async ({ next = false, reviewConfirmedId = null, differentPerson = false } = {}) => {
    const desk = inputs.current;
    const { form, qrPayload, reason } = latest.current;
    const { canSubmit, bookedDay } = registrationView(latest.current, desk);
    if (!canSubmit) return;
    dispatch({ type: "saveStarted" });
    try {
      const data = await registerPatient(request, {
        form, qrPayload, dayId: bookedDay, reason, atDoor: desk.atDoor, reviewConfirmedId, differentPerson,
      });
      const reg = data.registration;
      desk.setBanner(desk.atDoor
        ? `Registered and arrived: #${reg.reg_no} — ${reg.full_name}`
        : `Registered #${reg.reg_no} — ${reg.full_name}. SMS sent.`);
      desk.onRegistered?.(reg);
      desk.onDone(data);
      dispatch({ type: "saveSucceeded", next, atDoor: desk.atDoor });
      if (!next) desk.onClose();
    } catch (err) {
      dispatch({ type: "saveFailed", failure: registrationFailure(err) });
    }
  }, [dispatch, request]);

  const actions = useMemo(() => ({
    onScanned: (data, payload) => {
      dispatch({ type: "cardScanned", data, payload });
      request.reset();
    },
    captureStarted: () => dispatch({ type: "captureStarted" }),
    setField: (field, value) => dispatch({ type: "fieldChanged", field, value }),
    chooseReason: (reason) => dispatch({ type: "reasonChosen", reason }),
    chooseDay: (id) => dispatch({ type: "dayChosen", id }),
    toggleManual: () => dispatch({ type: "manualToggled" }),
    save,
  }), [dispatch, request, save]);

  const view = registrationView(state, { atDoor, doorDayId, days });
  return [{ ...state, ...view, receiving }, actions];
}
