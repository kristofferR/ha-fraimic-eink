import { test, expect } from "bun:test";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../custom_components/fraimic/frontend/fraimic-panel.js", import.meta.url), "utf8");
const voice = (entryId, patch = {}) => ({ entry_id: entryId, name: entryId, available: true, mode: "fixed", image: "", stt: "", language: "", agent: "homeassistant", ai_task_entity: "", ...patch });

function harness(patch = {}, globals = {}) {
  let Panel;
  const stored = new Map();
  runInNewContext(source, {
    HTMLElement: class {}, customElements: { define: (_name, cls) => { Panel = cls; } },
    structuredClone, URLSearchParams, queueMicrotask, URL, setTimeout, clearTimeout,
    localStorage: { getItem: (key) => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, String(value)) },
    ...globals,
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

function bindFields(panel, fields) {
  panel.shadowRoot = {
    querySelectorAll: (selector) => selector.split(", ").flatMap((part) => fields[part] ? [fields[part]] : []),
    querySelector: (selector) => fields[selector],
    getElementById: (id) => fields[`#${id}`],
  };
  for (const field of Object.values(fields)) field.addEventListener = (event, handler) => { field[event] = handler; };
}

test("service readiness follows checks and discards results for an edited key", async () => {
  const { panel } = harness({ ready: { local: true, openrouter: true } });
  panel._aiServiceChanged = () => {};
  await panel._openAiSettings();
  expect(panel._aiDraftReady("local")).toBe(true);
  const key = { value: "invalid" };
  bindFields(panel, { "#ai-key": key });
  panel._bindAiSettings();
  panel._aiTab = "openrouter";
  const checking = Promise.withResolvers();
  panel._api = () => checking.promise;
  key.input();
  expect(panel._aiDraftReady("openrouter")).toBe(false);
  const pending = panel._checkAi();
  key.value = "replacement";
  key.input();
  expect(panel._aiCheck).toBe(null);
  checking.resolve({ ok: true });
  await pending;
  expect(panel._aiCheck).toBe(null);
  expect(panel._aiDraftReady("openrouter")).toBe(false);
  panel._api = async () => ({ ok: false, error: "Invalid key" });
  await panel._checkAi();
  expect(panel._aiDraftReady("openrouter")).toBe(false);
  panel._api = async () => ({ ok: true });
  await panel._checkAi();
  expect(panel._aiDraftReady("openrouter")).toBe(true);
});

test("editing the server address requires detecting its API before saving it as default", async () => {
  const { panel, requests, notices } = harness({ provider: "local", ready: { local: true } });
  panel._aiServiceChanged = () => {};
  await panel._openAiSettings();
  const url = { value: "http://another-gpu" };
  bindFields(panel, { "#ai-url": url });
  panel._bindAiSettings();
  panel._aiCheck = { service: "local", ok: true };
  url.input();
  expect(panel._aiCheck).toBe(null);
  expect(panel._aiDraft.local_api).toBe("");
  expect(panel._aiDraftReady("local")).toBe(false);
  await panel._saveAiSettings();
  expect(requests.some(({ path, options }) => path === "ai/settings" && options)).toBe(false);
  expect(notices.at(-1)).toContain("Connect to the local server");
});

test("an empty edited prompt disables Create and prevents submitting the original request", async () => {
  const { panel, requests } = harness();
  panel._modal = { className: "create-dialog" };
  panel._createState = { phase: "compose", service: "local", request: "A fox", editing: true, prompt: "A fox" };
  const prompt = { value: "   " }, button = {};
  bindFields(panel, { "#create-prompt": prompt, "[data-create-run]": button });
  panel._bindCreate();
  prompt.input();
  expect(button.disabled).toBe(true);
  expect(panel._createActions()).toContain('data-create-run disabled');
  await panel._runCreate();
  expect(requests).toEqual([]);
  prompt.value = "An owl";
  prompt.input();
  expect(button.disabled).toBe(false);
});

test("a failed pipeline load can be retried from the microphone", async () => {
  const { panel, notices } = harness({}, {
    isSecureContext: true, AudioWorkletNode: class {},
    navigator: { mediaDevices: { getUserMedia: async () => { throw new Error("Microphone requested"); } } },
  });
  let attempts = 0;
  panel._hass = { callWS: async () => {
    if (++attempts === 1) throw new Error("offline");
    return { pipelines: [{ id: "speech", stt_engine: "stt.whisper" }] };
  } };
  panel._modal = { className: "create-dialog" };
  panel._createState = { phase: "compose", request: "" };
  panel._refreshCreate = () => {};
  await panel._startDictation();
  expect(notices.at(-1)).toContain("Could not load Assist pipelines");
  await panel._startDictation();
  expect(attempts).toBe(2);
  expect(notices.at(-1)).toBe("Microphone requested");
});

test("opening Create and starting dictation share the pending pipeline load", async () => {
  const loading = Promise.withResolvers();
  let loads = 0;
  const { panel, notices } = harness({}, {
    isSecureContext: true, AudioWorkletNode: class {},
    navigator: { mediaDevices: { getUserMedia: async () => { throw new Error("Microphone requested"); } } },
  });
  Object.assign(panel, {
    _hass: { callWS: () => { loads++; return loading.promise; } },
    _modal: { className: "create-dialog" }, _createState: { phase: "compose", request: "" },
    _refreshCreate: () => {},
  });
  const background = panel._loadPipelines();
  const start = panel._startDictation();
  expect(loads).toBe(1);
  loading.resolve({ pipelines: [{ id: "speech", stt_engine: "stt.whisper" }] });
  await Promise.all([background, start]);
  expect(panel._dictationPipeline().id).toBe("speech");
  expect(panel._pipelinesError).toBe("");
  expect(notices).toEqual(["Microphone requested"]);
});

test("dictation resumes a suspended audio context before connecting the recorder", async () => {
  const resumed = Promise.withResolvers(), resuming = Promise.withResolvers();
  let connected = false;
  const { panel } = harness({}, {
    navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) } },
    AudioContext: class {
      state = "suspended";
      audioWorklet = { addModule: async () => {} };
      resume() { resuming.resolve(); return resumed.promise; }
      createMediaStreamSource() { return { connect: () => { connected = true; } }; }
      close() { return Promise.resolve(); }
    },
    AudioWorkletNode: class { port = {}; }, Blob,
  });
  Object.assign(panel, {
    _createState: { phase: "compose", request: "" }, _modal: { className: "create-dialog" },
    _pipelines: { list: [{ id: "speech" }] }, _dictationProblem: () => "", _refreshCreate: () => {},
    _hass: { connection: { subscribeMessage: async () => () => {} } },
  });
  const start = panel._startDictation();
  await resuming.promise;
  expect(connected).toBe(false);
  resumed.resolve();
  await start;
  expect(connected).toBe(true);
  panel._cancelDictation();
});

