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

  postMessage(msg, transfer) {
    this.posted.push({ msg, transfer });
  }

  ready(ok = true) {
    this.onmessage({ data: { ready: ok } });
  }

  reply(index, text) {
    this.onmessage({ data: { id: this.posted[index].msg.id, text } });
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

const settle = () => Promise.resolve().then(() => Promise.resolve());

async function loaded() {
  const loading = detector.loadZxingWorker();
  instances[instances.length - 1].ready();
  await loading;
  return instances[instances.length - 1];
}

test("the reader is ready only once the worker has compiled the module", async () => {
  const loading = detector.loadZxingWorker();
  let done = false;
  loading.then(() => { done = true; });
  await settle();
  expect(done).toBe(false);
  instances[0].ready();
  await loading;
  expect(detector.loadZxingWorker()).toBe(loading);
  expect(instances).toHaveLength(1);
});

test("a slow first download is not cut off by the per-frame timeout", async () => {
  const pending = detector.detectWasmImageData(IMAGE);
  jest.advanceTimersByTime(detector.WASM_DETECT_TIMEOUT_MS * 3);
  const worker = instances[0];
  expect(worker.terminated).toBe(false);
  worker.ready();
  await settle();
  worker.reply(0, "1234567890");
  await expect(pending).resolves.toBe("1234567890");
});

test("a module that fails to compile rejects and the next load starts a fresh worker", async () => {
  const loading = detector.loadZxingWorker();
  instances[0].ready(false);
  await expect(loading).rejects.toThrow("QR reader unavailable");
  expect(instances[0].terminated).toBe(true);
  detector.loadZxingWorker();
  expect(instances).toHaveLength(2);
});

test("a load that never finishes gives up after the load timeout", async () => {
  const loading = detector.loadZxingWorker();
  jest.advanceTimersByTime(detector.WASM_LOAD_TIMEOUT_MS);
  await expect(loading).rejects.toThrow("QR reader unavailable");
  expect(instances[0].terminated).toBe(true);
});

test("without Worker support the reader is unavailable", async () => {
  delete global.Worker;
  await expect(detector.loadZxingWorker()).rejects.toThrow("Worker unavailable");
});

test("a decode result resolves the matching detect and transfers the pixels", async () => {
  const worker = await loaded();
  const image = { width: 2, height: 2, data: new Uint8ClampedArray(16) };
  const pending = detector.detectWasmImageData(image);
  await settle();
  expect(worker.posted[0].transfer).toEqual([image.data.buffer]);
  worker.reply(0, "1234567890");
  await expect(pending).resolves.toBe("1234567890");
});

test("a photo is sent whole with the photo reader options and a longer timeout", async () => {
  const worker = await loaded();
  const file = new Blob(["jpeg"], { type: "image/jpeg" });
  const pending = detector.detectWasmPhoto(file);
  await settle();
  expect(worker.posted[0].msg).toMatchObject({ image: file, photo: true });
  jest.advanceTimersByTime(detector.WASM_DETECT_TIMEOUT_MS * 2);
  expect(worker.terminated).toBe(false);
  worker.reply(0, "photo-card");
  await expect(pending).resolves.toBe("photo-card");
});

test("no image means no detect", async () => {
  await expect(detector.detectWasmImageData(null)).resolves.toBeNull();
  expect(instances).toHaveLength(0);
});

test("a worker crash settles every outstanding detect instead of hanging", async () => {
  const worker = await loaded();
  const first = detector.detectWasmImageData(IMAGE);
  const second = detector.detectWasmImageData({ ...IMAGE, data: new Uint8ClampedArray(16) });
  await settle();
  worker.onerror(new Error("crashed"));
  await expect(first).resolves.toBeNull();
  await expect(second).resolves.toBeNull();
  expect(worker.terminated).toBe(true);
});

test("one slow frame is dropped and the loaded worker is kept for the next frame", async () => {
  const worker = await loaded();
  const first = detector.detectWasmImageData(IMAGE);
  await settle();
  jest.advanceTimersByTime(detector.WASM_DETECT_TIMEOUT_MS);
  await expect(first).resolves.toBeNull();
  expect(worker.terminated).toBe(false);
  expect(() => worker.reply(0, "late")).not.toThrow();

  const next = detector.detectWasmImageData({ ...IMAGE, data: new Uint8ClampedArray(16) });
  await settle();
  expect(instances).toHaveLength(1);
  worker.reply(1, "next-card");
  await expect(next).resolves.toBe("next-card");
});

test("a worker that stalls on consecutive frames is replaced even when its late replies arrive", async () => {
  const stalled = await loaded();
  for (let i = 0; i < detector.WASM_MAX_STALLS; i += 1) {
    const frame = detector.detectWasmImageData({ ...IMAGE, data: new Uint8ClampedArray(16) });
    await settle();
    jest.advanceTimersByTime(detector.WASM_DETECT_TIMEOUT_MS);
    await expect(frame).resolves.toBeNull();
    if (!stalled.terminated) stalled.reply(i, "late");
  }
  expect(stalled.terminated).toBe(true);

  const next = detector.detectWasmImageData({ ...IMAGE, data: new Uint8ClampedArray(16) });
  expect(instances).toHaveLength(2);
  const replacement = instances[1];
  replacement.ready();
  await settle();
  replacement.reply(0, "next-card");
  await expect(next).resolves.toBe("next-card");
});

test("an undecodable frame keeps the healthy worker for the next frame", async () => {
  const worker = await loaded();
  const first = detector.detectWasmImageData(IMAGE);
  await settle();
  worker.reply(0, null);
  await expect(first).resolves.toBeNull();
  const next = detector.detectWasmImageData({ ...IMAGE, data: new Uint8ClampedArray(16) });
  await settle();
  expect(instances).toHaveLength(1);
  expect(worker.terminated).toBe(false);
  worker.reply(1, "1234567890");
  await expect(next).resolves.toBe("1234567890");
});

test("a frame that cannot be posted settles immediately", async () => {
  const worker = await loaded();
  worker.postMessage = () => { throw new Error("DataCloneError"); };
  await expect(detector.detectWasmImageData(IMAGE)).resolves.toBeNull();
});
