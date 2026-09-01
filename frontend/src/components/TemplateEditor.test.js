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
    expect(preview.textContent).toContain("Sikar Nagarik Parishad");
    expect(preview.textContent).toContain("Rupa Foundation");
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
