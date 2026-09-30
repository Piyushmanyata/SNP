export const initialDeskSession = Object.freeze({
  seq: 0,
  regMode: "",
  preRegPayload: "",
  scanResult: null,
  scanPayload: "",
  scanning: false,
  busy: false,
  found: null,
  findVal: "",
  searchResults: null,
  banner: "",
  error: "",
  doorPhone: "",
  paperCheck: null,
  printNote: "",
  focusUsbBox: false,
});

function newFind(state) {
  return {
    ...state,
    seq: state.seq + 1,
    banner: "",
    error: "",
    searchResults: null,
    found: null,
    scanResult: null,
    scanPayload: "",
    paperCheck: null,
  };
}

function arrivedBanner(registration, extra = "") {
  return `Arrived: #${registration.reg_no} — ${registration.full_name}${extra}`;
}

export function deskSession(state, event) {
  const current = event.seq === undefined || event.seq === state.seq;
  switch (event.type) {
    case "scanStarted":
      return {
        ...newFind(state),
        regMode: state.regMode === "door" ? "" : state.regMode,
        doorPhone: "",
        scanPayload: event.payload,
        scanning: true,
      };
    case "scanResolved":
      if (!current) return state;
      return {
        ...state,
        scanResult: event.result,
        scanning: false,
        banner: event.result.outcome === "arrived"
          ? arrivedBanner(event.result.registration, event.result.overwritten ? " (card details updated)" : "")
          : state.banner,
      };
    case "scanFailed":
      if (!current) return state;
      return { ...state, scanResult: null, scanPayload: "", scanning: false };
    case "scanAbandoned":
      return { ...state, seq: state.seq + 1, scanResult: null, scanPayload: "", doorPhone: "", scanning: false };
    case "confirmStarted":
      return { ...state, seq: state.seq + 1, busy: true, error: "" };
    case "confirmResolved":
      if (!current) return state;
      return { ...state, scanResult: event.result, banner: arrivedBanner(event.result.registration) };
    case "findStarted":
      return { ...newFind(state), scanning: false };
    case "lookupResolved":
      if (!current) return state;
      return { ...state, found: { reg: event.registration, reprint: event.reprint } };
    case "lookupFailed":
      if (!current) return state;
      return { ...state, found: null, error: event.message };
    case "searchResolved":
      if (!current) return state;
      return { ...state, searchResults: event.results };
    case "searchCleared":
      return { ...state, searchResults: null, findVal: event.clearText ? "" : state.findVal };
    case "findChanged":
      return { ...state, findVal: event.value };
    case "failed":
      if (!current) return state;
      return { ...state, error: event.message };
    case "printStarted":
      return { ...state, error: "", printNote: "" };
    case "printReady":
      if (!current) return state;
      return { ...state, paperCheck: { reg: event.reg, rx: event.rx, request: event.seq, busy: false, error: "" } };
    case "paperConfirmStarted":
      if (state.paperCheck?.request !== event.request) return state;
      return { ...state, paperCheck: { ...state.paperCheck, busy: true, error: "" } };
    case "paperConfirmed":
      if (event.request !== state.seq) {
        return state.paperCheck?.request === event.request ? { ...state, paperCheck: null } : state;
      }
      return {
        ...state,
        seq: state.seq + 1,
        paperCheck: null,
        scanResult: null,
        scanPayload: "",
        found: null,
        banner: `Printed #${event.registration.reg_no} — ${event.registration.full_name}. Next patient.`,
        focusUsbBox: true,
      };
    case "paperConfirmFailed":
      if (state.paperCheck?.request !== event.request) return state;
      return { ...state, paperCheck: { ...state.paperCheck, busy: false, error: event.message } };
    case "paperDismissed":
      return {
        ...state,
        paperCheck: null,
        scanResult: state.scanResult && { ...state.scanResult, prescription: null },
        printNote: event.note,
      };
    case "usbFocused":
      return { ...state, focusUsbBox: false };
    case "released": {
      const reg = event.registration;
      return {
        ...state,
        found: state.found?.reg.id === reg.id ? { ...state.found, reg } : state.found,
        searchResults: state.searchResults && state.searchResults.map((row) => (row.id === reg.id ? reg : row)),
      };
    }
    case "walkInResolved":
      if (!current) return state;
      if (!event.registration.arrived_at) {
        return {
          ...state,
          scanResult: null,
          scanPayload: "",
          doorPhone: "",
          found: { reg: event.registration, reprint: true },
        };
      }
      return {
        ...state,
        scanResult: { outcome: "arrived", registration: event.registration, prescription: null },
        scanPayload: "",
        banner: `Registered and arrived: #${event.registration.reg_no} — ${event.registration.full_name}`,
        doorPhone: "",
      };
    case "settled":
      return { ...state, busy: false };
    case "phoneChanged":
      return { ...state, doorPhone: event.phone };
    case "modalOpened":
      return { ...state, regMode: event.mode, preRegPayload: event.payload ?? "" };
    case "modalClosed":
      return { ...state, regMode: "", preRegPayload: "" };
    case "registered":
      return { ...state, found: { reg: event.registration, reprint: true } };
    case "printingChanged":
      return { ...state, found: null, searchResults: null };
    case "bannerShown":
      return { ...state, banner: event.message };
    case "unmounted":
      return { ...state, seq: state.seq + 1 };
    default:
      throw new Error(`Unknown Desk session event: ${event.type}`);
  }
}
