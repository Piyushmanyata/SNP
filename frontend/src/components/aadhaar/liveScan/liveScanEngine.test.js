import {
  HINT_AFTER_MS,
  PAYLOAD_IGNORE_MS,
  READER_UNAVAILABLE,
  SCAN_STALL_MS,
  createLiveScanEngine,
} from "./liveScanEngine";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function makeEngine({ lanes, decode = jest.fn().mockResolvedValue({ outcome: "garbage" }) } = {}) {
  let t = 0;
  const native = { load: jest.fn().mockResolvedValue(), detect: jest.fn().mockResolvedValue(null) };
  const wasm = { load: jest.fn().mockResolvedValue(), regions: ["roi", "full"], detect: jest.fn().mockResolvedValue(null) };
  const callbacks = {
    onLock: jest.fn(),
    onFailure: jest.fn(),
    onHint: jest.fn(),
    onScanStall: jest.fn(),
    onError: jest.fn(),
  };
  const engine = createLiveScanEngine({
    lanes: lanes || [native, wasm],
    decode,
    now: () => t,
    ...callbacks,
  });
  return {
    engine,
    native,
    wasm,
    decode,
    ...callbacks,
    advance: (ms) => {
      t += ms;
    },
  };
}

describe("createLiveScanEngine", () => {
  test("runs the native and WASM lanes side by side, one detect in flight per lane", async () => {
    const { engine, native, wasm } = makeEngine();
    const nativeHit = deferred();
    const wasmHit = deferred();
    native.detect.mockReturnValueOnce(nativeHit.promise);
    wasm.detect.mockReturnValueOnce(wasmHit.promise);
    engine.start();
    engine.tick();
    await flush();
    engine.tick();
    engine.tick();
    await flush();
    expect(native.detect).toHaveBeenCalledTimes(1);
    expect(wasm.detect).toHaveBeenCalledTimes(1);
    nativeHit.resolve(null);
    await flush();
    engine.tick();
    await flush();
    expect(native.detect).toHaveBeenCalledTimes(2);
    expect(wasm.detect).toHaveBeenCalledTimes(1);
    wasmHit.resolve(null);
  });

  test("loads each lane once and keeps it loaded across restarts", async () => {
    const { engine, native, wasm } = makeEngine();
    engine.start();
    for (let i = 0; i < 4; i += 1) {
      engine.tick();
      await flush();
    }
    engine.stop();
    engine.start();
    engine.tick();
    await flush();
    expect(native.load).toHaveBeenCalledTimes(1);
    expect(wasm.load).toHaveBeenCalledTimes(1);
  });

  test("alternates the Guide ROI and the full frame on the WASM lane", async () => {
    const { engine, wasm } = makeEngine();
    engine.start();
    for (let i = 0; i < 4; i += 1) {
      engine.tick();
      await flush();
    }
    expect(wasm.detect.mock.calls.map((call) => call[0])).toEqual(["roi", "full", "roi", "full"]);
  });

  test("a lane that cannot load is dropped while the other keeps scanning", async () => {
    const { engine, native, wasm, onError } = makeEngine();
    native.load.mockRejectedValue(new Error("no qr_code support"));
    engine.start();
    for (let i = 0; i < 3; i += 1) {
      engine.tick();
      await flush();
    }
    expect(native.detect).not.toHaveBeenCalled();
    expect(wasm.detect).toHaveBeenCalledTimes(3);
    expect(onError).not.toHaveBeenCalled();
  });

  test("when every lane fails the reader stops once and offers recovery", async () => {
    const { engine, native, wasm, onError } = makeEngine();
    native.load.mockRejectedValue(new Error("no qr_code support"));
    wasm.load.mockRejectedValue(new Error("Worker unavailable"));
    engine.start();
    engine.tick();
    await flush();
    engine.tick();
    await flush();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(READER_UNAVAILABLE);
    expect(engine.getState().running).toBe(false);
  });

  test("an engine without lanes reports the reader as unavailable", () => {
    const { engine, onError } = makeEngine({ lanes: [] });
    engine.start();
    expect(onError).toHaveBeenCalledWith(READER_UNAVAILABLE);
    expect(engine.getState().running).toBe(false);
  });

  test("Lock only when Decode returns card, then stops detecting", async () => {
    const decode = jest.fn().mockResolvedValue({ outcome: "card", data: { full_name: "A" } });
    const { engine, native, wasm, onLock } = makeEngine({ decode });
    native.detect.mockResolvedValueOnce("CARD");
    engine.start();
    engine.tick();
    await flush();
    await flush();
    expect(decode).toHaveBeenCalledWith("CARD");
    expect(onLock).toHaveBeenCalledTimes(1);
    expect(onLock).toHaveBeenCalledWith({ outcome: "card", data: { full_name: "A" } });
    const calls = native.detect.mock.calls.length + wasm.detect.mock.calls.length;
    engine.tick();
    await flush();
    expect(native.detect.mock.calls.length + wasm.detect.mock.calls.length).toBe(calls);
  });

  test("Soft Hold: no detect runs and a second payload is dropped while Decode is in flight", async () => {
    const pending = deferred();
    const decode = jest.fn().mockReturnValueOnce(pending.promise);
    const { engine, native, wasm } = makeEngine({ decode });
    const wasmHit = deferred();
    native.detect.mockResolvedValueOnce("FIRST");
    wasm.detect.mockReturnValueOnce(wasmHit.promise);
    engine.start();
    engine.tick();
    await flush();
    expect(engine.getState().holding).toBe(true);
    wasmHit.resolve("SECOND");
    await flush();
    engine.tick();
    await flush();
    expect(decode).toHaveBeenCalledTimes(1);
    expect(native.detect).toHaveBeenCalledTimes(1);
    pending.resolve({ outcome: "garbage" });
    await flush();
    expect(engine.getState().holding).toBe(false);
  });

  test("Failure resumes scanning and ignores that exact payload for a moment", async () => {
    const { engine, native, decode, onFailure, advance } = makeEngine();
    native.detect.mockResolvedValue("BAD");
    engine.start();
    engine.tick();
    await flush();
    await flush();
    expect(decode).toHaveBeenCalledTimes(1);
    expect(onFailure).toHaveBeenCalledWith({ outcome: "garbage" });
    engine.tick();
    await flush();
    expect(decode).toHaveBeenCalledTimes(1);
    advance(PAYLOAD_IGNORE_MS + 1);
    engine.tick();
    await flush();
    await flush();
    expect(decode).toHaveBeenCalledTimes(2);
  });

  test("a Decode that throws counts as a Failure, not a crash", async () => {
    const decode = jest.fn().mockRejectedValue(new Error("offline"));
    const { engine, native, onFailure, onError } = makeEngine({ decode });
    native.detect.mockResolvedValueOnce("CARD");
    engine.start();
    engine.tick();
    await flush();
    await flush();
    expect(onFailure).toHaveBeenCalledWith(null);
    expect(onError).not.toHaveBeenCalled();
    expect(engine.getState().running).toBe(true);
  });

  test("a detect arriving after stop and restart neither decodes nor locks", async () => {
    const decode = jest.fn().mockResolvedValue({ outcome: "card" });
    const { engine, native, onLock } = makeEngine({ decode });
    const late = deferred();
    native.detect.mockReturnValueOnce(late.promise);
    engine.start();
    engine.tick();
    await flush();
    engine.stop();
    engine.start();
    late.resolve("CARD");
    await flush();
    await flush();
    expect(decode).not.toHaveBeenCalled();
    expect(onLock).not.toHaveBeenCalled();
  });

  test("a Decode resolving after stop does not lock", async () => {
    const pending = deferred();
    const decode = jest.fn().mockReturnValueOnce(pending.promise);
    const { engine, native, onLock } = makeEngine({ decode });
    native.detect.mockResolvedValueOnce("CARD");
    engine.start();
    engine.tick();
    await flush();
    engine.stop();
    pending.resolve({ outcome: "card" });
    await flush();
    expect(onLock).not.toHaveBeenCalled();
  });

  test("hints once after the hint delay without a Lock", async () => {
    const { engine, onHint, advance } = makeEngine();
    engine.start();
    advance(HINT_AFTER_MS - 1);
    engine.tick();
    expect(onHint).not.toHaveBeenCalled();
    advance(1);
    engine.tick();
    engine.tick();
    expect(onHint).toHaveBeenCalledTimes(1);
  });
});

