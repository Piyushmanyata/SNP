import React, { act } from "react";
import ReactDOM from "react-dom/client";
import SelfRegister from "./SelfRegister";
import api from "../lib/api";

jest.mock("../lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
  formatApiError: (e) => e?.message || "error",
}));

jest.mock("../components/AadhaarScanner", () => ({
  __esModule: true,
  default: ({ onScanned, onFailure }) => (
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
    </>
  ),
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

const CAMP = {
  camp: { id: "c1", name: "Sikar Camp", venue: "Sikar Bhawan" },
  days: [{ id: "d1", day_date: "2026-09-01", is_today: true }],
};

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
  expect(container.querySelector('[data-testid="self-register-missing"]').textContent).toBe("Still needed: 10-digit mobile");
});

test.each([
  ["+91 98765 00001", "9876500001"],
  ["09876500001", "9876500001"],
  ["98765-00001", "9876500001"],
  ["98765000012", "9876500001"],
  ["9123456789", "9123456789"],
])("the mobile field normalises %s to %s", async (typed, stored) => {
  await act(async () => root.render(<SelfRegister />));
  const input = container.querySelector('[data-testid="self-phone-input"]');
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, typed);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(input.value).toBe(stored);
  expect(container.querySelector('[data-testid="self-register-missing"]').textContent).toBe("Still needed: Aadhaar card scan");
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
  expect(container.querySelector('[data-testid="self-day-select"]').textContent).toBe("01-09-2026 (today)");
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
