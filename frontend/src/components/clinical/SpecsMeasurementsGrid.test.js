import React, { act, useState } from "react";
import ReactDOM from "react-dom/client";
import { SpecsMeasurementsGrid } from "./SpecsMeasurementsGrid";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;
let latest;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function Live() {
  const [specs, setSpecs] = useState({ r_sph: "1.25" });
  latest = specs;
  return <SpecsMeasurementsGrid specsMeasurements={specs} onChange={setSpecs} />;
}

test("SPH and CYL take text so a phone keyboard can type a minus, and a sign button flips it", () => {
  act(() => root.render(<Live />));
  for (const key of ["r_sph", "r_cyl", "l_sph", "l_cyl"]) {
    expect(container.querySelector(`[data-testid="specs-${key}"]`).inputMode).toBe("text");
  }
  expect(container.querySelector('[data-testid="specs-r_axis"]').inputMode).toBe("numeric");
  act(() => container.querySelector('[data-testid="specs-r_sph-sign"]').click());
  expect(latest.r_sph).toBe("-1.25");
  act(() => container.querySelector('[data-testid="specs-r_sph-sign"]').click());
  expect(latest.r_sph).toBe("+1.25");
  act(() => container.querySelector('[data-testid="specs-l_cyl-sign"]').click());
  expect(latest.l_cyl).toBe("-");
});
