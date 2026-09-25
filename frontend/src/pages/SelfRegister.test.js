import React, { act } from "react";
import ReactDOM from "react-dom/client";
import SelfRegister from "./SelfRegister";
import api from "../lib/api";

jest.mock("../lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
  formatApiError: (e) => e?.response?.data?.detail?.message || e?.message || "error",
  errorPayload: (e) => e?.response?.data?.detail,
}));

let mockScannerProps = null;

jest.mock("../components/AadhaarScanner", () => ({
  __esModule: true,
  default: (props) => {
    mockScannerProps = props;
    const { onScanned, onFailure } = props;
    return (
    <>
    <button
      type="button"
      data-testid="fake-scan"
      onClick={() =>
        onScanned({
          full_name: "Sunita Devi",
          gender: "F",
          dob: "1975-06-14",
          age: 51,
          address: "12 Station Road",
          aadhaar_last4: "1234",
        }, "AADHAAR|Sunita Devi|F|1975-06-14|123456781234|12 Station Road")
      }
    >
      scan
    </button>
    <button type="button" data-testid="fake-failure" onClick={() => onFailure("garbage")}>fail</button>
    <button type="button" data-testid="fake-not-aadhaar" onClick={() => onFailure("not-aadhaar")}>not aadhaar</button>
    <button type="button" data-testid="fake-network" onClick={() => onFailure("request")}>network</button>
    <button type="button" data-testid="fake-camera" onClick={() => onFailure("error")}>camera</button>
    </>
    );
  },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

const STILL_NEEDED_MOBILE = "Still needed / अभी बाकी: 10-digit mobile / 10 अंकों का मोबाइल";
const PAST = { id: "d0", day_date: "2026-08-31", is_today: false, is_past: true, registered: 5, seat_limit: 50, remaining: 45 };
const TODAY_OPEN = { id: "d1", day_date: "2026-09-01", is_today: true, is_past: false, registered: 12, seat_limit: 50, remaining: 38 };
const TODAY_FULL = { ...TODAY_OPEN, registered: 50, remaining: 0 };
const TOMORROW_OPEN = { id: "d2", day_date: "2026-09-02", is_today: false, is_past: false, registered: 3, seat_limit: 30, remaining: 27 };
const TOMORROW_FULL = { ...TOMORROW_OPEN, registered: 30, remaining: 0 };

const CAMP = {
  camp: { id: "c1", name: "Sikar Camp", venue: "Sikar Bhawan" },
  days: [TODAY_OPEN],
};

function withDays(days) {
  api.get.mockResolvedValue({ data: { ...CAMP, days } });
}

let container;
let root;

beforeEach(() => {
  api.get.mockResolvedValue({ data: CAMP });
  api.post.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  jest.clearAllMocks();
});

async function renderAndScan() {
  await act(async () => {
    root.render(<SelfRegister />);
  });
  await act(async () => {
    container.querySelector('[data-testid="fake-scan"]').click();
  });
  act(() => {
    const input = container.querySelector('[data-testid="self-phone-input"]');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    setter.call(input, "9876500001");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

test("submit stays disabled without a mobile number", async () => {
  await act(async () => {
    root.render(<SelfRegister />);
  });
  await act(async () => {
    container.querySelector('[data-testid="fake-scan"]').click();
  });
  expect(container.querySelector('[data-testid="self-register-submit"]').disabled).toBe(true);
  expect(container.querySelector('[data-testid="self-register-missing"]').textContent).toBe(STILL_NEEDED_MOBILE);
});

function typePhone(value) {
  const input = container.querySelector('[data-testid="self-phone-input"]');
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  return input;
}

test.each([
  ["+91 98765 00001", "9876500001"],
  ["+91-98765-00001", "9876500001"],
  ["09876500001", "9876500001"],
  ["98765-00001", "9876500001"],
  ["9123456789", "9123456789"],
])("the mobile field keeps %s as typed and registers %s", async (typed, stored) => {
  await act(async () => root.render(<SelfRegister />));
  await act(async () => container.querySelector('[data-testid="fake-scan"]').click());
  expect(typePhone(typed).value).toBe(typed);
  expect(container.querySelector('[data-testid="self-register-missing"]')).toBeNull();
  api.post.mockResolvedValueOnce({ data: { receipt: { reg_no: 14, patient_qr: "qr-14" } } });
  await submit();
  expect(api.post.mock.calls[0][1].phone).toBe(stored);
});

test.each(["98765000012", "1234567890", "0091 98765 00001", "98765"])("the mobile %s is refused before registration", async (typed) => {
  await act(async () => root.render(<SelfRegister />));
  await act(async () => container.querySelector('[data-testid="fake-scan"]').click());
  typePhone(typed);
  expect(container.querySelector('[data-testid="self-register-submit"]').disabled).toBe(true);
  expect(container.querySelector('[data-testid="self-register-missing"]').textContent).toBe(STILL_NEEDED_MOBILE);
});

test("a scan submits the QR payload and never typed identity", async () => {
  await renderAndScan();
  api.post.mockResolvedValueOnce({ data: { receipt: { reg_no: 14, patient_qr: "qr-14" } } });
  await submit();
  const body = api.post.mock.calls[0][1];
  expect(body.qr_payload).toBe("AADHAAR|Sunita Devi|F|1975-06-14|123456781234|12 Station Road");
  expect(body).not.toHaveProperty("manual_entry");
  expect(body).not.toHaveProperty("aadhaar_scanned");
  expect(body).not.toHaveProperty("dob");
  expect(body).not.toHaveProperty("age");
  expect(body).not.toHaveProperty("aadhaar_last4");
  expect(container.textContent).not.toContain("identity check");
});

test("dates read DD-MM-YYYY in the day picker, the card preview and the receipt", async () => {
  await renderAndScan();
  expect(container.querySelector('[data-testid="self-day-select"]').textContent).toBe("01-09-2026 (today / आज) · 38 seats left / 38 सीटें बाकी");
  expect(container.querySelector('[data-testid="self-scanned-preview"]').textContent).toContain("14-06-1975");
  api.post.mockResolvedValueOnce({ data: { receipt: { reg_no: 14, patient_qr: "qr-14", day_date: "2026-09-01" } } });
  await submit();
  const receipt = container.querySelector('[data-testid="self-receipt"]').textContent;
  expect(receipt).toContain("01-09-2026");
  expect(receipt).not.toContain("2026-09-01");
});

test("a failed read sends the patient to the desk and offers no typed path", async () => {
  await act(async () => root.render(<SelfRegister />));
  expect(container.querySelector('[data-testid="self-scan-required"]')).toBeNull();
  await act(async () => container.querySelector('[data-testid="fake-failure"]').click());
  expect(container.querySelector('[data-testid="self-scan-required"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="self-enter-details"]')).toBeNull();
  expect(container.querySelector('[data-testid="aadhaar-review-form"]')).toBeNull();
  expect(container.querySelector('[data-testid="self-register-submit"]').disabled).toBe(true);
});

test("a card that is not an Aadhaar QR also sends the patient to the desk", async () => {
  await act(async () => root.render(<SelfRegister />));
  await act(async () => container.querySelector('[data-testid="fake-not-aadhaar"]').click());
  expect(container.querySelector('[data-testid="self-scan-required"]')).not.toBeNull();
});

test.each(["fake-network", "fake-camera"])("a %s failure asks the patient to try again, not to go to the desk", async (trigger) => {
  await act(async () => root.render(<SelfRegister />));
  await act(async () => container.querySelector(`[data-testid="${trigger}"]`).click());
  expect(container.querySelector('[data-testid="self-scan-required"]')).toBeNull();
  expect(container.querySelector('[data-testid="self-scan-retry"]').textContent).toContain("try again");
  await act(async () => container.querySelector('[data-testid="fake-scan"]').click());
  expect(container.querySelector('[data-testid="self-scan-retry"]')).toBeNull();
});

test("a locked card scan clears the go-to-the-desk notice", async () => {
  await act(async () => root.render(<SelfRegister />));
  await act(async () => container.querySelector('[data-testid="fake-failure"]').click());
  await act(async () => container.querySelector('[data-testid="fake-scan"]').click());
  expect(container.querySelector('[data-testid="self-scan-required"]')).toBeNull();
  expect(container.querySelector('[data-testid="self-scanned-preview"]')).not.toBeNull();
});

function submit() {
  return act(async () => {
    container.querySelector('[data-testid="self-register-submit"]').click();
  });
}

test("a retry after a failed submit reuses the same registration request id", async () => {
  await renderAndScan();
  api.post.mockRejectedValueOnce(new Error("Network Error"));
  await submit();
  api.post.mockResolvedValueOnce({
    data: { receipt: { reg_no: 12, patient_qr: "qr-12" } },
  });
  await submit();

  const ids = api.post.mock.calls.map((c) => c[1].registration_request_id);
  expect(ids).toHaveLength(2);
  expect(ids[0]).toBeTruthy();
  expect(ids[0]).toBe(ids[1]);
});

test("a different patient scanned after a failed submit gets its own request id", async () => {
  await renderAndScan();
  api.post.mockRejectedValueOnce(new Error("Network Error"));
  await submit();
  await act(async () => {
    container.querySelector('[data-testid="fake-scan"]').click();
  });
  api.post.mockResolvedValueOnce({
    data: { receipt: { reg_no: 13, patient_qr: "qr-13" } },
  });
  await submit();

  const ids = api.post.mock.calls.map((c) => c[1].registration_request_id);
  expect(ids[0]).toBeTruthy();
  expect(ids[1]).toBeTruthy();
  expect(ids[0]).not.toBe(ids[1]);
});

test("registering another patient starts a new request id", async () => {
  await renderAndScan();
  api.post.mockResolvedValue({
    data: { receipt: { reg_no: 12, patient_qr: "qr-12" } },
  });
  await submit();
  const firstId = api.post.mock.calls[0][1].registration_request_id;

  await act(async () => {
    container.querySelector('[data-testid="self-register-another"]').click();
  });
  await act(async () => {
    container.querySelector('[data-testid="fake-scan"]').click();
  });
  await submit();

  expect(api.post.mock.calls[1][1].registration_request_id).not.toBe(firstId);
});

test("the camp day comes first, lists today and later only, and starts on the first day with seats", async () => {
  withDays([PAST, TODAY_FULL, TOMORROW_OPEN]);
  await renderAndScan();
  const select = container.querySelector('[data-testid="self-day-select"]');
  const options = [...select.options];
  expect(options.map((o) => o.value)).toEqual(["d1", "d2"]);
  expect(options[0].disabled).toBe(true);
  expect(options[0].textContent).toContain("Full / भरा हुआ");
  expect(options[1].disabled).toBe(false);
  expect(options[1].textContent).toContain("27 seats left / 27 सीटें बाकी");
  expect(select.value).toBe("d2");
  expect(container.textContent).not.toContain("31-08-2026");
  const scanner = container.querySelector('[data-testid="fake-scan"]');
  expect(select.compareDocumentPosition(scanner) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  api.post.mockResolvedValueOnce({ data: { receipt: { reg_no: 3, patient_qr: "qr-3" } } });
  await submit();
  expect(api.post.mock.calls[0][1].camp_day_id).toBe("d2");
});

test("when every remaining day is full the page says the desk still registers everyone who comes", async () => {
  withDays([PAST, TODAY_FULL, TOMORROW_FULL]);
  await act(async () => root.render(<SelfRegister />));
  const notice = container.querySelector('[data-testid="self-all-full"]');
  expect(notice.textContent).toContain("Online booking is full");
  expect(notice.textContent).toContain("01-09-2026, 02-09-2026");
  expect(notice.textContent).toContain("Sikar Bhawan");
  expect(notice.textContent).toContain("registers everyone who comes");
  expect(notice.textContent).toContain("ऑनलाइन बुकिंग भर गई है");
  expect(notice.textContent).not.toContain("31-08-2026");
  expect(container.querySelector('[data-testid="fake-scan"]')).toBeNull();
  expect(container.querySelector('[data-testid="self-register-submit"]')).toBeNull();
});

test("a camp whose days have all passed offers no booking", async () => {
  withDays([PAST]);
  await act(async () => root.render(<SelfRegister />));
  expect(container.querySelector('[data-testid="self-no-camp"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="fake-scan"]')).toBeNull();
});

test("staff sign in is a quiet link to the staff page", async () => {
  await act(async () => root.render(<SelfRegister />));
  const link = container.querySelector('[data-testid="goto-staff-login-link"]');
  expect(link.getAttribute("href")).toBe("/login");
  expect(link.textContent).toBe("Staff sign in");
});

test("the scanner runs for a patient, without the USB / paste box", async () => {
  await act(async () => root.render(<SelfRegister />));
  expect(mockScannerProps.forPatient).toBe(true);
});

test.each(["CAMP_DAY_FULL", "DAY_PASSED"])("a %s refusal reloads the days and moves to the next day with seats", async (code) => {
  withDays([TODAY_OPEN, TOMORROW_OPEN]);
  await renderAndScan();
  withDays([TODAY_FULL, TOMORROW_OPEN]);
  api.post.mockRejectedValueOnce({ response: { data: { detail: { code, message: "This camp day is full." } } } });
  await submit();
  expect(api.get).toHaveBeenCalledTimes(2);
  expect(container.querySelector('[data-testid="self-day-select"]').value).toBe("d2");
  expect(container.textContent).toContain("This camp day is full.");
  expect(container.querySelector('[data-testid="self-scanned-preview"]')).not.toBeNull();
});

test("a network failure on submit keeps the page as it is", async () => {
  await renderAndScan();
  api.post.mockRejectedValueOnce(new Error("Network Error"));
  await submit();
  expect(api.get).toHaveBeenCalledTimes(1);
});

test("registering another patient reloads the seats left", async () => {
  await renderAndScan();
  api.post.mockResolvedValueOnce({ data: { receipt: { reg_no: 12, patient_qr: "qr-12" } } });
  await submit();
  expect(container.querySelector('[data-testid="self-receipt"]').textContent).toContain("आपका रजिस्ट्रेशन हो गया");
  await act(async () => container.querySelector('[data-testid="self-register-another"]').click());
  expect(api.get).toHaveBeenCalledTimes(2);
});
