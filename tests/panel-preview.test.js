import { test, expect } from "bun:test";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../custom_components/fraimic/frontend/fraimic-panel.js", import.meta.url), "utf8");

function harness({ bytes = 100, deferred = false } = {}) {
  const timers = new Map(), requests = [], decodes = [], releases = [];
  let Panel, nextTimer = 0;
  runInNewContext(source, {
    HTMLElement: class {}, customElements: { define: (_name, cls) => { Panel = cls; } },
    URLSearchParams, AbortController,
    setTimeout: (callback) => { const id = ++nextTimer; timers.set(id, callback); return id; },
    clearTimeout: (id) => timers.delete(id),
    createImageBitmap: async () => {
      const image = { width: 2560, height: 1440, closed: false, close() { this.closed = true; } };
      decodes.push(image);
      return image;
    },
  });
  const panel = Object.create(Panel.prototype);
  Object.assign(panel, {
    _detail: { source: "saved", itemId: "art", width: 1600, height: 1200 },
    _detailOptions: { fit: "cover", tone: "balanced", mode: "auto", crop: [0, .1, 1, .85] },
    _modal: { className: "detail-dialog" }, _selectedFrameId: "frame", _previewEnabled: false,
    _paintDetailPreview() {}, _friendlyError: (error) => error.message,
    _hass: { fetchWithAuth: async (key, { signal }) => {
      requests.push({ key, signal });
      if (deferred) await new Promise((resolve) => releases.push(resolve));
      return { ok: true, blob: async () => ({ size: bytes }) };
    } },
  });
  const next = () => {
    const [id, callback] = timers.entries().next().value;
    timers.delete(id);
    return callback();
  };
  const drain = async () => {
    for (let count = 0; timers.size; count++) {
      if (count > 20) throw new Error("Preview warming did not settle");
      await next();
    }
  };
  return { panel, timers, requests, decodes, releases, next, drain };
}

const mode = (request) => new URL(request.key, "http://test").searchParams.get("mode");

test("player uses polled frame data for missed wakes and LAN actions", () => {
  const { panel } = harness();
  panel._frames = [{ id: "frame", name: "Frame", delivery: "local", missed_wake: null, last_seen: 1 }];
  const lastSeen = Date.now() / 1000 - 600;
  panel._player = {
    state: "unreachable", frame: { name: "Frame", delivery: "backend", missed_wake: "2026-10-25T14:05:00Z", last_seen: lastSeen },
    preview: { title: "Art", status: "waiting" },
  };
  panel._clockTime = () => "14:05";
  let html = panel._playerTemplate();
  expect(html).toContain("Frame missed its 14:05 wake");
  expect(html).toContain("Last seen 10 minutes ago");
  expect(html).toContain("data-backend-status");
  expect(html).not.toContain('data-player-action="retry"');
  expect(panel._lanCommands()).toBe(false);
  panel._player.frame = { ...panel._player.frame, missed_wake: null };
  html = panel._playerTemplate();
  expect(html).toContain("Could not reach Frame");
  expect(html).toContain("Last seen 10 minutes ago");
  panel._player = null;
  expect(panel._lanCommands()).toBe(true);
});

test("terminal handoffs explain why delivery is no longer offered", () => {
  const { panel } = harness();
  panel._frames = [];
  for (const status of ["expired", "unavailable"]) {
    panel._player = { preview: { title: "Snapshot", status } };
    expect(panel._previewMeta(panel._player.preview)).toContain(`Delivery ${status}`);
    const html = panel._backendBody();
    expect(html).toContain(`Delivery ${status}`);
    expect(html).not.toContain("Offered at");
    expect(html).not.toContain("Waiting on the frame");
  }
});

