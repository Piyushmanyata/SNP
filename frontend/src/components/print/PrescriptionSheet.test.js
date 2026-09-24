import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { PrescriptionSheet } from "./PrescriptionSheet";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const RX = {
  camp_id: "camp-001", camp_name: "SNP Camp Nadia", venue: "Community Center", reg_no: "1001",
  patient_qr: "qr-1001", full_name: "Aparna Sen", age: 45, gender: "F", date: "2026-08-27",
  phone: "9876543210", address: "12 MG Road",
};

function render(props) {
  act(() => root.render(<PrescriptionSheet rx={RX} {...props} />));
  return container.querySelector('[data-testid="a4-prescription-sheet"]');
}

test("the sheet is the whole document: no buttons, no page chrome, no network", () => {
  const sheet = render();
  expect(container.querySelector("button")).toBeNull();
  expect(container.querySelector("style")).toBeNull();
  expect(container.firstElementChild).toBe(sheet);
  for (const block of ["rx-block-identity", "rx-diagnosis-row", "rx-glasses-box", "rx-bring-list", "rx-footer"]) {
    expect(sheet.querySelector(`[data-testid="${block}"]`)).not.toBeNull();
  }
  expect(sheet.textContent).toContain("SIKAR NAGARIK PARISHAD (KOLKATA)");
  expect(sheet.textContent).toContain("SIKAR ZILLA WELFARE TRUST");
  expect(sheet.textContent).toContain("sikarkolkata@gmail.com");
  expect(sheet.textContent).toContain("Community Center");
  expect(sheet.textContent).toContain("#1001");
});

test("the sheet is one fixed A4 box whose write area gives way to long text", () => {
  const sheet = render();
  expect(sheet.style.width).toBe("210mm");
  expect(sheet.style.height).toBe("297mm");
  expect(sheet.style.overflow).toBe("hidden");
  const writeArea = sheet.querySelector('[data-testid="rx-write-area"]').className;
  expect(writeArea).toContain("flex-1");
  expect(writeArea).toContain("min-h-0");
  expect(sheet.querySelectorAll('[data-testid="rx-medicine-line"]')).toHaveLength(3);
});

test("a long name, address and venue wrap inside the sheet instead of pushing the footer off the page", () => {
  const sheet = render({
    rx: { ...RX, full_name: "N".repeat(100), address: "A".repeat(300), venue: "V".repeat(120) },
  });
  const values = [...sheet.querySelectorAll('[data-testid="rx-block-identity"] [data-testid="rx-leader-value"]')];
  expect(values).toHaveLength(4);
  for (const value of values) expect(value.className).toContain("break-words");
  for (const fixed of ["rx-glasses-box", "rx-bring-list", "rx-signature", "rx-footer"]) {
    expect(sheet.querySelector(`[data-testid="${fixed}"]`).className).toContain("shrink-0");
  }
});

test("a preview grows with its content", () => {
  const sheet = render({ preview: true });
  expect(sheet.style.height).toBe("auto");
});

test("every sponsor sits in the footer band", () => {
  const logos = Array.from({ length: 5 }, (_, i) => ({
    id: `logo-${i}`, name: `sponsor-${i}.png`, data_url: "data:image/png;base64,aaa",
  }));
  const sheet = render({ logos });
  const strip = sheet.querySelector('[data-testid="rx-sponsor-strip"]');
  expect(strip.children).toHaveLength(5);
  expect(sheet.querySelector('[data-testid="rx-footer"]').contains(strip)).toBe(true);
});

test("without logos the letterhead and footer still print", () => {
  const sheet = render({ logos: [] });
  expect(sheet.querySelector('[data-testid="rx-sponsor-strip"]').children).toHaveLength(0);
  expect(sheet.textContent).toContain("Sponsorer :");
});

test("the patient QR carries an uppercase SNP prefix and a printable quiet zone", () => {
  const sheet = render({ rx: { ...RX, patient_qr: "K7M2QX9F" } });
  // 21 modules of Version 1 plus the spec's 4-module quiet zone on each side.
  expect(sheet.querySelector("svg").getAttribute("viewBox")).toBe("0 0 29 29");
});

test("the reference form's named strings stay put", () => {
  const sheet = render({ rx: { ...RX, date: "2026-09-01" } });
  expect(sheet.textContent).toContain("ARRANGMENT");
  expect(sheet.textContent).toContain("Remaks");
  expect(sheet.textContent).toContain("PRESCRIPTION FOR GLASSES");
  expect(sheet.textContent).toContain("Inter Pupillary distance");
  expect(sheet.textContent).toContain("Sponsorer :");
  const band = sheet.querySelector('[data-testid="rx-bring-list"]');
  expect([...band.querySelectorAll("p")].map((line) => line.textContent)).toEqual([
    "केवल मोतियाबिंद (IOL) ऑपरेशन की व्यवस्था की जाती है। ऑपरेशन के दिन लाएँ: यह पर्चा, टोकन, आधार कार्ड, राशन कार्ड, मोबाइल फ़ोन।",
    "Only cataract (IOL) operations are arranged. On the day of the operation bring: this prescription, token, Aadhaar card, ration card, mobile phone.",
  ]);
  expect(sheet.textContent).not.toContain("Please carry");
  expect(sheet.textContent).toContain("01-09-2026");
  expect(sheet.textContent).not.toContain("2026-09-01");
  expect(sheet.textContent).not.toContain("Operation will be done at");
  expect(sheet.textContent).toContain("Operation will be done by");
});
