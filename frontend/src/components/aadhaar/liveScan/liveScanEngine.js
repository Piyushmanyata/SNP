export const PAYLOAD_IGNORE_MS = 1500;
export const HINT_AFTER_MS = 4000;
export const SCAN_STALL_MS = 10000;
export const TICK_MS = 80;
export const READER_UNAVAILABLE = "QR reader unavailable. Retry the camera, upload a photo, or use a USB scanner.";

export function createLiveScanEngine({
  lanes = [],
  decode,
  now = () => Date.now(),
  onLock,
  onFailure,
  onHint,
  onScanStall,
  onError,
} = {}) {
  let session = 0;
  let running = false;
  let holding = false;
  let startedAt = 0;
  let hinted = false;
  let stalled = false;
  const ignoredUntil = new Map();
  const slots = lanes.map((lane) => ({ lane, busy: false, loaded: !lane.load, failed: false, turn: 0 }));

  const live = (mine) => running && mine === session;

  function isIgnored(payload) {
    const until = ignoredUntil.get(payload);
    if (until == null) return false;
    if (now() <= until) return true;
    ignoredUntil.delete(payload);
    return false;
  }

  function watchClock() {
    const elapsed = now() - startedAt;
    if (!hinted && elapsed >= HINT_AFTER_MS) {
      hinted = true;
      onHint?.();
    }
    if (!stalled && elapsed >= SCAN_STALL_MS) {
      stalled = true;
      onScanStall?.();
    }
  }

  async function resolve(payload, mine) {
    holding = true;
    let result = null;
    try {
      result = await decode(payload);
    } catch {
      result = null;
    }
    if (!live(mine)) return;
    holding = false;
    if (result?.outcome === "card") {
      running = false;
      onLock?.(result);
      return;
    }
    ignoredUntil.set(payload, now() + PAYLOAD_IGNORE_MS);
    onFailure?.(result);
  }

  async function run(slot, mine) {
    slot.busy = true;
    try {
      if (!slot.loaded) {
        await slot.lane.load();
        slot.loaded = true;
      }
      if (!live(mine) || holding) return;
      const regions = slot.lane.regions || [null];
      const region = regions[slot.turn % regions.length];
      slot.turn += 1;
      const payload = await slot.lane.detect(region);
      if (!live(mine) || holding || !payload || isIgnored(payload)) return;
      await resolve(payload, mine);
    } catch {
      if (!live(mine)) return;
      slot.failed = true;
      if (slots.every((s) => s.failed)) {
        stop();
        onError?.(READER_UNAVAILABLE);
      }
    } finally {
      slot.busy = false;
    }
  }

  function tick() {
    if (!running || holding) return;
    watchClock();
    const mine = session;
    for (const slot of slots) {
      if (!slot.busy && !slot.failed) run(slot, mine);
    }
  }

  function start() {
    session += 1;
    running = true;
    holding = false;
    startedAt = now();
    hinted = false;
    stalled = false;
    ignoredUntil.clear();
    for (const slot of slots) slot.failed = false;
    if (!slots.length) {
      running = false;
      onError?.(READER_UNAVAILABLE);
    }
  }

  function stop() {
    session += 1;
    running = false;
    holding = false;
  }

  function getState() {
    return {
      running,
      holding,
      lanes: slots.map(({ busy, loaded, failed }) => ({ busy, loaded, failed })),
    };
  }

  return { start, stop, tick, getState };
}
