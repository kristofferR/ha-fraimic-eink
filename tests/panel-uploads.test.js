import { test, expect } from "bun:test";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../custom_components/fraimic/frontend/fraimic-panel.js", import.meta.url), "utf8");

function harness({ fail = false } = {}) {
  let Panel;
  runInNewContext(source, {
    HTMLElement: class {}, customElements: { define: (_name, cls) => { Panel = cls; } },
    FormData, queueMicrotask, URLSearchParams,
  });
  const panel = Object.create(Panel.prototype);
  let buttons = [];
  const requests = [];
  Object.assign(panel, {
    _colours: new Set(["red"]), _artist: "An artist", _era: "1900", _query: "old search",
    _fits: true, _rendersWell: true, _route: "browse", _selectedSource: "all",
    _detailGeneration: 0, _sources: [], _sourceOrder: [], _sourceChildren: new Map(),
    _sourceNodeMeta: new Map(), _sourceStatus: new Map(), _expandedSources: new Set(), _playlists: [],
    shadowRoot: {
      host: {}, getElementById: () => null, querySelector: () => null,
      querySelectorAll: (selector) => selector === "[data-close-modal]" ? buttons : [],
    },
    _render() {
      // Replacing the DOM loses all handlers, just as a gallery refresh does.
      buttons = this._modal ? [new EventTarget()] : [];
      if (this._modal?.actions) buttons.push(new EventTarget());
      this._bind();
    },
    _hass: { fetchWithAuth: async (path, options) => {
      requests.push({ path, options });
      return { ok: !fail, json: async () => fail ? { message: "Invalid image" } : { width: 1280, height: 964 } };
    } },
    _loadSources: async () => {},
    _loadGallery: async () => panel._render(),
    _notify: () => {},
  });
  return { panel, requests, buttons: () => buttons };
}

test("Done still closes the upload dialog after the gallery replaces its buttons", async () => {
  const h = harness();
  await h.panel._uploadFiles([new File(["image"], "photo.jpg", { type: "image/jpeg" })]);
  expect(h.requests).toHaveLength(1);
  expect(h.requests[0].options.body.get("file").name).toBe("photo.jpg");
  expect(h.panel._modal.body).toContain("Saved · 1280 × 964");
  h.panel._render();
  const [close, done] = h.buttons();
  expect(typeof close.onclick).toBe("function");
  expect(typeof done.onclick).toBe("function");
  done.onclick();
  expect(h.panel._modal).toBeNull();
  expect(h.panel._selectedSource).toBe("saved");
  expect(h.panel._selectedBrowseId).toBe("uploads");
  expect(h.panel._query).toBe("");
  expect(h.panel._fits).toBe(false);
  expect(h.panel._rendersWell).toBe(false);
  expect(h.panel._colours.size).toBe(0);
  expect(h.panel._artist).toBe("");
  expect(h.panel._era).toBe("");
});

test("failed uploads remain visible and dismissible without changing the source", async () => {
  const h = harness({ fail: true });
  await h.panel._uploadFiles([new File(["bad"], "broken.jpg")]);
  expect(h.panel._modal.body).toContain("Invalid image");
  expect(h.panel._selectedSource).toBe("all");
  h.buttons()[1].onclick();
  expect(h.panel._modal).toBeNull();
});

test("Uploads is a top-level folder even with My library collapsed", () => {
  const { panel } = harness();
  panel._selectedSource = "saved";
  panel._selectedBrowseId = "uploads";
  panel._sourceChildren.set(panel._sourceNodeKey("saved"), [{ id: "uploads", title: "Uploads", count: 2 }]);
  const html = panel._sourceRailTemplate();
  expect(html).toContain('data-browse-id="uploads" data-source-title="Uploads" aria-current="true"');
  expect(html).toContain('<span>Uploads</span><span class="source-meta">2</span>');
});
