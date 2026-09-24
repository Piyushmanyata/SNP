import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { TokenSheet } from "./TokenSheet";

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

const OT_SLIP = {
  id: "tok-1",
  item_type: "ot",
  version: 2,
  collection_date: "2026-12-01",
  collection_venue: "Base Hospital",
  active: true,
  ot_eye: "R",
  bp: "140/90",
  blood_sugar: "110",
};

function renderToken(slip) {
  act(() => root.render(
    <TokenSheet slip={slip} registration={{ id: "reg-1", reg_no: 1001, full_name: "Aparna Sen" }} campName="SNP Camp Nadia" />,
  ));
  return container.querySelector('[data-testid="a6-token"]');
}

test("the Token is an A6 bilingual sheet with no QR, no buttons and no thermal slip", () => {
  const surface = renderToken(OT_SLIP);
  expect(container.firstElementChild).toBe(surface);
  expect(surface.style.width).toBe("105mm");
  expect(surface.style.height).toBe("148mm");
  expect(container.querySelector("button")).toBeNull();
  expect(surface.textContent).toContain("SNP Camp Nadia");
  expect(surface.textContent).toContain("Aparna Sen");
  expect(surface.textContent).toContain("#1001");
  expect(surface.textContent).not.toContain("Version");
  expect(surface.textContent).toContain("Base Hospital");
  expect(surface.textContent).toContain("9835317006");
  expect(surface.textContent).toContain("नाम / Name");
  expect(surface.querySelector("svg")).toBeNull();
  expect(container.innerHTML).not.toContain("58mm");
  expect(container.innerHTML).not.toContain("thermal");
});

test("an IOL surgery Token names the operation, the eye, the vitals and the Bring list with a DD-MM-YYYY date", () => {
  const surface = renderToken(OT_SLIP);
  expect(surface.textContent).toContain("मोतियाबिंद (IOL) ऑपरेशन / IOL Surgery");
  expect(surface.textContent).toContain("दायीं आँख / Right eye");
  expect(surface.textContent).toContain("140/90");
  expect(surface.textContent).toContain("110");
  expect(surface.textContent).toContain("01-12-2026");
  expect(surface.textContent).not.toContain("2026-12-01");
  expect(surface.textContent).toContain("पर्चा, यह टोकन, आधार कार्ड, राशन कार्ड, मोबाइल फ़ोन");
  expect(surface.textContent).not.toContain("वोटर");
});

test("an IOL surgery Token without recorded vitals prints no BP or blood sugar line", () => {
  const surface = renderToken({ ...OT_SLIP, ot_eye: "L", bp: null, blood_sugar: null });
  expect(surface.textContent).toContain("बायीं आँख / Left eye");
  expect(surface.textContent).not.toContain("BP");
  expect(surface.textContent).not.toContain("Blood sugar");
});

test("a Spectacles to be made Token keeps its collection line with a DD-MM-YYYY date", () => {
  const surface = renderToken({
    id: "tok-2",
    item_type: "specs_made",
    collection_date: "2026-12-05",
    collection_end_date: "2026-12-12",
    collection_venue: "Base Optical",
  });
  expect(surface.textContent).toContain("चश्मा / Spectacles");
  expect(surface.textContent).toContain("05-12-2026 – 12-12-2026");
  expect(surface.textContent).toContain("10:00 AM–5:00 PM");
  expect(surface.querySelector('[data-testid="token-superseded"]')).toBeNull();
  expect(surface.textContent).toContain("Bring this token for collection.");
  expect(surface.textContent).not.toContain("IOL");
  expect(surface.textContent).not.toContain("आधार कार्ड");
});

test("a replaced Token says it is no longer valid, and an IOL surgery Token has no collection hours", () => {
  const surface = renderToken({ ...OT_SLIP, superseded: true });
  expect(surface.querySelector('[data-testid="token-superseded"]').textContent).toContain("Replaced — not valid");
  expect(surface.querySelector('[data-testid="token-window"]')).toBeNull();
});