test.each([true, false])("stopping with a pending subscription delivers captured audio (handler ready: %s)", async (handlerReady) => {
  const subscribing = Promise.withResolvers(), subscription = Promise.withResolvers();
  const sent = [];
  let stopped = false, closed = false, unsubscribed = false;
  const { panel } = harness({}, {
    navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => { stopped = true; } }] }) } },
    AudioContext: class {
      sampleRate = 48000;
      audioWorklet = { addModule: async () => {} };
      createMediaStreamSource() { return { connect: () => {} }; }
      close() { closed = true; return Promise.resolve(); }
    },
    AudioWorkletNode: class { port = {}; }, Blob,
  });
  Object.assign(panel, {
    _createState: { phase: "compose", request: "" }, _modal: { className: "create-dialog" },
    _pipelines: { list: [{ id: "speech" }] }, _dictationProblem: () => "", _refreshCreate: () => {},
    _hass: { connection: {
      subscribeMessage: () => { subscribing.resolve(); return subscription.promise; },
      socket: { readyState: 1, send: (data) => sent.push([...data]) },
    } },
  });
  const start = panel._startDictation();
  await subscribing.promise;
  const run = panel._dictationRun;
  panel._dictationAudio(run, new Int16Array([1, -2]));
  const ready = () => panel._dictationEvent(run, { type: "run-start", data: { runner_data: { stt_binary_handler_id: 7 } } });
  if (handlerReady) ready();
  panel._stopDictation();
  expect(stopped && closed).toBe(true);
  expect(panel._dictationRun).toBe(run);
  expect(run.state.dictation).toBe("writing");
  subscription.resolve(() => { unsubscribed = true; });
  await start;
  if (!handlerReady) ready();
  expect(sent).toEqual([[7, 1, 0, 254, 255], [7]]);
  panel._dictationEvent(run, { type: "stt-end", data: { stt_output: { text: "A fox" } } });
  expect(panel._createState.request).toBe("A fox");
  expect(panel._dictationRun).toBe(null);
  expect(unsubscribed).toBe(true);
});

