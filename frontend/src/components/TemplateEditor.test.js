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
    if (url.startsWith("/templates?camp_id=")) {
      return Promise.resolve({
        data: {
          draft: {
            header_title: "SNP Free Eye Camp",
            header_subtitle: "Rotary Club Venue",
            footer_note: "Bring this prescription for follow-up.",
            blocks: [
              { id: "identity", type: "identity", label: "Identity", visible: true },
              { id: "diagnosis", type: "lines", label: "Diagnosis", height: 24, visible: true },
              { id: "prescription", type: "lines", label: "Prescription", height: 48, visible: true },
              { id: "signature", type: "signature", label: "Doctor's Signature", visible: true },
            ],
            logos: [
              { id: "logo-1", name: "sponsor_logo.png", data_url: "data:image/png;base64,fake", order: 0 },
            ],
          },
          published: { version: 1 },
        },
      });
    }
    return Promise.resolve({ data: {} });
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
});

describe("TemplateEditor component", () => {
  test("loads active camp template draft and renders editor with A4 preview", async () => {
    await act(async () => {
      root.render(<TemplateEditor />);
    });

    expect(api.get).toHaveBeenCalledWith("/camps");
    expect(api.get).toHaveBeenCalledWith("/templates?camp_id=camp-1");

    const campSelect = container.querySelector('[data-testid="tpl-camp-select"]');
    expect(campSelect).not.toBeNull();
    expect(campSelect.value).toBe("camp-1");

    const titleInput = container.querySelector('[data-testid="tpl-title-input"]');
    const subtitleInput = container.querySelector('[data-testid="tpl-subtitle-input"]');
    const footerInput = container.querySelector('[data-testid="tpl-footer-input"]');

    expect(titleInput.value).toBe("SNP Free Eye Camp");
    expect(subtitleInput.value).toBe("Rotary Club Venue");
    expect(footerInput.value).toBe("Bring this prescription for follow-up.");

    // Check preview
    const preview = container.querySelector('[data-testid="tpl-preview"]');
    expect(preview).not.toBeNull();
    expect(preview.textContent).toContain("Sample Patient");
  });

  test("edits letterhead text fields and updates live draft", async () => {
    await act(async () => {
      root.render(<TemplateEditor />);
    });

    const titleInput = container.querySelector('[data-testid="tpl-title-input"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(titleInput, "Updated Clinic Name");
      titleInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(titleInput.value).toBe("Updated Clinic Name");

    // Preview reflects change
    const preview = container.querySelector('[data-testid="tpl-preview"]');
    expect(preview.textContent).toContain("Updated Clinic Name");
  });

  test("toggles block visibility, updates height, and reorders blocks", async () => {
    await act(async () => {
      root.render(<TemplateEditor />);
    });

    const diagVisible = container.querySelector('[data-testid="tpl-block-visible-diagnosis"]');
    expect(diagVisible.checked).toBe(true);

    act(() => {
      diagVisible.click();
    });
    expect(diagVisible.checked).toBe(false);

    // Update height
    const diagHeight = container.querySelector('[data-testid="tpl-block-height-diagnosis"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(diagHeight, "35");
      diagHeight.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(diagHeight.value).toBe("35");

    // Move diagnosis down
    const moveDownBtn = container.querySelector('[data-testid="tpl-block-down-diagnosis"]');
    act(() => {
      moveDownBtn.click();
    });
  });

  test("removes sponsor logo from draft", async () => {
    await act(async () => {
      root.render(<TemplateEditor />);
    });

    const logoList = container.querySelector('[data-testid="tpl-logos-list"]');
    expect(logoList).not.toBeNull();
    expect(logoList.textContent).toContain("sponsor_logo.png");

    const removeLogoBtn = container.querySelector('[data-testid="tpl-remove-logo-0"]');
    act(() => {
      removeLogoBtn.click();
    });

    expect(container.querySelector('[data-testid="tpl-logos-list"]')).toBeNull();
  });

  test("saves draft template successfully", async () => {
    api.post.mockResolvedValueOnce({ data: { message: "Draft saved" } });

    await act(async () => {
      root.render(<TemplateEditor />);
    });

    const saveDraftBtn = container.querySelector('[data-testid="tpl-save-draft-button"]');
    await act(async () => {
      saveDraftBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith(
      "/templates/draft",
      expect.objectContaining({
        camp_id: "camp-1",
        header_title: "SNP Free Eye Camp",
      })
    );
    expect(container.textContent).toContain("Draft saved.");
  });

  test("publishes template and increments version badge", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/templates/draft") return Promise.resolve({ data: {} });
      if (url === "/templates/publish") {
        return Promise.resolve({
          data: { published: { version: 2 } },
        });
      }
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      root.render(<TemplateEditor />);
    });

    const publishBtn = container.querySelector('[data-testid="tpl-publish-button"]');
    await act(async () => {
      publishBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith("/templates/publish", { camp_id: "camp-1" });
    expect(container.textContent).toContain("Published v2.");
  });

  test("restores defaults when restore button clicked", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        draft: {
          header_title: "Default Header",
          header_subtitle: "Default Subtitle",
          footer_note: "Default Note",
          blocks: [
            { id: "identity", type: "identity", label: "Identity", visible: true },
          ],
          logos: [],
        },
      },
    });

    await act(async () => {
      root.render(<TemplateEditor />);
    });

    const restoreBtn = container.querySelector('[data-testid="tpl-restore-button"]');
    await act(async () => {
      restoreBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith("/templates/restore-defaults", { camp_id: "camp-1" });
    expect(container.textContent).toContain("Restored defaults.");
  });
});
