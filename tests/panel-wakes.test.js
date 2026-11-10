import { test, expect } from "bun:test";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../custom_components/fraimic/frontend/fraimic-panel.js", import.meta.url), "utf8");
const EVERY_DAY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function panel(player) {
  let Panel;
  runInNewContext(source, {
    HTMLElement: class {}, customElements: { define: (_name, cls) => { Panel = cls; } },
    URLSearchParams, AbortController, setTimeout, clearTimeout, structuredClone,
  });
  return Object.assign(Object.create(Panel.prototype), { _player: player, _frames: [{ id: "frame", name: "Large" }], _selectedFrameId: "frame" });
}

function wakes(fields = {}) {
  return {
    supported: true, active: true, synced: true, missed: 0,
    schedule: { times: ["07:00", "19:00"], interval: null, days: EVERY_DAY },
    next_wake: new Date(Date.now() + 3600e3).toISOString(),
    slots: [new Date(Date.now() + 3600e3).toISOString(), new Date(Date.now() + 86400e3).toISOString()],
    ...fields,
  };
}

test("summarises a schedule as the frame stores it", () => {
  const p = panel({});
  expect(p._wakeSummary({ times: ["07:00", "19:00"], interval: null, days: EVERY_DAY })).toBe("07:00 · 19:00");
  expect(p._wakeSummary({ times: [], interval: 360, days: ["mon", "tue", "wed", "thu", "fri"] })).toBe("Every 6 h · Weekdays");
  expect(p._wakeSummary({ times: [], interval: 90, days: ["mon", "wed"] })).toBe("Every 1.5 h · Mon, Wed");
  expect(p._wakeCount({ times: ["07:00", "19:00"], interval: null, days: EVERY_DAY })).toBe("2 wakes a day");
  expect(p._wakeCount({ times: [], interval: 1440, days: ["sat"] })).toBe("1 wake a week");
});

test("the menu says whether the frame holds the saved schedule", () => {
  const p = panel({ wakes: wakes({ synced: false }) });
  const menu = p._intervalMenuTemplate("queue-interval-menu");
  expect(menu).toContain("wake-menu");
  expect(menu).toContain("At its next wake");
  expect(menu).toContain("data-wake-off");
  // An unsaved edit hides the frame's status until it is saved.
  p._wakeDraft.times = ["08:00"];
  expect(p._intervalMenuTemplate("queue-interval-menu")).not.toContain("Saved on frame");
});

test("a frame without a schedule keeps the interval menu and offers one", () => {
  const p = panel({ interval: 1800, wakes: wakes({ active: false, schedule: null }) });
  const menu = p._intervalMenuTemplate("queue-interval-menu");
  expect(menu).toContain("Changes every");
  expect(menu).toContain("data-wake-edit");
  expect(panel({ interval: 1800, wakes: null })._intervalMenuTemplate("menu")).not.toContain("data-wake-edit");
});

test("queued rows show their wake only while playing", () => {
  const playing = panel({ wakes: wakes(), paused: false });
  expect(playing._rowTime(0)).toContain("row-time next");
  expect(playing._rowTime(1)).toContain("row-time");
  expect(playing._rowTime(2)).toBe("");
  expect(panel({ wakes: wakes(), paused: true })._rowTime(0)).toBe("");
});

test("a failed wake save preserves the draft for correction", async () => {
  const p = panel({});
  const draft = { times: [""], interval: null, days: EVERY_DAY };
  p._wakeDraft = draft;
  p._menu = "interval";
  p._api = async () => { throw new Error("Invalid time"); };
  p._notify = () => {};
  p._friendlyError = (error) => error.message;
  await p._saveWake(draft);
  expect(p._wakeDraft).toBe(draft);
  expect(p._menu).toBe("interval");
  p._api = async () => ({ wakes: wakes() });
  p._render = () => {};
  await p._saveWake(draft);
  expect(p._wakeDraft).toBeNull();
  expect(p._menu).toBeNull();
});