test.each([2, 3])("a disconnected socket ends dictation and releases the microphone: %s", (readyState) => {
  const { panel, notices } = harness();
  let stopped = false, unsubscribed = false;
  const state = { dictation: "listening" };
  const run = { state, handler: 7, stream: { getTracks: () => [{ stop: () => { stopped = true; } }] }, unsubscribe: () => { unsubscribed = true; } };
  Object.assign(panel, {
    _createState: state, _dictationRun: run, _refreshCreate: () => {},
    _hass: { connection: { socket: { readyState } } },
  });
  panel._stopDictation();
  expect(stopped).toBe(true);
  expect(unsubscribed).toBe(true);
  expect(panel._dictationRun).toBe(null);
  expect(state.dictation).toBe(null);
  expect(run.timer).toBeUndefined();
  expect(notices.at(-1)).toContain("Connection to Home Assistant lost");
});

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

test.each(["closed", "settings", "replaced", "generating"])("dictation skips a pending start when Create changes: %s", async (change) => {
  const { panel, notices } = harness();
  const loading = Promise.withResolvers();
  Object.assign(panel, {
    _createState: { phase: "compose", request: "A fox" },
    _modal: { className: "create-dialog" },
    _loadPipelines: () => loading.promise,
    _dictationProblem: () => "Microphone requested",
  });
  const start = panel._startDictation();
  if (change === "closed") panel._modal = null;
  else if (change === "settings") panel._modal = { className: "ai-dialog" };
  else if (change === "replaced") panel._createState = { phase: "compose", request: "" };
  else panel._createState.phase = "generating";
  loading.resolve();
  await start;
  expect(notices).toEqual([]);
  expect(panel._dictationRun).toBeUndefined();
});

test("concurrent dictation starts during pipeline loading request the microphone once", async () => {
  const microphone = Promise.withResolvers();
  let requests = 0;
  const { panel } = harness({}, {
    navigator: { mediaDevices: { getUserMedia: () => { requests++; return microphone.promise; } } },
  });
  const loading = Promise.withResolvers();
  Object.assign(panel, {
    _createState: { phase: "compose", request: "A fox" },
    _modal: { className: "create-dialog" },
    _loadPipelines: () => loading.promise,
    _dictationProblem: () => "",
    _refreshCreate: () => {},
  });
  const first = panel._startDictation();
  const second = panel._startDictation();
  loading.resolve();
  await second;
  expect(requests).toBe(1);
  let stops = 0;
  panel._stopDictation();
  expect(panel._dictationRun).toBe(null);
  expect(panel._createState.dictation).toBe(null);
  microphone.resolve({ getTracks: () => [{ stop: () => { stops++; } }] });
  await first;
  expect(stops).toBe(1);
  expect(panel._dictationRun).toBe(null);
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

test("Fraimic's AI voice mode saves without speech to text", async () => {
  const { panel, requests, notices } = harness();
  await panel._openAiSettings();
  panel._aiDraft.voice.first.mode = "fraimic";
  expect(panel._aiVoiceRow(panel._ai.voice[0])).not.toContain("Speech to text");
  await panel._saveAiSettings();
  expect(notices).toEqual(["AI art settings saved."]);
  expect(JSON.parse(requests.at(-1).options.body).voice.first).toMatchObject({ mode: "fraimic", stt: "", language: "" });
});
