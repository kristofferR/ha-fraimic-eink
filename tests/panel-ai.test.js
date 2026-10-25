import { test, expect } from "bun:test";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../custom_components/fraimic/frontend/fraimic-panel.js", import.meta.url), "utf8");
const voice = (entryId, patch = {}) => ({ entry_id: entryId, name: entryId, available: true, mode: "fixed", image: "", stt: "", language: "", agent: "homeassistant", ai_task_entity: "", ...patch });

function harness(patch = {}) {
  let Panel;
  const stored = new Map();
  runInNewContext(source, {
    HTMLElement: class {}, customElements: { define: (_name, cls) => { Panel = cls; } },
    structuredClone, URLSearchParams, queueMicrotask, URL, setTimeout, clearTimeout,
    localStorage: { getItem: (key) => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, String(value)) },
  });
  const ai = {
    provider: "", configured: false, ready: {}, openrouter: { has_key: false, model: "model" },
    local: { url: "http://gpu", api: "openai", model: "", steps: null },
    ai_task_entity: "", style: "none", styles: [{ id: "none", name: "None", template: "{prompt}" }],
    builtin_styles: {}, rewrite_entity: "", voice: [voice("first"), voice("second")],
    choices: { image_entities: [], data_entities: [], stt: [], images: [], agents: [], language: "en" },
    ...patch,
  };
  const requests = [], notices = [];
  const panel = Object.create(Panel.prototype);
  Object.assign(panel, {
    _selectedFrameId: "first", _ai: ai, _frames: [],
    _api: async (path, options) => { requests.push({ path, options }); return ai; },
    _openModal: (_title, body, actions, options) => { panel._modal = { body, actions, ...options }; },
    _renderPreservingFocus: () => {},
    _closeModal: () => { panel._modal = null; },
    _notify: (message) => notices.push(message),
    shadowRoot: { getElementById: () => null },
  });
  return { panel, ai, requests, notices };
}

test("fixed-picture and Assist voice settings save without an image provider or other frames configured", async () => {
  for (const mode of ["fixed", "assist"]) {
    const { panel, requests, notices } = harness();
    await panel._openAiSettings();
    expect(panel._aiDraft.provider).toBe("");
    Object.assign(panel._aiDraft.voice.first, { mode, image: "picture", stt: "stt.whisper" });
    await panel._saveAiSettings();
    const saved = JSON.parse(requests.at(-1).options.body);
    expect(saved.provider).toBe("");
    expect(saved.voice.first.mode).toBe(mode);
    expect(saved.voice.second.image).toBe("");
    expect(notices).toEqual(["AI art settings saved."]);
  }
});

test("an edited voice frame still requires its picture or STT", async () => {
  const { panel, notices } = harness();
  await panel._openAiSettings();
  panel._aiDraft.voice.first.mode = "assist";
  await panel._saveAiSettings();
  expect(notices[0]).toContain("Choose speech to text for first");
});

test("failed local checks preserve a saved API only for the saved URL", async () => {
  const { panel } = harness({ provider: "local", configured: true });
  await panel._openAiSettings();
  panel._api = async () => ({ ok: false, error: "offline" });
  await panel._checkAi();
  expect(panel._aiDraft.local_api).toBe("openai");
  panel._aiDraft.local_url = "http://another-gpu";
  await panel._checkAi();
  expect(panel._aiDraft.local_api).toBe("");
});

test("reopening settings and Create retries a failed model load", async () => {
  const { panel } = harness({ provider: "openrouter", configured: true, ready: { openrouter: true } });
  let attempts = 0;
  panel._aiModels = { entryId: "first", list: null, error: "offline" };
  panel._loadAiModels = () => { attempts++; };
  await panel._openAiSettings();
  expect(attempts).toBe(1);
  panel._createBody = panel._createActions = () => "";
  await panel._openCreate();
  expect(attempts).toBe(2);
  panel._aiModels.list = [];
  await panel._openAiSettings();
  expect(attempts).toBe(2);
});

test("per-frame AI Task selections are shown and preserved when saving", async () => {
  const { panel, requests } = harness({
    provider: "ai_task", configured: true, ai_task_entity: "ai_task.shared",
    voice: [voice("first", { mode: "art", stt: "stt.whisper", ai_task_entity: "ai_task.frame" })],
    choices: { image_entities: [{ id: "ai_task.frame", name: "Frame model" }], data_entities: [], stt: [], images: [], agents: [], language: "en" },
  });
  await panel._openAiSettings();
  expect(panel._modal.body).toContain('data-ai-voice="first:ai_task_entity"');
  panel._ai.choices.image_entities = [];
  expect(panel._aiVoiceRow(panel._ai.voice[0])).toContain('value="ai_task.frame" selected>ai_task.frame (unavailable)');
  await panel._saveAiSettings();
  expect(JSON.parse(requests.at(-1).options.body).voice.first.ai_task_entity).toBe("ai_task.frame");
});

