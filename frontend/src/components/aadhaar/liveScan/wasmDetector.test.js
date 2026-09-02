const IMAGE = { width: 2, height: 2, data: new Uint8ClampedArray(16) };

let instances;
let detector;

class FakeWorker {
  constructor(url) {
    this.url = url;
    this.posted = [];
    this.terminated = false;
    instances.push(this);
  }

  postMessage(msg) {
    this.posted.push(msg);
  }

  terminate() {
    this.terminated = true;
  }
}

beforeEach(() => {
  instances = [];
  global.Worker = FakeWorker;
  jest.useFakeTimers();
  jest.resetModules();
  detector = require("./wasmDetector");
});

afterEach(() => {
  jest.useRealTimers();
  delete global.Worker;
});

test("a decode result resolves the matching detect", async () => {
  await detector.loadZxingWorker();
  const pending = detector.detectWasmImageData(IMAGE);
  const worker = instances[0];
  worker.onmessage({ data: { id: worker.posted[0].id, text: "1234567890" } });
  await expect(pending).resolves.toBe("1234567890");
});

test("a worker that fails to load settles every outstanding detect instead of hanging", async () => {
  await detector.loadZxingWorker();
  const first = detector.detectWasmImageData(IMAGE);
  const second = detector.detectWasmImageData(IMAGE);
  instances[0].onerror(new Error("importScripts failed"));
  await expect(first).resolves.toBeNull();
  await expect(second).resolves.toBeNull();
});

test("a worker that never answers times out rather than wedging the scan loop", async () => {
  await detector.loadZxingWorker();
  const pending = detector.detectWasmImageData(IMAGE);
  jest.advanceTimersByTime(detector.WASM_DETECT_TIMEOUT_MS);
  await expect(pending).resolves.toBeNull();
});

test("a timed-out detect leaves no pending job behind for a late reply", async () => {
  await detector.loadZxingWorker();
  const pending = detector.detectWasmImageData(IMAGE);
  const worker = instances[0];
  jest.advanceTimersByTime(detector.WASM_DETECT_TIMEOUT_MS);
  await expect(pending).resolves.toBeNull();
  expect(() =>
    worker.onmessage({ data: { id: worker.posted[0].id, text: "late" } })
  ).not.toThrow();
});

test("one bad frame does not end WASM scanning for the rest of the session", async () => {
  await detector.loadZxingWorker();
  const failed = detector.detectWasmImageData(IMAGE);
  const worker = instances[0];
  worker.onerror(new Error("one bad frame"));
  await expect(failed).resolves.toBeNull();

  const next = detector.detectWasmImageData(IMAGE);
  expect(instances).toHaveLength(1);
  expect(worker.terminated).toBe(false);
  worker.onmessage({ data: { id: worker.posted[1].id, text: "1234567890" } });
  await expect(next).resolves.toBe("1234567890");
});
