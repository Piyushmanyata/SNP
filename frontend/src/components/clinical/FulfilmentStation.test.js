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

let printedText = [];

beforeEach(() => {
  printedText = [];
  window.print = jest.fn(() => {
    printedText.push(document.getElementById("print-root")?.textContent);
    window.dispatchEvent(new Event("afterprint"));
  });
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
        setBanner={jest.fn()}
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
        setBanner={jest.fn()}
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

  test("the specs picker shows each day's dates, venue and the fixed hours", async () => {
    await renderStation({
      line: "specs_made",
      data: { transcription: { id: "tx-1", specs_measurements: RX }, registration: { id: "r" }, fulfilments: [] },
      specsDays: [
        { id: "sp-2", day_date: "2026-09-06", end_date: "2026-09-06", venue: "Optical" },
        { id: "sp-3", day_date: "2026-09-07", end_date: "2026-09-14", venue: "Hall B" },
      ],
    });

    const picker = container.querySelector('[data-testid="specs_collection_day_id-select"]');
    expect(picker.value).toBe("sp-2");
    expect(picker.textContent).toContain("06-09-2026 · Optical · 10:00 AM–5:00 PM");
    expect(picker.textContent).toContain("07-09-2026 – 14-09-2026 · Hall B · 10:00 AM–5:00 PM");
    expect(picker.textContent).not.toContain("2026-09-06");
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

  test("a prescribed IOL surgery is scheduled with a Token printed on the spot", async () => {
    const onDone = jest.fn();
    api.post.mockResolvedValueOnce({ data: { slip: { id: "hospital-token" } } });
    api.get.mockResolvedValueOnce({ data: {
      slip: { id: "hospital-token", item_type: "ot", ot_eye: "R", collection_date: "2026-10-02", collection_venue: "Bajaj Hospital" },
      registration: { id: "r", reg_no: 101, full_name: "Aparna Sen" },
      camp_name: "SNP Camp Nadia",
    } });
    await renderStation({
      line: "ot",
      data: {
        transcription: { id: "tx-1" },
        committed_revision: { id: "rev-1", ot_outcome: "iol_surgery", ot_eye: "R" },
        registration: { id: "r" },
        fulfilments: [],
      },
      otDays: [{ id: "ot-1", day_date: "2026-10-02", venue: "Bajaj Hospital", seats_free: 5 }],
      onDone,
    });
    expect(container.textContent).not.toContain("Done at camp");
    const picker = container.querySelector('[data-testid="ot_schedule_day_id-select"]');
    expect(picker.textContent).toContain("02-10-2026 · Bajaj Hospital");
    expect(picker.textContent).not.toContain("2026-10-02");
    expect(container.querySelector('[data-testid="station-ot-save"]').textContent).toBe("Schedule and print token");
    expect(container.querySelector('[data-testid="station-ot-declined"]').textContent).toBe("Patient declined");
    await act(async () => {
      container.querySelector('[data-testid="station-ot-paper-review"]').click();
      container.querySelector('[data-testid="station-ot-save"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
      item_type: "ot", status: "deferred", ot_schedule_day_id: "ot-1",
    }));
    expect(api.get).toHaveBeenCalledWith("/clinical/slip/hospital-token");
    expect(window.print).toHaveBeenCalledTimes(1);
    expect(printedText[0]).toContain("Aparna Sen");
    expect(printedText[0]).toContain("Bajaj Hospital");
    expect(onDone).toHaveBeenCalled();
  });

  test("Patient declined records the refusal with no day and prints nothing", async () => {
    const onDone = jest.fn();
    const setBanner = jest.fn();
    await renderStation({
      line: "ot",
      data: {
        transcription: { id: "tx-1" },
        committed_revision: { id: "rev-1", ot_outcome: "iol_surgery", ot_eye: "L" },
        registration: { id: "r" },
        fulfilments: [],
      },
      otDays: [{ id: "ot-1", day_date: "2026-10-02", venue: "Bajaj Hospital", seats_free: 0 }],
      onDone,
      setBanner,
    });
    const declined = () => container.querySelector('[data-testid="station-ot-declined"]');
    expect(declined().disabled).toBe(true);
    await act(async () => container.querySelector('[data-testid="station-ot-paper-review"]').click());
    expect(declined().disabled).toBe(false);
    await act(async () => declined().click());
    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
      item_type: "ot", status: "declined", ot_schedule_day_id: null, paper_reviewed: true,
    }));
    expect(window.print).not.toHaveBeenCalled();
    expect(onDone).toHaveBeenCalled();
    expect(setBanner).toHaveBeenCalledWith("Hospital: Surgery declined");
  });

  test("a Hospital referral offers nothing to record at the station", async () => {
    await renderStation({
      line: "ot",
      data: {
        transcription: { id: "tx-1" },
        committed_revision: { id: "rev-1", ot_outcome: "referral" },
        registration: { id: "r" },
        fulfilments: [],
      },
      otDays: [{ id: "ot-1", day_date: "2026-10-02", venue: "Bajaj Hospital", seats_free: 5 }],
    });
    expect(container.querySelector('[data-testid="station-ot-referral"]').textContent)
      .toContain("Hospital referral");
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector("select")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
  });

  test("a scheduled IOL surgery can still be recorded as declined", async () => {
    await renderStation({
      line: "ot",
      data: {
        transcription: { id: "tx-1" },
        committed_revision: { id: "rev-1", ot_outcome: "iol_surgery", ot_eye: "R" },
        registration: { id: "r" },
        fulfilments: [{ item_type: "ot", status: "deferred", ot_schedule_day_id: "ot-1" }],
        slips: [{ id: "slip-ot", item_type: "ot", active: true }],
      },
      otDays: [{ id: "ot-1", day_date: "2026-10-02", venue: "Bajaj Hospital", seats_free: 5 }],
    });
    expect(container.querySelector('[data-testid="station-ot-recorded"]').textContent).toBe("IOL surgery scheduled");
    expect(container.querySelector('[data-testid="station-ot-print-token"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-ot-save"]')).toBeNull();
    const declined = () => container.querySelector('[data-testid="station-ot-declined"]');
    expect(declined().disabled).toBe(true);
    await act(async () => container.querySelector('[data-testid="station-ot-paper-review"]').click());
    await act(async () => declined().click());
    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
      item_type: "ot", status: "declined", ot_schedule_day_id: null,
    }));
  });

  test("a declined surgery shows Surgery declined and offers nothing more", async () => {
    await renderStation({
      line: "ot",
      data: {
        transcription: { id: "tx-1" },
        committed_revision: { id: "rev-1", ot_outcome: "iol_surgery", ot_eye: "R" },
        registration: { id: "r" },
        fulfilments: [{ item_type: "ot", status: "declined" }],
      },
    });
    expect(container.querySelector('[data-testid="station-ot-recorded"]').textContent).toBe("Surgery declined");
    expect(container.querySelector("button")).toBeNull();
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
      specsDays: [{ id: "sp-2", day_date: "2026-09-06", venue: "Optical", start_time: "10:00", end_time: "17:00" }],
    });

    expect(container.querySelector('[data-testid="station-specs_made-print-token"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-specs_made-save"]')).toBeNull();
    expect(container.querySelector('[data-testid="station-specs_made-token-replaced"]')).toBeNull();
  });

  test("a Token replaced by a schedule change tells the desk to print the new one", async () => {
    await renderStation({
      line: "ot",
      data: {
        transcription: { id: "tx-1" },
        registration: { id: "reg-1" },
        fulfilments: [{ item_type: "ot", status: "deferred", ot_schedule_day_id: "ot-1" }],
        slips: [{ id: "slip-2", item_type: "ot", active: true, replaces: "slip-1" }],
      },
      otDays: [{ id: "ot-1", day_date: "2026-10-02", venue: "OT Theatre", seats_free: 3 }],
    });

    expect(container.querySelector('[data-testid="station-ot-token-replaced"]').textContent)
      .toContain("Print this new Token and take back the old one");
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
    });
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-paper-review"]').click();
    });
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-save"]').click();
    });
    expect(container.querySelector('[data-testid="station-medicine"] [role="alert"]').textContent).toContain("network");
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-save"]').click();
    });
    expect(container.querySelector('[role="alert"]')).toBeNull();
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

test("a Spectacles to be made order can be cancelled at its station", async () => {
  api.post.mockResolvedValueOnce({ data: { fulfilment: { id: "f-9", status: "cancelled" }, slip: null } });
  const onDone = jest.fn();
  await renderStation({
    line: "specs_made",
    data: {
      transcription: { id: "tx-1", specs_measurements: { r_sph: "-1.00", l_sph: "-1.00" } },
      committed_revision: { id: "rev-1" },
      clinical_generation: 1,
      registration: { id: "r" },
      fulfilments: [{ id: "f-9", item_type: "specs_made", status: "deferred", specs_collection_day_id: "sp-1" }],
      slips: [{ id: "slip-1", item_type: "specs_made", active: true }],
    },
    onDone,
  });
  const cancel = container.querySelector('[data-testid="station-specs_made-cancelled"]');
  expect(cancel.textContent).toBe("Cancel spectacles order");
  expect(cancel.disabled).toBe(true);
  await act(async () => container.querySelector('[data-testid="station-specs_made-paper-review"]').click());
  await act(async () => cancel.click());
  expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
    item_type: "specs_made", status: "cancelled", specs_collection_day_id: null,
  }));
  expect(onDone).toHaveBeenCalled();
});
