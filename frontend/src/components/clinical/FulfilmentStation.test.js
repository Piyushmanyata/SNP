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

async function renderSection(data, otDays = [], specsDays = [], line = "medicine") {
  await act(async () => {
    root.render(
      <FulfilmentSection
        line={line}
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
  test("a line section shows only that line", async () => {
    await renderSection({ transcription: { id: "tx-1" }, registration: { id: "reg-1" }, fulfilments: [] }, [], [], "medicine");

    expect(container.querySelector('[data-testid="station-medicine"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-ot"]')).toBeNull();
    expect(container.textContent).toContain("Given");
    expect(container.textContent).toContain("Out of stock");
  });

  test("issuing specs is blocked until both eyes have a power", async () => {
    await renderStation({
      line: "specs_fixed",
      data: {
        transcription: { id: "tx-1", specs_measurements: { r_sph: "-1.00" } },
        registration: { id: "reg-1" },
        fulfilments: [],
      },
    });

    expect(container.querySelector('[data-testid="station-specs_fixed-needs-power"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-specs_fixed-save"]').disabled).toBe(true);
  });

  test("medicine does not need a prescribed power", async () => {
    await renderStation({
      line: "medicine",
      data: { transcription: { id: "tx-1" }, registration: { id: "reg-1" }, fulfilments: [] },
    });
    expect(container.querySelector('[data-testid="station-medicine-needs-power"]')).toBeNull();
    expect(container.querySelector('[data-testid="station-medicine-fulfilled"]').disabled).toBe(true);
    act(() => {
      container.querySelector('[data-testid="station-medicine-paper-review"]').click();
    });
    expect(container.querySelector('[data-testid="station-medicine-fulfilled"]').disabled).toBe(false);
  });

  test("recording Fixed-power specs posts a fulfilled specs_fixed line", async () => {
    await renderStation({
      line: "specs_fixed",
      data: { transcription: { id: "tx-9", specs_measurements: RX }, registration: { id: "r" }, fulfilments: [] },
    });

    await act(async () => {
      container.querySelector('[data-testid="station-specs_fixed-paper-review"]').click();
      container.querySelector('[data-testid="station-specs_fixed-save"]').click();
    });

    expect(api.post).toHaveBeenCalledWith(
      "/clinical/fulfilment",
      expect.objectContaining({
        transcription_id: "tx-9",
        item_type: "specs_fixed",
        status: "fulfilled",
        paper_reviewed: true,
      }),
    );
  });

  test("the specs picker shows date venue and window and omits incomplete days", async () => {
    await renderStation({
      line: "specs_made",
      data: { transcription: { id: "tx-1", specs_measurements: RX }, registration: { id: "r" }, fulfilments: [] },
      specsDays: [
        { id: "sp-legacy", day_date: "2026-09-05", venue: "Old Optical", window_required: true },
        { id: "sp-2", day_date: "2026-09-06", venue: "Optical", start_time: "09:00", end_time: "12:00" },
        { id: "sp-3", day_date: "2026-09-07", venue: "Hall B", start_time: "14:00", end_time: "16:00" },
      ],
    });

    const picker = container.querySelector('[data-testid="specs_collection_day_id-select"]');
    expect(picker.value).toBe("sp-2");
    expect(picker.textContent).toContain("09:00–12:00");
    expect(picker.textContent).toContain("Optical");
    expect(picker.textContent).not.toContain("Old Optical");
    expect(picker.textContent).not.toContain("full");
  });

  test("empty specs schedule says no day is scheduled", async () => {
    await renderStation({
      line: "specs_made",
      data: { transcription: { id: "tx-1", specs_measurements: RX }, registration: { id: "r" }, fulfilments: [] },
      specsDays: [],
    });
    expect(container.querySelector('[data-testid="specs_collection_day_id-none-free"]').textContent)
      .toContain("No day is scheduled");
  });

  test("every clinical day full names the admin action and blocks saving", async () => {
    await renderStation({
      line: "ot",
      data: { transcription: { id: "tx-1" }, registration: { id: "r" }, fulfilments: [] },
      otDays: [{ id: "ot-1", day_date: "2026-10-02", venue: "OT Theatre", seats_free: 0 }],
    });

    expect(container.querySelector('[data-testid="ot_schedule_day_id-none-free"]').textContent)
      .toContain("Call the admin");
    expect(container.querySelector('[data-testid="station-ot-save"]').disabled).toBe(true);
  });

  test("surgery can only be scheduled at the hospital and prints its token", async () => {
    const navigate = jest.fn();
    api.post.mockResolvedValueOnce({ data: { slip: { id: "hospital-token" } } });
    await renderStation({
      line: "ot",
      data: { transcription: { id: "tx-1" }, registration: { id: "r" }, fulfilments: [] },
      otDays: [{ id: "ot-1", day_date: "2026-10-02", venue: "Bajaj Hospital", seats_free: 5 }],
      navigate,
    });
    expect(container.textContent).not.toContain("Done at camp");
    expect(container.textContent).toContain("hospital");
    await act(async () => {
      container.querySelector('[data-testid="station-ot-paper-review"]').click();
      container.querySelector('[data-testid="station-ot-save"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
      item_type: "ot", status: "deferred", ot_schedule_day_id: "ot-1",
    }));
    expect(navigate).toHaveBeenCalledWith("/print/slip/hospital-token");
  });

  test("a deferred specs_made record shows a reprint control", async () => {
    await renderStation({
      line: "specs_made",
      data: {
        transcription: { id: "tx-1", specs_measurements: RX },
        registration: { id: "reg-1" },
        fulfilments: [{ item_type: "specs_made", status: "deferred", specs_collection_day_id: "sp-2" }],
        slips: [{ id: "slip-1", item_type: "specs_made", active: true }],
      },
      specsDays: [{ id: "sp-2", day_date: "2026-09-06", venue: "Optical", start_time: "09:00", end_time: "12:00" }],
    });

    expect(container.querySelector('[data-testid="station-specs_made-print-token"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-specs_made-save"]')).toBeNull();
  });

  test("a failed issue retry reuses the same operation id", async () => {
    const uuid = jest.spyOn(crypto, "randomUUID").mockReturnValue("op-retry-1");
    api.post.mockRejectedValueOnce(new Error("network"));
    api.post.mockResolvedValueOnce({ data: { fulfilment: { id: "f-1" }, slip: null } });
    await renderStation({
      line: "medicine",
      data: {
        transcription: { id: "tx-1" },
        registration: { id: "r" },
        committed_revision: { id: "rev-1" },
        clinical_generation: 1,
        fulfilments: [],
      },
      setError: jest.fn(),
    });
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-paper-review"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-fulfilled"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-fulfilled"]').click();
    });
    const ids = api.post.mock.calls.map((call) => call[1].operation_id);
    expect(ids).toEqual(["op-retry-1", "op-retry-1"]);
    uuid.mockRestore();
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
    expect(container.querySelector('[data-testid="station-medicine-recorded"]')).not.toBeNull();

    await renderStation({
      line: "medicine",
      data: {
        transcription: { id: "tx-2" }, registration: { id: "reg-2" },
        fulfilments: [{ item_type: "medicine", status: "not_available" }],
      },
    });
    expect(container.querySelector('[data-testid="station-medicine-recorded"]').textContent).toContain("not available");
  });
});
