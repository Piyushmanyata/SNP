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
const MEDICINE = { medicine_id: "med-1", name: "Moxifloxacin" };
const POWERS = [
  { id: "p1", value: -1.5, label: "-1.50", active: true },
  { id: "p2", value: 2, label: "+2.00", active: true },
  { id: "p3", value: 2.25, label: "+2.25", active: true },
];
const FIXED = { fixed_power_r: 2, fixed_power_l: 2 };

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
    await renderSection({
      transcription: { id: "tx-1", prescribed_medicines: [MEDICINE] },
      registration: { id: "reg-1" },
      fulfilments: [],
    }, [], [], "medicine");

    expect(container.querySelector('[data-testid="station-medicine"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-ot"]')).toBeNull();
    expect(container.textContent).toContain("Moxifloxacin");
    expect(container.textContent).toContain("Given");
    expect(container.textContent).toContain("Not available");
  });

  test("each prescribed medicine carries its own outcome and the server derives the status", async () => {
    await renderStation({
      line: "medicine",
      powers: POWERS,
      data: {
        transcription: {
          id: "tx-1",
          prescribed_medicines: [MEDICINE, { medicine_id: "med-2", name: "Timolol" }],
        },
        registration: { id: "reg-1" },
        fulfilments: [],
      },
    });

    await act(async () => {
      container.querySelector('[data-testid="medicine-med-2-missing"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-paper-review"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-save"]').click();
    });

    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
      item_type: "medicine",
      medicine_outcomes: [
        { medicine_id: "med-1", given: true },
        { medicine_id: "med-2", given: false },
      ],
    }));
  });

  test("a power that ran out can be substituted and both powers are sent", async () => {
    await renderStation({
      line: "specs_fixed",
      powers: POWERS,
      data: {
        transcription: { id: "tx-1", ...FIXED },
        registration: { id: "reg-1" },
        fulfilments: [],
      },
    });

    await act(async () => {
      container.querySelector('[data-testid="fixed-power-both-2.25"]').click();
    });
    expect(container.querySelector('[data-testid="power-substituted"]')).not.toBeNull();
    await act(async () => {
      container.querySelector('[data-testid="station-specs_fixed-paper-review"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-specs_fixed-save"]').click();
    });

    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
      item_type: "specs_fixed",
      issued_power_r: 2.25,
      issued_power_l: 2.25,
    }));
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
    expect(container.querySelector('[data-testid="station-medicine-save"]').disabled).toBe(true);
    act(() => {
      container.querySelector('[data-testid="station-medicine-paper-review"]').click();
    });
    expect(container.querySelector('[data-testid="station-medicine-save"]').disabled).toBe(false);
  });

  test("recording Fixed-power specs posts a fulfilled specs_fixed line", async () => {
    await renderStation({
      line: "specs_fixed",
      powers: POWERS,
      data: { transcription: { id: "tx-9", ...FIXED }, registration: { id: "r" }, fulfilments: [] },
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

  test("a prescription with different powers per eye opens split and never fuses the two", async () => {
    await renderStation({
      line: "specs_fixed",
      powers: POWERS,
      data: {
        transcription: { id: "tx-1", fixed_power_r: -1.5, fixed_power_l: 2 },
        registration: { id: "reg-1" },
        fulfilments: [],
      },
    });

    expect(container.querySelector('[data-testid="fixed-power-split"]').checked).toBe(true);
    expect(container.querySelector('[data-testid="fixed-power-both--1.5"]')).toBeNull();

    await act(async () => {
      container.querySelector('[data-testid="fixed-power-r-2.25"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-specs_fixed-paper-review"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-specs_fixed-save"]').click();
    });

    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
      issued_power_r: 2.25,
      issued_power_l: 2,
    }));
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
      container.querySelector('[data-testid="station-medicine-save"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-save"]').click();
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
