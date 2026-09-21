import {
  FALLBACK_HINT_MS,
  NATIVE_MISS_LIMIT,
  PAYLOAD_IGNORE_MS,
  PROMOTE_AFTER_MS,
  SCAN_STALL_MS,
  ZXING_READER_OPTIONS,
  createLiveScanEngine,
} from "./liveScanEngine";

function deferred() {
  let resolve;
  const promise = new Promise((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function makeEngine(overrides = {}) {
  let t = 0;
  const loadWasm = jest.fn().mockResolvedValue();
  const detectNative = jest.fn().mockResolvedValue(null);
  const detectWasm = jest.fn().mockResolvedValue(null);
  const decode = jest.fn();
  const onLock = jest.fn();
  const onFailure = jest.fn();
  const onHintFallbacks = jest.fn();
  const onScanStall = jest.fn();
  const engine = createLiveScanEngine({
    hasNativeDetector: true,
    now: () => t,
    detectNative,
    detectWasm,
    loadWasm,
    decode,
    onLock,
    onFailure,
    onHintFallbacks,
    onScanStall,
    ...overrides,
  });
  return {
    engine,
    advance: (ms) => {
      t += ms;
    },
    loadWasm,
    detectNative,
    detectWasm,
    decode,
    onLock,
    onFailure,
    onHintFallbacks,
    onScanStall,
  };
}

const frame = { width: 1280, height: 720 };

describe("ZXING_READER_OPTIONS", () => {
  test("QR only and never downscales",
    () => {
      expect(ZXING_READER_OPTIONS).toEqual({
        formats: ["QRCode"],
        tryHarder: true,
        tryRotate: true,
        tryInvert: false,
        tryDownscale: false,
        maxNumberOfSymbols: 1,
      });
    }
  );
});

describe("createLiveScanEngine", () => {
  test("a failed QR reader stops scanning and offers recovery without unhandled rejection", async () => {
    const onError = jest.fn();
    const { engine } = makeEngine({
      hasNativeDetector: false,
      loadWasm: jest.fn().mockRejectedValue(new Error("Worker unavailable")),
      onError,
    });
    engine.start();
    await expect(engine.tick(frame)).resolves.toEqual({ error: true });
    expect(engine.getState().started).toBe(false);
    expect(onError).toHaveBeenCalledTimes(1);
    await expect(engine.tick(frame)).resolves.toEqual({ skipped: true });
  });

  test("does not load WASM while native is present and locking",
    async () => {
      const { engine, loadWasm, detectNative, decode, onLock } = makeEngine();
      detectNative.mockResolvedValue("AADHAAR|ok");
      decode.mockResolvedValue({ outcome: "card", data: { full_name: "A" } });
      engine.start();
      await engine.tick(frame);
      expect(loadWasm).not.toHaveBeenCalled();
      expect(onLock).toHaveBeenCalled();
      expect(engine.getState().decoder).toBe("native");
    }
  );

  test("loads WASM immediately when BarcodeDetector is missing",
    async () => {
      const { engine, loadWasm } = makeEngine({ hasNativeDetector: false });
      engine.start();
      await Promise.resolve();
      expect(loadWasm).toHaveBeenCalledTimes(1);
      expect(engine.getState().decoder).toBe("wasm");
    }
  );

  test("promotes to WASM after 8 consecutive native misses",
    async () => {
      const { engine, loadWasm, detectNative, detectWasm, advance } = makeEngine();
      engine.start();
      for (let i = 0; i < NATIVE_MISS_LIMIT; i += 1) {
        await engine.tick(frame);
        advance(50);
      }
      expect(loadWasm).toHaveBeenCalledTimes(1);
      expect(engine.getState().decoder).toBe("wasm");
      detectNative.mockClear();
      await engine.tick(frame);
      expect(detectNative).not.toHaveBeenCalled();
      expect(detectWasm).toHaveBeenCalled();
    }
  );

  test("promotes to WASM after 1.25s even with fewer than 8 misses",
    async () => {
      const { engine, loadWasm, advance } = makeEngine();
      engine.start();
      await engine.tick(frame);
      advance(PROMOTE_AFTER_MS);
      await engine.tick(frame);
      expect(loadWasm).toHaveBeenCalledTimes(1);
      expect(engine.getState().decoder).toBe("wasm");
    }
  );

  test("alternates Guide ROI then full frame at native pixels",
    async () => {
      const { engine, detectNative } = makeEngine();
      engine.start();
      await engine.tick(frame);
      await engine.tick(frame);
      await engine.tick(frame);
      expect(detectNative.mock.calls.map((c) => c[1])).toEqual(["roi", "full", "roi"]);
      expect(detectNative.mock.calls[0][0]).toBe(frame);
    }
  );

  test("Lock only on Decode card, then freezes",
    async () => {
      const { engine, detectNative, decode, onLock } = makeEngine();
      detectNative.mockResolvedValue("payload-1");
      decode.mockResolvedValue({ outcome: "card", data: { full_name: "Ramesh" } });
      engine.start();
      await engine.tick(frame);
      expect(onLock).toHaveBeenCalledWith(
        expect.objectContaining({ outcome: "card", data: { full_name: "Ramesh" } })
      );
      expect(engine.getState().frozen).toBe(true);
      detectNative.mockClear();
      await engine.tick(frame);
      expect(detectNative).not.toHaveBeenCalled();
    }
  );

  test("Failure resumes and ignores that payload for 1.5s",
    async () => {
      const { engine, detectNative, detectWasm, decode, onFailure, onLock, advance } = makeEngine();
      detectNative.mockResolvedValue("UPI-QR");
      detectWasm.mockResolvedValue("UPI-QR");
      decode.mockResolvedValue({ outcome: "not-aadhaar", message: "nope" });
      engine.start();
      await engine.tick(frame);
      expect(onFailure).toHaveBeenCalled();
      expect(onLock).not.toHaveBeenCalled();
      expect(engine.getState().frozen).toBe(false);
      decode.mockClear();
      await engine.tick(frame);
      expect(decode).not.toHaveBeenCalled();
      advance(PAYLOAD_IGNORE_MS + 1);
      decode.mockResolvedValue({ outcome: "card", data: { full_name: "Later" } });
      await engine.tick(frame);
      expect(decode).toHaveBeenCalled();
    }
  );

  test("drops a second tick while a detect is in flight",
    async () => {
      const { engine, detectNative } = makeEngine();
      const first = deferred();
      detectNative.mockReturnValueOnce(first.promise);
      engine.start();
      const a = engine.tick(frame);
      const b = engine.tick(frame);
      first.resolve(null);
      await Promise.all([a, b]);
      expect(detectNative).toHaveBeenCalledTimes(1);
    }
  );

  test("stops detection during Soft Hold",
    async () => {
      const { engine, detectNative, decode } = makeEngine();
      const held = deferred();
      detectNative.mockResolvedValue("hold-me");
      decode.mockReturnValueOnce(held.promise);
      engine.start();
      const first = engine.tick(frame);
      for (let i = 0; i < 20 && !engine.getState().softHold; i += 1) {
        await Promise.resolve();
      }
      expect(engine.getState().softHold).toBe(true);
      detectNative.mockClear();
      await engine.tick(frame);
      expect(detectNative).not.toHaveBeenCalled();
      held.resolve({ outcome: "garbage", message: "bad" });
      await first;
    }
  );

  test("never runs native and WASM detects at the same time",
    async () => {
      const { engine, detectNative, detectWasm, loadWasm } = makeEngine();
      let nativeRunning = 0;
      let wasmRunning = 0;
      let overlap = 0;
      detectNative.mockImplementation(async () => {
        nativeRunning += 1;
        if (nativeRunning && wasmRunning) overlap += 1;
        await Promise.resolve();
        nativeRunning -= 1;
        return null;
      });
      detectWasm.mockImplementation(async () => {
        wasmRunning += 1;
        if (nativeRunning && wasmRunning) overlap += 1;
        await Promise.resolve();
        wasmRunning -= 1;
        return null;
      });
      loadWasm.mockImplementation(async () => {
        await Promise.resolve();
      });
      engine.start();
      for (let i = 0; i < NATIVE_MISS_LIMIT + 2; i += 1) {
        await engine.tick(frame);
      }
      expect(overlap).toBe(0);
    }
  );

  test("hints photo/USB after 2.5s without Lock",
    async () => {
      const { engine, onHintFallbacks, advance } = makeEngine();
      engine.start();
      await engine.tick(frame);
      expect(onHintFallbacks).not.toHaveBeenCalled();
      advance(FALLBACK_HINT_MS);
      await engine.tick(frame);
      expect(onHintFallbacks).toHaveBeenCalledTimes(1);
    }
  );

  test("a result arriving after stop and restart belongs to no attempt",
    async () => {
      const { engine, detectNative, decode, onLock, onFailure } = makeEngine();
      const held = deferred();
      detectNative.mockResolvedValue("payload-1");
      decode.mockReturnValueOnce(held.promise);
      engine.start();
      const stale = engine.tick(frame);
      for (let i = 0; i < 20 && !engine.getState().softHold; i += 1) {
        await Promise.resolve();
      }
      engine.stop();
      engine.start();
      held.resolve({ outcome: "card", data: { full_name: "Stale" } });
      await stale;
      expect(onLock).not.toHaveBeenCalled();
      expect(onFailure).not.toHaveBeenCalled();
      expect(engine.getState().frozen).toBe(false);
      expect(engine.getState().inFlight).toBe(false);

      decode.mockResolvedValue({ outcome: "card", data: { full_name: "Fresh" } });
      await engine.tick(frame);
      expect(onLock).toHaveBeenCalledTimes(1);
      expect(onLock).toHaveBeenCalledWith(
        expect.objectContaining({ data: { full_name: "Fresh" } })
      );
    }
  );

  test("a detect arriving after stop and restart neither locks nor counts as a miss",
    async () => {
      const { engine, detectNative, decode, onLock } = makeEngine();
      const held = deferred();
      detectNative.mockReturnValueOnce(held.promise);
      engine.start();
      const stale = engine.tick(frame);
      engine.stop();
      engine.start();
      held.resolve("payload-1");
      await stale;
      expect(decode).not.toHaveBeenCalled();
      expect(onLock).not.toHaveBeenCalled();
      expect(engine.getState().nativeMisses).toBe(0);
    }
  );

  test("a reader failure permits a fresh attempt after restart",
    async () => {
      const onError = jest.fn();
      const loadWasm = jest.fn().mockRejectedValueOnce(new Error("Worker unavailable")).mockResolvedValue();
      const { engine, detectWasm, decode, onLock } = makeEngine({ hasNativeDetector: false, loadWasm, onError });
      engine.start();
      await engine.tick(frame);
      expect(onError).toHaveBeenCalledTimes(1);

      detectWasm.mockResolvedValue("payload-1");
      decode.mockResolvedValue({ outcome: "card", data: { full_name: "After retry" } });
      engine.start();
      await engine.tick(frame);
      expect(onLock).toHaveBeenCalledTimes(1);
      expect(engine.getState().inFlight).toBe(false);
    }
  );

  test("never decodes while a detect is running",
    async () => {
      const { engine, detectNative, decode } = makeEngine();
      let detecting = 0;
      let decoding = 0;
      let overlap = 0;
      let seq = 0;
      detectNative.mockImplementation(async () => {
        detecting += 1;
        if (decoding) overlap += 1;
        await Promise.resolve();
        detecting -= 1;
        seq += 1;
        return `payload-${seq}`;
      });
      decode.mockImplementation(async () => {
        decoding += 1;
        if (detecting) overlap += 1;
        await Promise.resolve();
        await Promise.resolve();
        decoding -= 1;
        return { outcome: "not-aadhaar" };
      });
      engine.start();
      const runs = [];
      for (let i = 0; i < 6; i += 1) {
        runs.push(engine.tick(frame));
        runs.push(engine.tick(frame));
        await Promise.resolve();
      }
      await Promise.all(runs);
      expect(decode).toHaveBeenCalled();
      expect(overlap).toBe(0);
    }
  );

  test("restarting live scan resets to native-first",
    async () => {
      const { engine, loadWasm, detectNative, advance } = makeEngine();
      engine.start();
      advance(PROMOTE_AFTER_MS);
      await engine.tick(frame);
      await engine.tick(frame);
      expect(engine.getState().decoder).toBe("wasm");
      engine.stop();
      engine.start();
      expect(engine.getState().decoder).toBe("native");
      detectNative.mockClear();
      loadWasm.mockClear();
      await engine.tick(frame);
      expect(detectNative).toHaveBeenCalled();
      expect(loadWasm).not.toHaveBeenCalled();
    }
  );
});

describe("Scan stall", () => {
  test("twenty seconds with no Detect at all reveals the fallbacks",
    async () => {
      const { engine, onScanStall, advance } = makeEngine();
      engine.start();
      await engine.tick(frame);
      expect(onScanStall).not.toHaveBeenCalled();

      advance(SCAN_STALL_MS - 1);
      await engine.tick(frame);
      expect(onScanStall).not.toHaveBeenCalled();
      expect(engine.getState().stalled).toBe(false);

      advance(1);
      await engine.tick(frame);
      expect(onScanStall).toHaveBeenCalledTimes(1);
      expect(engine.getState().stalled).toBe(true);
    }
  );

  test("a stall fires once, not on every later tick",
    async () => {
      const { engine, onScanStall, advance } = makeEngine();
      engine.start();
      advance(SCAN_STALL_MS);
      await engine.tick(frame);
      await engine.tick(frame);
      await engine.tick(frame);
      expect(onScanStall).toHaveBeenCalledTimes(1);
    }
  );

  test("an unrelated QR followed by the twenty second timeout still reveals the recovery path",
    async () => {
      jest.useFakeTimers();
      try {
        const detectNative = jest.fn().mockResolvedValue("UPI-QR");
        const detectWasm = jest.fn().mockResolvedValue("UPI-QR");
        const decode = jest.fn().mockResolvedValue({ outcome: "not-aadhaar", message: "nope" });
        const { engine, onScanStall, onFailure, onLock } = makeEngine({
          now: () => Date.now(),
          detectNative,
          detectWasm,
          decode,
        });
        engine.start();
        await engine.tick(frame);
        expect(onFailure).toHaveBeenCalledTimes(1);
        expect(onScanStall).not.toHaveBeenCalled();

        jest.advanceTimersByTime(SCAN_STALL_MS);
        await engine.tick(frame);
        expect(onScanStall).toHaveBeenCalledTimes(1);
        expect(onLock).not.toHaveBeenCalled();
        expect(engine.getState().frozen).toBe(false);
      } finally {
        jest.useRealTimers();
      }
    }
  );

  test("a throttled repeat of the same unrelated QR still reveals the recovery path",
    async () => {
      jest.useFakeTimers();
      try {
        const detectNative = jest.fn().mockResolvedValue("UPI-QR");
        const detectWasm = jest.fn().mockResolvedValue("UPI-QR");
        const decode = jest.fn().mockResolvedValue({ outcome: "not-aadhaar", message: "nope" });
        const { engine, onScanStall } = makeEngine({ now: () => Date.now(), detectNative, detectWasm, decode });
        engine.start();
        jest.advanceTimersByTime(SCAN_STALL_MS - 100);
        await engine.tick(frame);
        expect(decode).toHaveBeenCalledTimes(1);
        expect(onScanStall).not.toHaveBeenCalled();

        jest.advanceTimersByTime(100);
        await engine.tick(frame);
        expect(decode).toHaveBeenCalledTimes(1);
        expect(onScanStall).toHaveBeenCalledTimes(1);
      } finally {
        jest.useRealTimers();
      }
    }
  );

  test("an accepted Aadhaar identity is what holds the recovery path back",
    async () => {
      const { engine, detectNative, decode, onScanStall, onLock, advance } = makeEngine();
      detectNative.mockResolvedValue("AADHAAR|ok");
      decode.mockResolvedValue({ outcome: "card", data: { full_name: "Ramesh" } });
      engine.start();
      await engine.tick(frame);
      expect(onLock).toHaveBeenCalledTimes(1);
      expect(engine.getState().identityAccepted).toBe(true);

      advance(SCAN_STALL_MS * 2);
      await engine.tick(frame);
      expect(onScanStall).not.toHaveBeenCalled();
    }
  );

  test("restarting the scan clears the stall",
    async () => {
      const { engine, onScanStall, advance } = makeEngine();
      engine.start();
      advance(SCAN_STALL_MS);
      await engine.tick(frame);
      expect(onScanStall).toHaveBeenCalledTimes(1);

      engine.start();
      expect(engine.getState().stalled).toBe(false);
      expect(engine.getState().identityAccepted).toBe(false);
      await engine.tick(frame);
      expect(onScanStall).toHaveBeenCalledTimes(1);
    }
  );
});