describe("Scan stall", () => {
  test("reveals the fallbacks once when nothing locks in time", () => {
    const { engine, onScanStall, advance } = makeEngine();
    engine.start();
    advance(SCAN_STALL_MS - 1);
    engine.tick();
    expect(onScanStall).not.toHaveBeenCalled();
    advance(1);
    engine.tick();
    advance(5000);
    engine.tick();
    expect(onScanStall).toHaveBeenCalledTimes(1);
  });

  test("an unrelated QR that keeps failing still reveals the recovery path", async () => {
    const decode = jest.fn().mockResolvedValue({ outcome: "not-aadhaar" });
    const { engine, native, onScanStall, advance } = makeEngine({ decode });
    native.detect.mockResolvedValue("UNRELATED");
    engine.start();
    for (let i = 0; i < 5; i += 1) {
      advance(SCAN_STALL_MS / 4);
      engine.tick();
      await flush();
      await flush();
    }
    expect(onScanStall).toHaveBeenCalledTimes(1);
  });

  test("restarting the scan clears the stall and the hint", () => {
    const { engine, onScanStall, onHint, advance } = makeEngine();
    engine.start();
    advance(SCAN_STALL_MS);
    engine.tick();
    engine.stop();
    engine.start();
    engine.tick();
    advance(SCAN_STALL_MS);
    engine.tick();
    expect(onScanStall).toHaveBeenCalledTimes(2);
    expect(onHint).toHaveBeenCalledTimes(2);
  });

  test("a stopped engine never hints or stalls", () => {
    const { engine, onScanStall, onHint, advance } = makeEngine();
    engine.start();
    engine.stop();
    advance(SCAN_STALL_MS);
    engine.tick();
    expect(onScanStall).not.toHaveBeenCalled();
    expect(onHint).not.toHaveBeenCalled();
  });
});
