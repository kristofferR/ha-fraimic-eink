import { test, expect } from "bun:test";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../custom_components/fraimic/frontend/fraimic-panel.js", import.meta.url), "utf8");
const voice = (entryId, patch = {}) => ({ entry_id: entryId, name: entryId, available: true, mode: "fixed", image: "", stt: "", language: "", agent: "homeassistant", ai_task_entity: "", ...patch });

function harness(patch = {}) {
  let Panel;
  runInNewContext(source, {
    HTMLElement: class {}, customElements: { define: (_name, cls) => { Panel = cls; } },
    structuredClone, URLSearchParams, queueMicrotask, URL,
  });
  const ai = {
    provider: "", configured: false, openrouter: { has_key: false, model: "model" },
    local: { url: "http://gpu", api: "openai", model: "", steps: null },
    ai_task_entity: "", style: "none", styles: [{ id: "none", name: "None", template: "{prompt}" }],
    builtin_styles: {}, rewrite_entity: "", voice: [voice("first"), voice("second")],
    choices: { image_entities: [], data_entities: [], stt: [], images: [], agents: [], language: "en" },
    ...patch,
  };
  const requests = [], notices = [];
  const panel = Object.create(Panel.prototype);
  Object.assign(panel, {
    _selectedFrameId: "first", _ai: ai,
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
  const { panel } = harness({ provider: "openrouter", configured: true });
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
