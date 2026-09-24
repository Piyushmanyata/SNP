import React, { act } from "react";
import { printDocument, IMAGE_WAIT_MS } from "./printJob";

global.IS_REACT_ACT_ENVIRONMENT = true;

const decode = jest.fn(() => Promise.resolve());
let seenAtPrint = null;

beforeEach(() => {
  window.HTMLImageElement.prototype.decode = decode;
  seenAtPrint = null;
  window.print = jest.fn(() => {
    const host = document.getElementById("print-root");
    seenAtPrint = { text: host?.textContent, style: host?.querySelector("style")?.textContent, parent: host?.parentNode };
    window.dispatchEvent(new Event("afterprint"));
  });
});

afterEach(() => {
  jest.useRealTimers();
  document.getElementById("print-root")?.remove();
});

test("the document prints alone on the page size asked for, then leaves", async () => {
  await act(async () => {
    await printDocument(<p>Token for Aparna</p>, { pageSize: "A6" });
  });
  expect(window.print).toHaveBeenCalledTimes(1);
  expect(seenAtPrint.parent).toBe(document.body);
  expect(seenAtPrint.text).toContain("Token for Aparna");
  expect(seenAtPrint.style).toContain("@page { size: A6; margin: 0 }");
  expect(seenAtPrint.style).toContain("body > :not(#print-root) { display: none !important }");
  expect(document.getElementById("print-root")).toBeNull();
});

test("printing waits for every image to decode", async () => {
  let finish;
  decode.mockImplementationOnce(() => new Promise((done) => { finish = done; }));
  let printed;
  await act(async () => {
    printed = printDocument(<img alt="" src="data:image/png;base64,AAAA" />, { pageSize: "A4" });
  });
  expect(window.print).not.toHaveBeenCalled();
  await act(async () => { finish(); await printed; });
  expect(window.print).toHaveBeenCalledTimes(1);
});

test("a logo that never decodes still prints after 3 seconds", async () => {
  jest.useFakeTimers();
  decode.mockImplementationOnce(() => new Promise(() => {}));
  let printed;
  await act(async () => {
    printed = printDocument(<img alt="" src="data:image/png;base64,AAAA" />, { pageSize: "A4" });
  });
  await act(async () => { jest.advanceTimersByTime(IMAGE_WAIT_MS - 1); });
  expect(window.print).not.toHaveBeenCalled();
  await act(async () => { jest.advanceTimersByTime(1); await printed; });
  expect(IMAGE_WAIT_MS).toBe(3000);
  expect(window.print).toHaveBeenCalledTimes(1);
});

test("the job finishes only when the browser says printing is over", async () => {
  window.print = jest.fn();
  let done = false;
  await act(async () => {
    printDocument(<p>Sheet</p>, { pageSize: "A4" }).then(() => { done = true; });
  });
  expect(window.print).toHaveBeenCalledTimes(1);
  expect(done).toBe(false);
  await act(async () => { window.dispatchEvent(new Event("afterprint")); });
  expect(done).toBe(true);
});
