import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api, { errorPayload, formatApiError } from "../../lib/api";
import { v4 } from "../../lib/uuid";
import { deskSession, initialDeskSession } from "./deskSession";
import { reasonBody } from "./ManualReason";
import { REQUEST_CONFLICT, registerPatient, registrationError } from "./register";

const AADHAAR_PAYLOAD = /^(\d{100,}|<.*>)$/s;

function superseded() {
  return { outcome: "card", quiet: true, superseded: true };
}

export function useDeskSession({ printPrescription, onCreated, printingOpen, operatingDayId }) {
  const [state, setState] = useState(initialDeskSession);
  const latest = useRef(initialDeskSession);
  const printing = useRef(false);

  const dispatch = useCallback((event) => {
    latest.current = deskSession(latest.current, event);
    setState(latest.current);
    return latest.current;
  }, []);

  useEffect(() => () => { dispatch({ type: "unmounted" }); }, [dispatch]);

  useEffect(() => {
    if (state.paperCheck || !state.focusUsbBox) return;
    dispatch({ type: "usbFocused" });
    document.querySelector("[data-usb-box]")?.focus();
  }, [state.paperCheck, state.focusUsbBox, dispatch]);

  const actions = useMemo(() => {
    const isCurrent = (seq) => seq === latest.current.seq;

    const resolveDoorScan = async (payload) => {
      const { seq } = dispatch({ type: "scanStarted", payload });
      try {
        const { data } = await api.post("/desk/scan", { payload });
        if (!isCurrent(seq)) return superseded();
        dispatch({ type: "scanResolved", seq, result: data });
        return { outcome: "card", source: "desk_scan" };
      } catch (err) {
        if (!isCurrent(seq)) return superseded();
        dispatch({ type: "scanFailed", seq });
        const detail = errorPayload(err);
        if (detail?.code === "NOT_A_CARD") return { outcome: "garbage", message: detail.message };
        throw err;
      }
    };

    const confirmPatient = async (patientId) => {
      const { busy, scanning, scanPayload } = latest.current;
      if (!patientId || busy || scanning) return;
      const { seq } = dispatch({ type: "confirmStarted" });
      try {
        const { data } = await api.post("/desk/scan/confirm", { patient_id: patientId, payload: scanPayload });
        dispatch({ type: "confirmResolved", seq, result: data });
      } catch (err) {
        dispatch({ type: "failed", seq, message: formatApiError(err) });
      } finally {
        dispatch({ type: "settled" });
      }
    };

    const lookup = async (value, reprint) => {
      const { seq } = dispatch({ type: "findStarted" });
      try {
        const { data } = await api.post("/desk/lookup", { value });
        const current = isCurrent(seq);
        dispatch({ type: "lookupResolved", seq, registration: data.registration, reprint });
        return current;
      } catch (err) {
        dispatch({ type: "lookupFailed", seq, message: formatApiError(err) });
        return false;
      }
    };

    const find = async (e) => {
      e?.preventDefault();
      const value = latest.current.findVal.trim();
      if (!value) {
        dispatch({ type: "searchCleared" });
        return;
      }
      if (AADHAAR_PAYLOAD.test(value)) {
        dispatch({ type: "findChanged", value: "" });
        if (!printingOpen) {
          dispatch({ type: "failed", message: "That is an Aadhaar QR. Use New Registration to register this patient." });
          return;
        }
        try {
          const result = await resolveDoorScan(value);
          if (result.outcome !== "card") dispatch({ type: "failed", message: result.message });
        } catch (err) {
          dispatch({ type: "failed", message: formatApiError(err) });
        }
        return;
      }
      if (/^\d+$/.test(value) || /^snp:/i.test(value)) {
        if (await lookup(value, /^\d+$/.test(value))) dispatch({ type: "findChanged", value: "" });
        return;
      }
      const { seq } = dispatch({ type: "findStarted" });
      try {
        const { data } = await api.get(`/patients/search?q=${encodeURIComponent(value)}`);
        dispatch({ type: "searchResolved", seq, results: data.results });
      } catch (err) {
        dispatch({ type: "failed", seq, message: formatApiError(err) });
      }
    };

    const print = async (reg, known) => {
      if (printing.current) return;
      printing.current = true;
      const seq = latest.current.seq;
      dispatch({ type: "printStarted" });
      try {
        let rx = known;
        if (!reg.arrived_at) rx = (await api.post(`/desk/arrive/${reg.id}`)).data.prescription;
        if (!rx) rx = (await api.get(`/desk/print/${reg.id}`)).data.prescription;
        if (!isCurrent(seq)) return;
        await printPrescription(rx);
        dispatch({ type: "printReady", seq, reg, rx });
      } catch (err) {
        dispatch({ type: "failed", seq, message: formatApiError(err) });
      } finally {
        printing.current = false;
      }
    };

    const confirmPaper = async () => {
      const check = latest.current.paperCheck;
      if (!check) return;
      if (!isCurrent(check.request)) {
        dispatch({ type: "paperConfirmed", request: check.request });
        return;
      }
      dispatch({ type: "paperConfirmStarted", request: check.request });
      try {
        const { data } = await api.post(`/desk/print/${check.reg.id}`, { sheet_stamp: check.rx?.sheet_stamp ?? null });
        dispatch({ type: "paperConfirmed", request: check.request, registration: data.registration });
      } catch (err) {
        dispatch({ type: "paperConfirmFailed", request: check.request, message: formatApiError(err) });
      }
    };

    const dismissPaper = (note) => dispatch({ type: "paperDismissed", note });

    const noCardPrint = async (reg, reason) => {
      dispatch({ type: "failed", message: "" });
      try {
        const { data } = await api.post("/desk/no-card", {
          patient_id: reg.id, reason: reason.code, note: reasonBody(reason).note,
          ...(reason.last4 ? { aadhaar_last4: reason.last4 } : {}),
        });
        dispatch({ type: "released", registration: data.registration });
        await print(data.registration);
        return true;
      } catch (err) {
        dispatch({ type: "failed", message: formatApiError(err) });
        return false;
      }
    };

    const submitDoorWalkIn = async () => {
      const { scanResult, scanPayload, doorPhone } = latest.current;
      if (!scanResult?.card) return;
      if (!operatingDayId) {
        dispatch({ type: "failed", message: "No operating camp day. Use Pre-registration." });
        return;
      }
      const { seq, walkIn } = dispatch({ type: "walkInStarted", key: scanPayload || "", reqId: v4() });
      try {
        const card = scanResult.card;
        const created = await registerPatient({
          form: {
            full_name: card.full_name,
            age: card.age ?? "",
            phone: doorPhone,
            gender: card.gender,
            address: card.address,
            aadhaar_last4: card.aadhaar_last4,
            dob: card.dob,
          },
          qrPayload: scanPayload,
          dayId: operatingDayId,
          reqId: walkIn.reqId,
          atDoor: true,
        });
        onCreated(created);
        dispatch({ type: "walkInResolved", seq, registration: created.registration });
      } catch (err) {
        dispatch({
          type: "walkInFailed",
          seq,
          reqId: errorPayload(err)?.code === REQUEST_CONFLICT ? v4() : "",
          message: registrationError(err),
        });
      } finally {
        dispatch({ type: "settled" });
      }
    };

    return {
      resolveDoorScan,
      confirmPatient,
      confirmMismatch: () => confirmPatient(latest.current.scanResult?.registration?.id),
      lookupCode: (value) => lookup(value, false),
      find,
      setFindVal: (value) => dispatch({ type: "findChanged", value }),
      clearSearch: () => dispatch({ type: "searchCleared", clearText: true }),
      print,
      printScanned: (reg) => print(reg, latest.current.scanResult?.prescription),
      confirmPaper,
      printAgain: () => {
        const { reg } = latest.current.paperCheck;
        dismissPaper("");
        print(reg);
      },
      printerProblem: () => dismissPaper("Printer problem. Nothing was recorded. Fix the printer, then press Print again."),
      closePaper: () => dismissPaper("Not recorded as printed. Press Print again when the paper is ready."),
      noCardPrint,
      submitDoorWalkIn,
      setDoorPhone: (phone) => dispatch({ type: "phoneChanged", phone }),
      abandonScan: () => dispatch({ type: "scanAbandoned" }),
      openPreReg: () => dispatch({ type: "modalOpened", mode: "prereg" }),
      preRegBurst: (payload) => dispatch({ type: "modalOpened", mode: "prereg", payload }),
      openDoorManual: () => dispatch({ type: "modalOpened", mode: "door" }),
      closeRegistration: () => dispatch({ type: "modalClosed" }),
      showRegistered: (registration) => dispatch({ type: "registered", registration }),
      showBanner: (message) => dispatch({ type: "bannerShown", message }),
    };
  }, [dispatch, printPrescription, onCreated, printingOpen, operatingDayId]);

  return [state, actions];
}
