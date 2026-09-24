import { createElement, Fragment } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";

export const IMAGE_WAIT_MS = 3000;

function pageRules(pageSize) {
  return `@media screen { #print-root { display: none } }
@media print { body > :not(#print-root) { display: none !important } @page { size: ${pageSize}; margin: 0 } }`;
}

function imagesReady(host) {
  let timer;
  const decoded = Promise.all([...host.querySelectorAll("img")].map((img) => img.decode().catch(() => undefined)));
  const cap = new Promise((resolve) => { timer = setTimeout(resolve, IMAGE_WAIT_MS); });
  return Promise.race([decoded, cap]).finally(() => clearTimeout(timer));
}

export async function printDocument(element, { pageSize }) {
  document.getElementById("print-root")?.remove();
  const host = document.createElement("div");
  host.id = "print-root";
  document.body.appendChild(host);
  const root = createRoot(host);
  flushSync(() => root.render(createElement(Fragment, null, createElement("style", null, pageRules(pageSize)), element)));
  try {
    await imagesReady(host);
    await new Promise((resolve) => {
      window.addEventListener("afterprint", resolve, { once: true });
      window.print();
    });
  } finally {
    root.unmount();
    host.remove();
  }
}