test("retry disables result actions and submits only once across pending deletion and generation", async () => {
  const { panel } = harness();
  const deletion = Promise.withResolvers();
  const generation = Promise.withResolvers();
  const started = Promise.withResolvers();
  const requests = [];
  Object.assign(panel, {
    _frames: [],
    _modal: { className: "create-dialog" },
    _createState: { phase: "result", service: "openrouter", request: "A fox", result: { image_id: "old" } },
    _createBody: () => "",
    _loadSources: async () => {},
    _loadCreatePreview: () => {},
    _api: (path) => {
      requests.push(path);
      if (path === "ai/create") { started.resolve(); return generation.promise; }
      return deletion.promise;
    },
  });
  const retry = panel._discardCreation(true);
  expect(panel._modal.actions.match(/disabled/g)).toHaveLength(3);
  await panel._discardCreation(true);
  await panel._discardCreation(false);
  await panel._runCreate();
  expect(requests).toEqual(["library/image/old"]);
  deletion.resolve();
  await started.promise;
  await panel._runCreate();
  await panel._discardCreation(true);
  expect(requests).toEqual(["library/image/old", "ai/create"]);
  generation.resolve({ image_id: "new" });
  await retry;
  expect(panel._createState.result.image_id).toBe("new");
  expect(panel._modal.actions).not.toContain("disabled");
});

test("a failed generation can be retried after duplicate submissions were rejected", async () => {
  const { panel } = harness();
  const generation = Promise.withResolvers();
  let attempts = 0;
  Object.assign(panel, {
    _createState: { phase: "compose", service: "openrouter", request: "A fox" },
    _refreshCreate: () => {},
    _api: () => { attempts++; return generation.promise; },
  });
  const first = panel._runCreate();
  await panel._runCreate();
  expect(attempts).toBe(1);
  generation.reject(new Error("offline"));
  await first;
  expect(panel._createState.phase).toBe("compose");
  expect(panel._createState.error).toBe("offline");
  await panel._runCreate();
  expect(attempts).toBe(2);
});

test("Create opens to the prompt before setup, and setup returns to it with the text", async () => {
  const { panel } = harness();
  await panel._openCreate();
  expect(panel._modal.className).toContain("create-dialog");
  expect(panel._modal.body).toContain('id="create-request"');
  expect(panel._modal.body).toContain("No image service yet");
  expect(panel._modal.actions).toContain("Set up AI art");
  panel._createState.request = "A fox";
  await panel._openAiSettings({ tab: "local", returnToCreate: true });
  expect(panel._aiTab).toBe("local");
  await panel._modal.onClose();
  expect(panel._createState.request).toBe("A fox");
});

test("settings edit any service while the default stays separate", async () => {
  const { panel, requests } = harness({ provider: "local", configured: true, ready: { local: true } });
  await panel._openAiSettings();
  expect(panel._aiTab).toBe("local");
  panel._aiTab = "openrouter";
  panel._aiDraft.openrouter_key = "sk-or-v1-new";
  await panel._saveAiSettings();
  const saved = JSON.parse(requests.at(-1).options.body);
  expect(saved.provider).toBe("local");
  expect(saved.openrouter_key).toBe("sk-or-v1-new");
});

test("Create remembers this browser's service and model, and falls back when it is not ready", async () => {
  const { panel, ai, requests } = harness({
    provider: "openrouter", configured: true, ready: { openrouter: true, local: true },
    local: { url: "http://gpu", api: "sdwebui", model: "sdxl", steps: null },
  });
  Object.assign(panel, { _aiModels: { entryId: "first", list: [] }, _loadSources: async () => {}, _loadCreatePreview: () => {}, _refreshCreate: () => {} });
  await panel._openCreate();
  expect(panel._createState.service).toBe("openrouter");
  panel._pickCreateService("local");
  panel._createState.request = "A fox";
  await panel._runCreate();
  const body = JSON.parse(requests.find((request) => request.path === "ai/create").options.body);
  expect([body.provider, body.model]).toEqual(["local", "sdxl"]);
  panel._createState.phase = "compose";
  await panel._openCreate();
  expect(panel._createState.service).toBe("local");
  ai.ready.local = false;
  await panel._openCreate();
  expect(panel._createState.service).toBe("openrouter");
});

test("dictation sends buffered audio after run-start and inserts the words at the cursor", () => {
  const { panel } = harness();
  const sent = [];
  const state = { phase: "compose", request: "A fox under a lamp", dictation: "listening" };
  const run = { state, start: 5, end: 5, buffer: [], handler: null, stopped: false, unsubscribe: async () => {} };
  Object.assign(panel, {
    _createState: state, _dictationRun: run, _refreshCreate: () => {},
    _hass: { connection: { socket: { readyState: 1, send: (data) => sent.push([...data]) } } },
  });
  panel._dictationAudio(run, new Int16Array([1, -2]));
  expect(sent).toEqual([]);
  panel._dictationEvent(run, { type: "run-start", data: { runner_data: { stt_binary_handler_id: 7 } } });
  expect(sent).toEqual([[7, 1, 0, 254, 255]]);
  panel._dictationEvent(run, { type: "stt-vad-end" });
  expect(sent.at(-1)).toEqual([7]);
  expect(state.dictation).toBe("writing");
  panel._dictationEvent(run, { type: "stt-end", data: { stt_output: { text: "reading " } } });
  expect(state.request).toBe("A fox reading under a lamp");
  expect(state.dictation).toBe(null);
  expect(panel._dictationRun).toBe(null);
});
