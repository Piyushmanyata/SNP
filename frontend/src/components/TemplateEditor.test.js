import React, { act } from "react";
import ReactDOM from "react-dom/client";
import TemplateEditor from "./TemplateEditor";
import api from "../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../lib/api", () => {
  const actual = jest.requireActual("../lib/api");
  return {
    __esModule: true,
    default: {
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      delete: jest.fn(),
    },
    formatApiError: actual.formatApiError,
    errorPayload: actual.errorPayload,
  };
});

const LOGO = { id: "logo-1", name: "sponsor_logo.png", data_url: "data:image/png;base64,fake", order: 0 };

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();

  api.get.mockImplementation((url) => {
    if (url === "/camps") {
      return Promise.resolve({
        data: {
          camps: [
            { id: "camp-1", name: "Kolkata Eye Camp", venue: "Rotary Club", is_active: true },
            { id: "camp-2", name: "Howrah Eye Camp", venue: "Town Hall", is_active: false },
          ],
        },
      });
    }
    if (url.startsWith("/templates/logos")) {
      return Promise.resolve({ data: { logos: [LOGO] } });
    }
    return Promise.resolve({ data: {} });
  });
  api.put.mockResolvedValue({ data: { logos: [LOGO] } });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
});

async function render() {
  await act(async () => {
    root.render(<TemplateEditor />);
  });
}

describe("TemplateEditor", () => {
  test("camp switches hide stale logos and ignore old camp responses", async () => {
    const originalGet = api.get.getMockImplementation();
    let resolveFirst;
    let resolveSecond;
    api.get.mockImplementation((url) => {
      if (url === "/templates/logos?camp_id=camp-1") return new Promise((resolve) => { resolveFirst = resolve; });
      if (url === "/templates/logos?camp_id=camp-2") return new Promise((resolve) => { resolveSecond = resolve; });
      return originalGet(url);
    });
    await render();
    await act(async () => {
      const select = container.querySelector('[data-testid="tpl-camp-select"]');
      select.value = "camp-2";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => resolveSecond({ data: { logos: [{ ...LOGO, name: "Current camp logo" }] } }));
    await act(async () => resolveFirst({ data: { logos: [LOGO] } }));
    expect(container.textContent).toContain("Current camp logo");
    expect(container.textContent).not.toContain("sponsor_logo.png");
    await act(async () => {
      const select = container.querySelector('[data-testid="tpl-camp-select"]');
      select.value = "camp-1";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.querySelector('[data-testid="tpl-save-logos-button"]')).toBeNull();
    await act(async () => resolveFirst({ data: { logos: [LOGO] } }));
  });

  test("loads the active camp's sponsor logos", async () => {
    await render();
    expect(api.get).toHaveBeenCalledWith("/camps");
    expect(api.get).toHaveBeenCalledWith("/templates/logos?camp_id=camp-1");
    expect(container.querySelector('[data-testid="tpl-logos-list"]')).not.toBeNull();
    expect(container.textContent).toContain("sponsor_logo.png");
  });

  test("offers no way to edit the header, subtitle, footer or layout", async () => {
    await render();
    expect(container.querySelector('[data-testid="tpl-header-title-input"]')).toBeNull();
    expect(container.querySelector('[data-testid="tpl-header-subtitle-input"]')).toBeNull();
    expect(container.querySelector('[data-testid="tpl-footer-input"]')).toBeNull();
    expect(container.querySelector('[data-testid="tpl-blocks-editor"]')).toBeNull();
    expect(container.querySelector('[data-testid="tpl-publish-button"]')).toBeNull();
    expect(container.querySelector('[data-testid="tpl-restore-defaults-button"]')).toBeNull();
    expect(container.querySelector('[data-testid="tpl-locked-note"]')).not.toBeNull();
  });

  test("saving logos writes the live record with no publish step", async () => {
    await render();
    await act(async () => {
      container.querySelector('[data-testid="tpl-save-logos-button"]').click();
    });
    expect(api.put).toHaveBeenCalledWith("/templates/logos", {
      camp_id: "camp-1",
      logos: [{ ...LOGO, order: 0 }],
    });
    expect(container.textContent).toContain("live");
    expect(api.post).not.toHaveBeenCalled();
  });

  test("shows the A4 preview of the fixed prescription", async () => {
    await render();
    const preview = container.querySelector('[data-testid="tpl-preview"]');
    expect(preview).not.toBeNull();
    expect(preview.textContent).toContain("SIKAR NAGARIK PARISHAD (KOLKATA)");
    expect(preview.textContent).toContain("Sponsorer :");
  });

  test("the editor states the server's limits and stops adding at six logos", async () => {
    const six = Array.from({ length: 6 }, (_, i) => ({ ...LOGO, id: `logo-${i}`, order: i }));
    api.get.mockImplementation((url) => (url === "/camps"
      ? Promise.resolve({ data: { camps: [{ id: "camp-1", name: "Kolkata Eye Camp", venue: "Rotary Club", is_active: true }] } })
      : Promise.resolve({ data: { logos: six } })));
    await act(async () => { root.render(<TemplateEditor />); });
    const limits = container.querySelector('[data-testid="tpl-logo-limits"]').textContent;
    expect(limits).toContain("Up to 6 logos");
    expect(limits).toContain("2 MB");
    expect(limits).toContain("600 px");
    expect(container.querySelector('[data-testid="tpl-logo-input"]').disabled).toBe(true);
    expect(container.textContent).toContain("6 of 6");
  });

  test("surfaces a save failure", async () => {
    api.put.mockRejectedValueOnce({ response: { data: { detail: "Each logo must be 2 MB or smaller." } } });
    await render();
    await act(async () => {
      container.querySelector('[data-testid="tpl-save-logos-button"]').click();
    });
    expect(container.textContent).toContain("Each logo must be 2 MB or smaller.");
  });
});