test("opening warms all dither modes without decoding or displaying them", async () => {
  const h = harness();
  h.panel._queueDetailPreview();
  await h.drain();
  expect(h.requests.map(mode)).toEqual(["auto", "bayer", "none", "floyd_steinberg", "atkinson", "official"]);
  expect(h.decodes).toHaveLength(0);
  h.panel._queueDetailPreview();
  expect(h.timers.size).toBe(0);
  h.panel._previewEnabled = true;
  h.panel._queueDetailPreview();
  await new Promise(setImmediate);
  expect(h.decodes).toHaveLength(1);
  expect(h.panel._detailPreview.bitmap.key).toBe(h.panel._detailPreview.wanted);
  expect(h.requests).toHaveLength(6);
});

test("selection jumps ahead of warming and crop/tone changes replace queued work", async () => {
  const h = harness({ deferred: true });
  h.panel._queueDetailPreview();
  const first = h.next();
  h.panel._detailOptions.mode = "official";
  h.panel._detailOptions.tone = "soft";
  h.panel._detailOptions.crop = [0, 0, .5, 1];
  h.panel._queueDetailPreview();
  expect(h.requests).toHaveLength(1);
  h.releases.shift()();
  await first;
  const second = h.next();
  expect(mode(h.requests[1])).toBe("official");
  const query = new URL(h.requests[1].key, "http://test").searchParams;
  expect(query.get("tone")).toBe("soft");
  expect(JSON.parse(query.get("crop"))).toEqual([0, 0, .5, 1]);
  h.releases.shift()();
  await second;
  h.panel._disposeDetailPreview();
  expect(h.timers.size).toBe(0);
});

test("compressed cache is byte bounded and warming stops after eviction", async () => {
  const h = harness({ bytes: 9 * 1024 * 1024 });
  h.panel._queueDetailPreview();
  await h.drain();
  expect(h.requests).toHaveLength(6);
  expect(h.panel._detailPreview.bytes).toBeLessThanOrEqual(24 * 1024 * 1024);
  expect(h.panel._detailPreview.cache.has(h.panel._detailPreview.wanted)).toBe(true);
  expect(h.decodes).toHaveLength(0);
});

test("only the requested bitmap is retained and closing aborts background work", async () => {
  const h = harness();
  h.panel._queueDetailPreview();
  await h.drain();
  h.panel._previewEnabled = true;
  h.panel._queueDetailPreview();
  await new Promise(setImmediate);
  h.panel._detailOptions.mode = "none";
  h.panel._queueDetailPreview();
  await new Promise(setImmediate);
  expect(h.decodes).toHaveLength(2);
  expect(h.decodes[0].closed).toBe(true);
  expect(h.decodes[1].closed).toBe(false);
  h.panel._disposeDetailPreview();
  expect(h.decodes[1].closed).toBe(true);
  expect(h.requests.at(-1).signal.aborted).toBe(true);
});

test("rotated crop coordinates round-trip and preserve the wall aspect", () => {
  const { panel } = harness();
  const original = [.125, .25, .625, .75];
  for (const rotation of [0, 90, 180, 270]) {
    expect([...panel._rotateCrop(panel._rotateCrop(original, rotation), -rotation)]).toEqual(original);
    panel._detail.saved_rotation = rotation;
    const frame = { width: 1440, height: 2560, rotation: 90 };
    const crop = panel._rotateCrop(panel._defaultCrop(panel._detail, frame), rotation);
    const ratio = (crop[2] - crop[0]) / (crop[3] - crop[1]) * panel._detailSourceRatio;
    expect(ratio).toBeCloseTo(2560 / 1440);
  }
});


test("disabled source caching warms only the selected mode", async () => {
  const h = harness();
  h.panel._detail.warm_previews = false;
  h.panel._queueDetailPreview();
  await h.drain();
  expect(h.requests.map(mode)).toEqual(["auto"]);
  h.panel._detailOptions.mode = "bayer";
  h.panel._queueDetailPreview();
  await h.drain();
  expect(h.requests.map(mode)).toEqual(["auto", "bayer"]);
});

