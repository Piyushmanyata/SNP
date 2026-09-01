import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { FulfilmentStation } from "./FulfilmentStation";
import { FulfilmentSection } from "./FulfilmentSection";
import api from "../../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    __esModule: true,
    default: {
      post: jest.fn(),
      get: jest.fn(),
    },
    formatApiError: actual.formatApiError,
  };
});

const RX = { r_sph: "-1.00", l_sph: "-1.25", add: "+2.00" };

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  api.post.mockResolvedValue({ data: { fulfilment: { id: "f-1" }, slip: null } });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
});

async function renderStation(props) {
  await act(async () => {
    root.render(
      <FulfilmentStation
        onDone={jest.fn()}
        navigate={jest.fn()}
        setBanner={jest.fn()}
        setError={jest.fn()}
        {...props}
      />
    );
  });
}

async function renderSection(data, otDays = [], specsDays = []) {
  await act(async () => {
    root.render(
      <FulfilmentSection
        data={data}
        otDays={otDays}
        specsDays={specsDays}
        onDone={jest.fn()}
        navigate={jest.fn()}
        setBanner={jest.fn()}
        setError={jest.fn()}
      />
    );
  });
}

describe("Fulfilment lines", () => {
  test("the screen shows the four physical desks", async () => {
    await renderSection({ transcription: { id: "tx-1" }, registration: { id: "reg-1" }, fulfilments: [] });

    for (const line of ["medicine", "specs_fixed", "specs_made", "ot"]) {
      expect(container.querySelector(`[data-testid="station-${line}"]`)).not.toBeNull();
    }
    expect(container.textContent).toContain("Fixed-power specs");
    expect(container.textContent).toContain("Spectacles to be made");
  });

  test("a specs line cannot be recorded until both eyes have a power", async () => {
    await renderSection({
      transcription: { id: "tx-1", specs_measurements: { r_sph: "-1.00" } },
      registration: { id: "reg-1" },
      fulfilments: [],
    });

    expect(container.querySelector('[data-testid="station-specs_fixed-needs-power"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-specs_fixed-save"]').disabled).toBe(true);
    expect(container.querySelector('[data-testid="station-specs_made-save"]').disabled).toBe(true);
    expect(container.querySelector('[data-testid="station-medicine-save"]').disabled).toBe(true);
    expect(container.querySelector('[data-testid="station-medicine-needs-power"]')).toBeNull();
  });

  test("recording Fixed-power specs posts a fulfilled specs line", async () => {
    await renderStation({
      line: "specs_fixed",
      data: { transcription: { id: "tx-9", specs_measurements: RX }, registration: { id: "r" }, fulfilments: [] },
    });

    const save = container.querySelector('[data-testid="station-specs_fixed-save"]');
    expect(save.disabled).toBe(true);

    const status = container.querySelector('[data-testid="station-specs_fixed-status"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
      setter.call(status, "fulfilled");
      status.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector('[data-testid="station-specs_fixed-save"]').click();
    });

    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", {
      transcription_id: "tx-9",
      item_type: "specs",
      status: "fulfilled",
      ot_schedule_day_id: null,
      specs_collection_day_id: null,
    });
  });

  test("the day picker pre-selects the earliest free day and disables full ones", async () => {
    await renderStation({
      line: "specs_made",
      data: { transcription: { id: "tx-1", specs_measurements: RX }, registration: { id: "r" }, fulfilments: [] },
      specsDays: [
        { id: "sp-1", day_date: "2026-09-05", venue: "Optical", seats_free: 0 },
        { id: "sp-2", day_date: "2026-09-06", venue: "Optical", seats_free: 4 },
        { id: "sp-3", day_date: "2026-09-07", venue: "Optical", seats_free: 9 },
      ],
    });

    const picker = container.querySelector('[data-testid="specs_collection_day_id-select"]');
    expect(picker.value).toBe("sp-2");
    const options = [...picker.querySelectorAll("option")];
    expect(options.find((o) => o.value === "sp-1").disabled).toBe(true);
    expect(options.find((o) => o.value === "sp-1").textContent).toContain("full");
    expect(options.find((o) => o.value === "sp-3").disabled).toBe(false);
  });

  test("every clinical day full names the admin action and blocks saving", async () => {
    await renderStation({
      line: "ot",
      data: { transcription: { id: "tx-1" }, registration: { id: "r" }, fulfilments: [] },
      otDays: [{ id: "ot-1", day_date: "2026-10-02", venue: "OT Theatre", seats_free: 0 }],
    });

    const status = container.querySelector('[data-testid="station-ot-status"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
      setter.call(status, "deferred");
      status.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(container.querySelector('[data-testid="ot_schedule_day_id-none-free"]').textContent)
      .toContain("Call the admin");
    expect(container.querySelector('[data-testid="station-ot-save"]').disabled).toBe(true);
  });

  test("a deferred specs record shows on the Spectacles-to-be-made line, not the Fixed-power line", async () => {
    await renderSection({
      transcription: { id: "tx-1", specs_measurements: RX },
      registration: { id: "reg-1" },
      fulfilments: [{ item_type: "specs", status: "deferred", specs_collection_day_id: "sp-2" }],
      slips: [{ id: "slip-1", item_type: "specs", active: true }],
    }, [], [{ id: "sp-2", day_date: "2026-09-06", venue: "Optical", seats_free: 4 }]);

    expect(container.querySelector('[data-testid="station-specs_made-print-token"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-specs_fixed-print-token"]')).toBeNull();
    expect(container.querySelector('[data-testid="station-specs_fixed-status"]').value).toBe("");
  });

  test("a station re-syncs when the patient changes", async () => {
    const props = {
      line: "medicine",
      data: {
        transcription: { id: "tx-1" }, registration: { id: "reg-1" },
        fulfilments: [{ item_type: "medicine", status: "fulfilled" }],
      },
    };
    await renderStation(props);
    expect(container.querySelector('[data-testid="station-medicine-status"]').value).toBe("fulfilled");

    await renderStation({
      line: "medicine",
      data: {
        transcription: { id: "tx-2" }, registration: { id: "reg-2" },
        fulfilments: [{ item_type: "medicine", status: "not_available" }],
      },
    });
    expect(container.querySelector('[data-testid="station-medicine-status"]').value).toBe("not_available");
  });
});
