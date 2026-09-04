import { readRoster, writeRoster, clearRoster, needsRoster, ROSTER_STORAGE_KEY } from "./roster";
import api from "./api";

describe("roster helper", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  test("read write clear round-trip", () => {
    expect(readRoster()).toBeNull();
    writeRoster({ id: "r-1", name: "Anita" });
    expect(readRoster()).toEqual({ id: "r-1", name: "Anita" });
    expect(JSON.parse(sessionStorage.getItem(ROSTER_STORAGE_KEY))).toEqual({
      id: "r-1",
      name: "Anita",
    });
    clearRoster();
    expect(readRoster()).toBeNull();
  });

  test("needsRoster is true only for desk roles", () => {
    expect(needsRoster({ role: "volunteer" })).toBe(true);
    expect(needsRoster({ role: "clinical_desk_operator" })).toBe(true);
    expect(needsRoster({ role: "admin" })).toBe(false);
    expect(needsRoster({ role: "team_lead" })).toBe(false);
    expect(needsRoster(null)).toBe(false);
  });

  test("api interceptor sets X-Roster-Id from sessionStorage", () => {
    writeRoster({ id: "r-9", name: "Sita" });
    const handlers = api.interceptors.request.handlers;
    expect(handlers.length).toBeGreaterThan(0);
    const cfg = handlers[0].fulfilled({ headers: {} });
    expect(cfg.headers["X-Roster-Id"]).toBe("r-9");
  });
});