test("sending to other frames lets the backend use their own crop and rotation", async () => {
  const { panel } = harness();
  const selected = { id: "frame", width: 1440, height: 2560, rotation: 90 };
  const target = { id: "other", width: 1600, height: 1200, rotation: 0 };
  panel._frames = [selected, target];
  panel._detail.saved_rotation = 90;
  panel._fitDifference = () => 0;
  panel._openModal = () => {};
  panel._closeModal = () => {};
  const buttons = [selected, target].map((frame) => ({ dataset: { showFrame: frame.id } }));
  let both;
  panel.shadowRoot = {
    querySelectorAll: () => buttons,
    querySelector: () => ({ addEventListener: (_event, fn) => { both = fn; } }),
  };
  const sends = [];
  panel._artAction = async (...args) => sends.push(args);
  const crop = [.2, 0, .8, 1];
  panel._showNow("saved", "art", { crop });
  buttons[1].onclick();
  await both();
  expect(sends.map((args) => args[5])).toEqual(["other", "frame", "other"]);
  expect(sends.map((args) => args[4].crop)).toEqual([null, crop, null]);
});

test("standalone queue exposes Play, frame settings, and a single editable list", () => {
  const { panel } = harness();
  panel._frames = [{ id: "frame", name: "Frame" }];
  panel._player = { state: "playing", transport_available: true, paused: true, interval: 1800,
    current: {}, queue_count: 1, hand_queue: [{ id: "one", title: "One", meta: "Picture" }] };
  expect(panel._playerTemplate()).toContain('data-player-action="play"');
  const queue = panel._queueTemplate();
  expect(queue).toContain('data-menu="interval"');
  expect(queue).toContain('data-menu="end"');
  expect(queue).toContain('data-remove-queue="0:one"');
  expect(queue).not.toContain("Next from");
  expect(queue).not.toContain("Choose a playlist");
});

test("auto picks follow the hand queue and can be kept above the divider", async () => {
  const { panel } = harness();
  panel._frames = [{ id: "frame", name: "Frame" }];
  panel._player = { state: "playing", interval: 1800, current: {}, end_action: "auto",
    auto: { sources: [{ kind: "shuffle", label: "Surprise me", weight: 2 }] },
    hand_queue: [{ id: "one", title: "One", meta: "Picture" }],
    auto_queue: [{ id: "pick", title: "Pick", meta: "Monet · Surprise me", auto_source: "Surprise me" }] };
  const queue = panel._queueTemplate();
  expect(queue).toContain("Then: Auto mode");
  expect(queue).toContain("Surprise me 2×");
  expect(queue).toContain('data-remove-queue="1:pick"');
  expect(queue).toContain("Monet · Surprise me");
  const sent = [];
  panel._queueAction = async (body) => sent.push(body);
  await panel._reorderQueue("queue", 1, 0, true);
  await panel._reorderQueue("queue", 0, 1);
  expect(sent).toEqual([{ action: "reorder", section: "queue", ordered_ids: ["pick", "one"], keep_ids: ["pick"] }]);
});

test("Clear stays available when a repeating queue reaches its final picture", () => {
  const { panel } = harness();
  panel._player = { interval: 1800, current: { title: "Last picture" }, hand_queue: [],
    end_action: "repeat", repeat: true };
  expect(panel._queueTemplate()).toContain("data-clear-queue >Clear</button>");
  panel._player.end_action = "stop";
  panel._player.repeat = false;
  expect(panel._queueTemplate()).toContain("data-clear-queue disabled>Clear</button>");
});

test("queue timing controls use the frame API without a playlist", async () => {
  const { panel } = harness();
  const calls = [];
  panel._player = { shuffle: false };
  panel._api = async (url, options) => { calls.push([url, JSON.parse(options.body)]); return {}; };
  panel._render = () => {};
  await panel._setInterval(21600);
  expect(calls).toEqual([["player/control", { action: "interval", interval: 21600, entry_id: "frame" }]]);
});

test("player explains a deferred send and an exhausted queue", () => {
  const { panel } = harness();
  expect(panel._playbackStatus({ delay: { message: "Battery low." } })).toBe("Battery low.");
  expect(panel._playbackStatus({ exhausted: true, paused: true })).toBe("Queue finished · picture stays on frame");
});
