/*
 * Fraimic sidebar panel.
 *
 * Vanilla web component (no build step, no external deps). Talks to the
 * integration's authenticated /api/fraimic/* endpoints via hass.fetchWithAuth
 * and signs <img> URLs with auth/sign_path so thumbnails work in plain img
 * tags. Styled exclusively with HA theme variables so light/dark both work.
 */

const API = "/api/fraimic";

class FraimicPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "library";
    this._images = [];
    this._albums = [];
    this._frames = [];
    this._scenes = [];
    this._packs = [];
    this._albumFilter = "";
    this._signedCache = new Map();
    this._initialized = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._renderShell();
      this._refreshAll();
    }
  }

  set narrow(narrow) {
    this._narrow = narrow;
  }

  /* ------------------------------------------------------------- helpers */

  async _api(path, options = {}) {
    const resp = await this._hass.fetchWithAuth(`${API}/${path}`, options);
    let body = null;
    try {
      body = await resp.json();
    } catch (_err) {
      /* non-JSON error body */
    }
    if (!resp.ok) {
      throw new Error((body && body.message) || `${resp.status} ${resp.statusText}`);
    }
    return body;
  }

  async _signedUrl(path) {
    const cached = this._signedCache.get(path);
    if (cached && Date.now() - cached.ts < 45 * 60 * 1000) return cached.url;
    const result = await this._hass.callWS({
      type: "auth/sign_path",
      path,
      expires: 3600,
    });
    this._signedCache.set(path, { url: result.path, ts: Date.now() });
    return result.path;
  }

  _setImgSrc(img, path) {
    this._signedUrl(path)
      .then((url) => {
        img.src = url;
      })
      .catch(() => {
        img.alt = "unavailable";
      });
  }

  _toast(message, isError = false) {
    const bar = this.shadowRoot.getElementById("toast");
    bar.textContent = message;
    bar.className = isError ? "show error" : "show";
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      bar.className = "";
    }, 4000);
  }

  _el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of children) node.appendChild(child);
    return node;
  }

  _effectiveSize(frame) {
    // Aspect the user sees on the wall: mount rotation swaps the axes.
    const rotated = frame.rotation === 90 || frame.rotation === 270;
    return {
      width: rotated ? frame.height : frame.width,
      height: rotated ? frame.width : frame.height,
    };
  }

  _frameLabel(frame) {
    return `${frame.title} (${frame.width}×${frame.height})`;
  }

  /* ---------------------------------------------------------------- data */

  async _refreshAll() {
    await Promise.all([
      this._loadLibrary(),
      this._loadFrames(),
      this._loadScenes(),
      this._loadPacks(),
    ]).catch((err) => this._toast(err.message, true));
    this._renderTab();
  }

  async _loadLibrary() {
    const data = await this._api("library");
    this._images = data.images;
    this._albums = data.albums;
  }

  async _loadFrames() {
    this._frames = (await this._api("frames")).frames;
  }

  async _loadScenes() {
    this._scenes = (await this._api("scenes")).scenes;
  }

  async _loadPacks() {
    this._packs = (await this._api("packs")).packs;
  }

  /* --------------------------------------------------------------- shell */

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          overflow: auto;
          background: var(--primary-background-color);
          color: var(--primary-text-color);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        header {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 0 16px;
          height: 56px;
          background: var(--app-header-background-color, var(--primary-color));
          color: var(--app-header-text-color, var(--text-primary-color, #fff));
        }
        header h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; }
        nav {
          display: flex;
          gap: 4px;
          padding: 8px 16px 0;
          border-bottom: 1px solid var(--divider-color);
          flex-wrap: wrap;
        }
        nav button {
          background: none;
          border: none;
          border-bottom: 2px solid transparent;
          color: var(--secondary-text-color);
          font: inherit;
          font-size: 14px;
          padding: 8px 12px;
          cursor: pointer;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        nav button.active {
          color: var(--primary-color);
          border-bottom-color: var(--primary-color);
        }
        main { padding: 16px; }
        .toolbar {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
          margin-bottom: 16px;
        }
        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 16px;
        }
        .card {
          background: var(--card-background-color);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 1px 4px rgba(0,0,0,0.2));
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }
        .card .thumbwrap {
          aspect-ratio: 4 / 3;
          background: var(--secondary-background-color);
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
        }
        .card img { width: 100%; height: 100%; object-fit: cover; display: block; }
        .card .body { padding: 10px 12px; flex: 1; }
        .card .title {
          font-size: 14px;
          font-weight: 500;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .card .sub { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
        .card .actions {
          display: flex;
          gap: 4px;
          padding: 4px 8px 8px;
          flex-wrap: wrap;
        }
        button.btn {
          background: none;
          border: none;
          color: var(--primary-color);
          font: inherit;
          font-size: 13px;
          font-weight: 500;
          text-transform: uppercase;
          padding: 6px 8px;
          border-radius: 4px;
          cursor: pointer;
        }
        button.btn:hover { background: rgba(var(--rgb-primary-color, 33,150,243), 0.1); }
        button.btn.danger { color: var(--error-color); }
        button.btn.raised {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }
        button.btn:disabled { opacity: 0.4; cursor: default; }
        select, input[type="text"] {
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          padding: 6px 8px;
          font: inherit;
          font-size: 13px;
        }
        .chip {
          display: inline-block;
          font-size: 11px;
          padding: 2px 8px;
          border-radius: 10px;
          background: var(--secondary-background-color);
          color: var(--secondary-text-color);
          margin: 2px 2px 0 0;
        }
        .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }
        .dot.on { background: var(--success-color, #4caf50); }
        .dot.off { background: var(--error-color, #f44336); }
        .empty {
          text-align: center;
          color: var(--secondary-text-color);
          padding: 48px 16px;
        }
        #toast {
          position: fixed;
          bottom: 16px;
          left: 50%;
          transform: translateX(-50%) translateY(80px);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: 6px;
          box-shadow: 0 3px 12px rgba(0,0,0,0.4);
          padding: 12px 20px;
          max-width: 80vw;
          transition: transform 0.2s ease;
          z-index: 20;
        }
        #toast.show { transform: translateX(-50%) translateY(0); }
        #toast.error { border-left: 4px solid var(--error-color, #f44336); }
        .overlay {
          position: fixed;
          inset: 0;
          background: rgba(0,0,0,0.55);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 10;
          padding: 16px;
        }
        .dialog {
          background: var(--card-background-color);
          border-radius: 12px;
          box-shadow: 0 6px 30px rgba(0,0,0,0.5);
          max-width: min(920px, 96vw);
          max-height: 92vh;
          overflow: auto;
          padding: 20px;
          box-sizing: border-box;
        }
        .dialog h2 { margin: 0 0 12px; font-size: 18px; font-weight: 500; }
        .dialog .row { display: flex; gap: 8px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
        .dialog .row label { min-width: 140px; font-size: 14px; }
        .dialog .dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
        /* Crop editor */
        #cropStage {
          position: relative;
          user-select: none;
          touch-action: none;
          display: inline-block;
          max-width: 100%;
        }
        #cropStage img { display: block; max-width: 100%; max-height: 60vh; }
        #cropBox {
          position: absolute;
          border: 2px solid var(--primary-color);
          box-shadow: 0 0 0 9999px rgba(0,0,0,0.45);
          cursor: move;
          box-sizing: border-box;
        }
        .handle {
          position: absolute;
          width: 16px;
          height: 16px;
          background: var(--primary-color);
          border-radius: 50%;
          z-index: 2;
        }
        .handle.nw { top: -8px; left: -8px; cursor: nwse-resize; }
        .handle.ne { top: -8px; right: -8px; cursor: nesw-resize; }
        .handle.sw { bottom: -8px; left: -8px; cursor: nesw-resize; }
        .handle.se { bottom: -8px; right: -8px; cursor: nwse-resize; }
        .mini { width: 44px; height: 33px; object-fit: cover; border-radius: 4px; vertical-align: middle; margin-right: 8px; background: var(--secondary-background-color); }
        a { color: var(--primary-color); }
      </style>
      <header><h1>Fraimic</h1></header>
      <nav id="tabs"></nav>
      <main id="content"></main>
      <div id="toast"></div>
      <div id="modal"></div>
    `;
    const tabs = [
      ["library", "Library"],
      ["frames", "Frames"],
      ["scenes", "Scenes"],
      ["packs", "Art Packs"],
    ];
    const nav = this.shadowRoot.getElementById("tabs");
    for (const [id, label] of tabs) {
      nav.appendChild(
        this._el("button", {
          id: `tab-${id}`,
          text: label,
          onclick: () => {
            this._tab = id;
            this._renderTab();
          },
        })
      );
    }
  }

  _renderTab() {
    for (const button of this.shadowRoot.querySelectorAll("nav button")) {
      button.classList.toggle("active", button.id === `tab-${this._tab}`);
    }
    const content = this.shadowRoot.getElementById("content");
    content.innerHTML = "";
    if (this._tab === "library") this._renderLibrary(content);
    else if (this._tab === "frames") this._renderFrames(content);
    else if (this._tab === "scenes") this._renderScenes(content);
    else this._renderPacks(content);
  }

  /* ------------------------------------------------------------- library */

  _renderLibrary(root) {
    const toolbar = this._el("div", { class: "toolbar" });

    const upload = this._el("button", {
      class: "btn raised",
      text: "Upload images",
      onclick: () => fileInput.click(),
    });
    const fileInput = this._el("input", { type: "file", accept: "image/*", style: "display:none" });
    fileInput.multiple = true;
    fileInput.addEventListener("change", () => this._uploadFiles(fileInput.files));

    const filter = this._el("select", {
      onchange: (ev) => {
        this._albumFilter = ev.target.value;
        this._renderTab();
      },
    });
    filter.appendChild(this._el("option", { value: "", text: "All albums" }));
    for (const album of this._albums) {
      const option = this._el("option", { value: album, text: album });
      if (album === this._albumFilter) option.selected = true;
      filter.appendChild(option);
    }

    const renameBtn = this._el("button", {
      class: "btn",
      text: "Rename album",
      onclick: () => this._renameAlbum(),
    });
    const deleteBtn = this._el("button", {
      class: "btn danger",
      text: "Delete album",
      onclick: () => this._deleteAlbum(),
    });
    toolbar.append(upload, fileInput, filter);
    if (this._albumFilter) toolbar.append(renameBtn, deleteBtn);
    root.appendChild(toolbar);

    const images = this._albumFilter
      ? this._images.filter((image) => image.albums.includes(this._albumFilter))
      : this._images;
    if (!images.length) {
      root.appendChild(
        this._el("div", {
          class: "empty",
          text: "No images yet. Upload some, or install an art pack.",
        })
      );
      return;
    }
    const grid = this._el("div", { class: "grid" });
    for (const image of images) grid.appendChild(this._libraryCard(image));
    root.appendChild(grid);
  }

  _libraryCard(image) {
    const img = this._el("img", { loading: "lazy" });
    this._setImgSrc(img, `${API}/library/thumb/${image.image_id}`);
    const chips = this._el("div", {}, image.albums.map((album) =>
      this._el("span", { class: "chip", text: album })
    ));
    const body = this._el("div", { class: "body" }, [
      this._el("div", { class: "title", text: image.filename }),
      this._el("div", {
        class: "sub",
        text: image.width && image.height ? `${image.width}×${image.height}` : "",
      }),
      chips,
    ]);
    const actions = this._el("div", { class: "actions" }, [
      this._el("button", {
        class: "btn",
        text: "Send",
        onclick: () => this._sendImage(image),
      }),
      this._el("button", {
        class: "btn",
        text: "Crop",
        onclick: () => this._openCropEditor(image),
      }),
      this._el("button", {
        class: "btn",
        text: "Albums",
        onclick: () => this._editAlbums(image),
      }),
      this._el("button", {
        class: "btn danger",
        text: "Delete",
        onclick: () => this._deleteImage(image),
      }),
    ]);
    return this._el("div", { class: "card" }, [
      this._el("div", { class: "thumbwrap" }, [img]),
      body,
      actions,
    ]);
  }

  async _uploadFiles(files) {
    if (!files || !files.length) return;
    let done = 0;
    for (const file of files) {
      const form = new FormData();
      form.append("file", file, file.name);
      if (this._albumFilter) form.append("album", this._albumFilter);
      try {
        await this._api("library/upload", { method: "POST", body: form });
        done += 1;
      } catch (err) {
        this._toast(`${file.name}: ${err.message}`, true);
      }
    }
    if (done) this._toast(`Uploaded ${done} image${done === 1 ? "" : "s"}`);
    await this._loadLibrary();
    this._renderTab();
  }

  async _sendImage(image) {
    const frame = await this._pickFrame("Send to frame");
    if (!frame) return;
    const targets = frame === "all" ? this._frames : [frame];
    this._toast("Sending… the e-ink refresh takes ~30 s");
    try {
      const result = await this._api("library/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_id: image.image_id,
          entry_ids: targets.map((f) => f.entry_id),
        }),
      });
      const failed = Object.values(result.results).filter((r) => !r.ok);
      this._toast(
        failed.length
          ? `Sent with ${failed.length} failure(s): ${failed[0].error}`
          : "Sent ✓",
        Boolean(failed.length)
      );
    } catch (err) {
      this._toast(err.message, true);
    }
  }

  _pickFrame(title) {
    if (!this._frames.length) {
      this._toast("No frames are loaded", true);
      return Promise.resolve(null);
    }
    if (this._frames.length === 1) return Promise.resolve(this._frames[0]);
    return new Promise((resolve) => {
      const select = this._el("select");
      select.appendChild(this._el("option", { value: "all", text: "All frames" }));
      this._frames.forEach((frame, index) => {
        select.appendChild(this._el("option", { value: String(index), text: this._frameLabel(frame) }));
      });
      this._openDialog(title, [this._el("div", { class: "row" }, [select])], [
        this._el("button", { class: "btn", text: "Cancel", onclick: () => { this._closeDialog(); resolve(null); } }),
        this._el("button", {
          class: "btn raised",
          text: "Send",
          onclick: () => {
            this._closeDialog();
            resolve(select.value === "all" ? "all" : this._frames[Number(select.value)]);
          },
        }),
      ]);
    });
  }

  async _editAlbums(image) {
    const current = image.albums.join(", ");
    const answer = prompt("Albums (comma-separated):", current);
    if (answer === null) return;
    const albums = answer.split(",").map((a) => a.trim()).filter(Boolean);
    try {
      await this._api(`library/image/${image.image_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ albums }),
      });
      await this._loadLibrary();
      this._renderTab();
    } catch (err) {
      this._toast(err.message, true);
    }
  }

  async _deleteImage(image) {
    if (!confirm(`Delete "${image.filename}" from the library?`)) return;
    try {
      await this._api(`library/image/${image.image_id}`, { method: "DELETE" });
      await Promise.all([this._loadLibrary(), this._loadScenes()]);
      this._renderTab();
      this._toast("Deleted");
    } catch (err) {
      this._toast(err.message, true);
    }
  }

  async _renameAlbum() {
    const name = prompt(`Rename album "${this._albumFilter}" to:`, this._albumFilter);
    if (!name || name === this._albumFilter) return;
    try {
      await this._api("library/album", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "rename", name: this._albumFilter, new_name: name }),
      });
      this._albumFilter = name;
      await this._loadLibrary();
      this._renderTab();
    } catch (err) {
      this._toast(err.message, true);
    }
  }

  async _deleteAlbum() {
    if (!confirm(`Delete album "${this._albumFilter}"? Images stay in the library.`)) return;
    try {
      await this._api("library/album", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete", name: this._albumFilter }),
      });
      this._albumFilter = "";
      await this._loadLibrary();
      this._renderTab();
    } catch (err) {
      this._toast(err.message, true);
    }
  }

  /* --------------------------------------------------------- crop editor */

  async _openCropEditor(image) {
    if (!this._frames.length) {
      this._toast("No frames are loaded", true);
      return;
    }
    let frame = this._frames[0];

    const img = this._el("img", { draggable: "false" });
    const box = this._el("div", { id: "cropBox" });
    for (const corner of ["nw", "ne", "sw", "se"]) {
      box.appendChild(this._el("div", { class: `handle ${corner}` }));
    }
    const stage = this._el("div", { id: "cropStage" }, [img, box]);

    const frameSelect = this._el("select", {
      onchange: () => {
        frame = this._frames[Number(frameSelect.value)];
        placeBox(this._initialBox(image, frame));
      },
    });
    this._frames.forEach((f, index) => {
      frameSelect.appendChild(this._el("option", { value: String(index), text: this._frameLabel(f) }));
    });

    // Normalized box state [x0, y0, x1, y1]
    let norm = null;
    const aspect = () => {
      const size = this._effectiveSize(frame);
      return size.width / size.height;
    };

    const placeBox = (next) => {
      norm = next;
      const rect = { w: img.clientWidth, h: img.clientHeight };
      box.style.left = `${norm[0] * rect.w}px`;
      box.style.top = `${norm[1] * rect.h}px`;
      box.style.width = `${(norm[2] - norm[0]) * rect.w}px`;
      box.style.height = `${(norm[3] - norm[1]) * rect.h}px`;
    };

    img.addEventListener("load", () => placeBox(this._initialBox(image, frame)));
    this._setImgSrc(img, `${API}/library/image/${image.image_id}`);

    // Pointer interactions: move (box) or aspect-locked resize (handles).
    let gesture = null;
    const onDown = (ev) => {
      ev.preventDefault();
      const handle = ev.target.classList.contains("handle") ? ev.target : null;
      gesture = {
        corner: handle ? handle.classList[1] : null,
        startX: ev.clientX,
        startY: ev.clientY,
        startNorm: [...norm],
      };
      box.setPointerCapture(ev.pointerId);
    };
    const onMove = (ev) => {
      if (!gesture) return;
      const rect = { w: img.clientWidth, h: img.clientHeight };
      const dx = (ev.clientX - gesture.startX) / rect.w;
      const dy = (ev.clientY - gesture.startY) / rect.h;
      const [sx0, sy0, sx1, sy1] = gesture.startNorm;
      const imgAspect = rect.w / rect.h; // normalized-space aspect correction
      const boxAspect = aspect() / imgAspect; // (norm width) / (norm height)

      if (!gesture.corner) {
        // Move, clamped inside the image.
        const w = sx1 - sx0;
        const h = sy1 - sy0;
        const x0 = Math.min(Math.max(sx0 + dx, 0), 1 - w);
        const y0 = Math.min(Math.max(sy0 + dy, 0), 1 - h);
        placeBox([x0, y0, x0 + w, y0 + h]);
        return;
      }
      // Resize anchored at the opposite corner, width drives height.
      const anchorX = gesture.corner.includes("w") ? sx1 : sx0;
      const anchorY = gesture.corner.includes("n") ? sy1 : sy0;
      const movingX = (gesture.corner.includes("w") ? sx0 : sx1) + dx;
      let w = Math.abs(movingX - anchorX);
      // Clamp so both dimensions stay inside [0,1] from the anchor.
      const maxW = Math.min(
        gesture.corner.includes("w") ? anchorX : 1 - anchorX,
        (gesture.corner.includes("n") ? anchorY : 1 - anchorY) * boxAspect
      );
      w = Math.min(Math.max(w, 0.05), maxW);
      const h = w / boxAspect;
      const x0 = gesture.corner.includes("w") ? anchorX - w : anchorX;
      const y0 = gesture.corner.includes("n") ? anchorY - h : anchorY;
      placeBox([x0, y0, x0 + w, y0 + h]);
    };
    const onUp = () => {
      gesture = null;
    };
    box.addEventListener("pointerdown", onDown);
    box.addEventListener("pointermove", onMove);
    box.addEventListener("pointerup", onUp);
    box.addEventListener("pointercancel", onUp);

    const save = async () => {
      try {
        await this._api(`library/image/${image.image_id}/crop`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ width: frame.width, height: frame.height, box: norm }),
        });
        this._closeDialog();
        await this._loadLibrary();
        this._renderTab();
        this._toast("Crop saved — cached renders for this size were invalidated");
      } catch (err) {
        this._toast(err.message, true);
      }
    };
    const clear = async () => {
      try {
        await this._api(`library/image/${image.image_id}/crop`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ width: frame.width, height: frame.height, box: null }),
        });
        this._closeDialog();
        await this._loadLibrary();
        this._renderTab();
        this._toast("Crop cleared");
      } catch (err) {
        this._toast(err.message, true);
      }
    };

    this._openDialog(
      `Crop — ${image.filename}`,
      [
        this._el("div", { class: "row" }, [
          this._el("label", { text: "Target frame" }),
          frameSelect,
        ]),
        stage,
      ],
      [
        this._el("button", { class: "btn", text: "Clear crop", onclick: clear }),
        this._el("button", { class: "btn", text: "Cancel", onclick: () => this._closeDialog() }),
        this._el("button", { class: "btn raised", text: "Save", onclick: save }),
      ]
    );
  }

  _initialBox(image, frame) {
    const key = `${frame.width}x${frame.height}`;
    if (image.crops && image.crops[key]) return [...image.crops[key]];
    // Default: the centered cover-crop the pipeline would use anyway.
    const size = this._effectiveSize(frame);
    const target = size.width / size.height;
    const source = image.width && image.height ? image.width / image.height : target;
    if (source > target) {
      const w = target / source;
      return [(1 - w) / 2, 0, (1 + w) / 2, 1];
    }
    const h = source / target;
    return [0, (1 - h) / 2, 1, (1 + h) / 2];
  }

  /* -------------------------------------------------------------- frames */

  _renderFrames(root) {
    const toolbar = this._el("div", { class: "toolbar" }, [
      this._el("button", {
        class: "btn raised",
        text: "Refresh",
        onclick: async () => {
          await this._loadFrames().catch((err) => this._toast(err.message, true));
          this._renderTab();
        },
      }),
    ]);
    root.appendChild(toolbar);
    if (!this._frames.length) {
      root.appendChild(this._el("div", { class: "empty", text: "No frames are loaded." }));
      return;
    }
    const grid = this._el("div", { class: "grid" });
    for (const frame of this._frames) {
      const rows = [
        this._el("div", { class: "title" }, [
          this._el("span", { class: `dot ${frame.online ? "on" : "off"}` }),
          document.createTextNode(frame.title),
        ]),
        this._el("div", { class: "sub", text: `${frame.width}×${frame.height} · rotation ${frame.rotation}°` }),
        this._el("div", {
          class: "sub",
          text:
            (frame.battery != null ? `Battery ${frame.battery}%${frame.charging ? " ⚡" : ""}` : "Battery unknown") +
            (frame.firmware ? ` · fw ${frame.firmware}` : ""),
        }),
        this._el("div", { class: "sub", text: frame.online ? "Online" : "Offline (deep sleep?)" }),
      ];
      const actions = this._el("div", { class: "actions" }, [
        this._el("button", {
          class: "btn",
          text: "Open frame UI",
          onclick: () => window.open(`http://${frame.host}/`, "_blank"),
        }),
      ]);
      grid.appendChild(
        this._el("div", { class: "card" }, [this._el("div", { class: "body" }, rows), actions])
      );
    }
    root.appendChild(grid);
  }

  /* -------------------------------------------------------------- scenes */

  _renderScenes(root) {
    const toolbar = this._el("div", { class: "toolbar" }, [
      this._el("button", {
        class: "btn raised",
        text: "New scene",
        onclick: () => this._openSceneEditor(null),
      }),
    ]);
    root.appendChild(toolbar);
    if (!this._scenes.length) {
      root.appendChild(
        this._el("div", {
          class: "empty",
          text: "No scenes yet. A scene assigns a library image to each frame and pushes them all at once.",
        })
      );
      return;
    }
    const grid = this._el("div", { class: "grid" });
    for (const scene of this._scenes) {
      const mappingRows = Object.entries(scene.mappings).map(([entryId, imageId]) => {
        const frame = this._frames.find((f) => f.entry_id === entryId);
        const image = this._images.find((i) => i.image_id === imageId);
        const row = this._el("div", { class: "sub" });
        const mini = this._el("img", { class: "mini", loading: "lazy" });
        if (image) this._setImgSrc(mini, `${API}/library/thumb/${image.image_id}`);
        row.append(
          mini,
          document.createTextNode(
            `${frame ? frame.title : "(unloaded frame)"} ← ${image ? image.filename : "(missing image)"}`
          )
        );
        return row;
      });
      const body = this._el("div", { class: "body" }, [
        this._el("div", { class: "title", text: scene.name }),
        ...(scene.source === "pack" ? [this._el("span", { class: "chip", text: "art pack" })] : []),
        ...mappingRows,
      ]);
      const actions = this._el("div", { class: "actions" }, [
        this._el("button", {
          class: "btn raised",
          text: "Send",
          onclick: async (ev) => {
            ev.target.disabled = true;
            this._toast("Sending scene…");
            try {
              const result = await this._api(`scenes/${scene.scene_id}/send`, { method: "POST" });
              const failed = Object.values(result.results).filter((r) => !r.ok);
              this._toast(
                failed.length ? `Scene sent with ${failed.length} failure(s)` : "Scene sent ✓",
                Boolean(failed.length)
              );
            } catch (err) {
              this._toast(err.message, true);
            } finally {
              ev.target.disabled = false;
            }
          },
        }),
        this._el("button", { class: "btn", text: "Edit", onclick: () => this._openSceneEditor(scene) }),
        this._el("button", {
          class: "btn danger",
          text: "Delete",
          onclick: async () => {
            if (!confirm(`Delete scene "${scene.name}"?`)) return;
            try {
              await this._api(`scenes/${scene.scene_id}`, { method: "DELETE" });
              await this._loadScenes();
              this._renderTab();
            } catch (err) {
              this._toast(err.message, true);
            }
          },
        }),
      ]);
      grid.appendChild(this._el("div", { class: "card" }, [body, actions]));
    }
    root.appendChild(grid);
  }

  _openSceneEditor(scene) {
    if (!this._frames.length) {
      this._toast("No frames are loaded", true);
      return;
    }
    if (!this._images.length) {
      this._toast("The library is empty — upload images first", true);
      return;
    }
    const nameInput = this._el("input", { type: "text", value: scene ? scene.name : "" });
    nameInput.placeholder = "Scene name";

    const selects = new Map();
    const rows = [this._el("div", { class: "row" }, [this._el("label", { text: "Name" }), nameInput])];
    for (const frame of this._frames) {
      const select = this._el("select");
      select.appendChild(this._el("option", { value: "", text: "(not included)" }));
      for (const image of this._images) {
        const option = this._el("option", { value: image.image_id, text: image.filename });
        if (scene && scene.mappings[frame.entry_id] === image.image_id) option.selected = true;
        select.appendChild(option);
      }
      const preview = this._el("img", { class: "mini" });
      const syncPreview = () => {
        if (select.value) this._setImgSrc(preview, `${API}/library/thumb/${select.value}`);
        else preview.removeAttribute("src");
      };
      select.addEventListener("change", syncPreview);
      syncPreview();
      selects.set(frame.entry_id, select);
      rows.push(
        this._el("div", { class: "row" }, [
          this._el("label", { text: this._frameLabel(frame) }),
          preview,
          select,
        ])
      );
    }

    const save = async () => {
      const mappings = {};
      for (const [entryId, select] of selects) {
        if (select.value) mappings[entryId] = select.value;
      }
      try {
        if (scene) {
          await this._api(`scenes/${scene.scene_id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: nameInput.value, mappings }),
          });
        } else {
          await this._api("scenes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: nameInput.value, mappings }),
          });
        }
        this._closeDialog();
        await this._loadScenes();
        this._renderTab();
      } catch (err) {
        this._toast(err.message, true);
      }
    };

    this._openDialog(scene ? "Edit scene" : "New scene", rows, [
      this._el("button", { class: "btn", text: "Cancel", onclick: () => this._closeDialog() }),
      this._el("button", { class: "btn raised", text: "Save", onclick: save }),
    ]);
  }

  /* --------------------------------------------------------------- packs */

  _renderPacks(root) {
    if (!this._packs.length) {
      root.appendChild(this._el("div", { class: "empty", text: "No packs in the catalog." }));
      return;
    }
    const grid = this._el("div", { class: "grid" });
    for (const pack of this._packs) {
      const body = this._el("div", { class: "body" }, [
        this._el("div", { class: "title", text: pack.name }),
        this._el("span", { class: "chip", text: pack.category }),
        this._el("div", { class: "sub", text: pack.description || "" }),
        this._el("div", {
          class: "sub",
          text: `${pack.installed_count}/${pack.images.length} installed · ${pack.attribution}`,
        }),
        this._el("div", { class: "sub", text: pack.images.map((image) => image.title).join(" · ") }),
      ]);
      const installBtn = this._el("button", {
        class: "btn raised",
        text: pack.installed ? "Reinstall missing" : pack.installed_count ? "Resume install" : "Install",
        onclick: async (ev) => {
          ev.target.disabled = true;
          ev.target.textContent = "Installing…";
          this._toast(`Installing ${pack.name} — downloads are throttled, this can take a minute`);
          try {
            const result = await this._api(`packs/${pack.id}/install`, { method: "POST" });
            const failures = result.failed.length ? `, ${result.failed.length} failed` : "";
            this._toast(`${pack.name}: ${result.installed_count}/${result.total} installed${failures}`, Boolean(result.failed.length));
            await Promise.all([this._loadLibrary(), this._loadScenes(), this._loadPacks()]);
            this._renderTab();
          } catch (err) {
            this._toast(err.message, true);
            ev.target.disabled = false;
          }
        },
      });
      if (pack.installed) installBtn.disabled = true;
      const actions = this._el("div", { class: "actions" }, [installBtn]);
      if (pack.installed_count) {
        actions.appendChild(
          this._el("button", {
            class: "btn danger",
            text: "Uninstall",
            onclick: async () => {
              if (!confirm(`Remove ${pack.name} and its images from the library?`)) return;
              try {
                const result = await this._api(`packs/${pack.id}/uninstall`, { method: "POST" });
                this._toast(`Removed ${result.removed} images`);
                await Promise.all([this._loadLibrary(), this._loadScenes(), this._loadPacks()]);
                this._renderTab();
              } catch (err) {
                this._toast(err.message, true);
              }
            },
          })
        );
      }
      grid.appendChild(this._el("div", { class: "card" }, [body, actions]));
    }
    root.appendChild(grid);
  }

  /* -------------------------------------------------------------- dialog */

  _openDialog(title, contentNodes, actionNodes) {
    const modal = this.shadowRoot.getElementById("modal");
    modal.innerHTML = "";
    const dialog = this._el("div", { class: "dialog" }, [
      this._el("h2", { text: title }),
      ...contentNodes,
      this._el("div", { class: "dialog-actions" }, actionNodes),
    ]);
    const overlay = this._el("div", {
      class: "overlay",
      onclick: (ev) => {
        if (ev.target === overlay) this._closeDialog();
      },
    });
    overlay.appendChild(dialog);
    modal.appendChild(overlay);
  }

  _closeDialog() {
    this.shadowRoot.getElementById("modal").innerHTML = "";
  }
}

customElements.define("fraimic-panel", FraimicPanel);
