/*
 * Fraimic sidebar panel.
 *
 * Vanilla web component (no build step, no external deps). Talks to the
 * integration's authenticated /api/fraimic/* endpoints via hass.fetchWithAuth
 * and signs <img> URLs with auth/sign_path so thumbnails work in plain img
 * tags. Styled exclusively with HA theme variables so light/dark both work.
 */

const API = "/api/fraimic";
// Mirrors MIN_ART_SHORT_EDGE in const.py: anything with a shorter short edge
// upscales visibly soft on the ~150 PPI panel.
const LOW_RES_SHORT_EDGE = 1000;
const PACK_REFRESH_MAX_ATTEMPTS = 30;
const PACK_REFRESH_MAX_DELAY = 15000;
const PACK_PROGRESS_MAX_ATTEMPTS = 600;

class FraimicPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "library";
    this._images = [];
    this._albums = [];
    this._frames = [];
    this._selectedFrameId = this._readStoredFrame();
    this._player = null;
    this._queueOpen = false;
    this._frameMenuOpen = false;
    this._appMenuOpen = false;
    this._rowMenu = null;
    this._showPlaylistWarning = false;
    this._drag = null;
    this._touchDrag = null;
    this._touchAutoScrollFrame = null;
    this._scenes = [];
    this._packs = [];
    this._packRefreshTimer = null;
    this._packProgressTimer = null;
    this._packProgressAttempts = 0;
    this._installingPacks = new Set();
    this._albumFilter = "";
    this._packCategory = "";
    this._screens = [];
    this._screensEntry = "";
    this._descriptors = null;
    this._selectMode = false;
    this._selected = new Set();
    this._dialogStack = [];
    this._highlightEntry = null;
    this._signedCache = new Map();
    this._playerRefreshTimer = null;
    this._playerRefreshInFlight = false;
    this._playerGeneration = 0;
    // Lazy thumbnails: sign only near-viewport images, a few at a time, so a
    // large library doesn't fire hundreds of sign_path calls on tab open.
    this._signQueue = [];
    this._signActive = 0;
    this._thumbObserver =
      "IntersectionObserver" in window
        ? new IntersectionObserver(
            (observations) => {
              for (const observation of observations) {
                if (!observation.isIntersecting) continue;
                this._thumbObserver.unobserve(observation.target);
                this._enqueueSign(observation.target);
              }
            },
            { rootMargin: "300px" }
          )
        : null;
    this._initialized = false;
  }

  connectedCallback() {
    if (this._initialized) this._startPlayerRefresh();
  }

  disconnectedCallback() {
    clearTimeout(this._packRefreshTimer);
    clearTimeout(this._packProgressTimer);
    this._packRefreshTimer = null;
    this._packProgressTimer = null;
    this._packProgressAttempts = 0;
    this._installingPacks.clear();
    clearTimeout(this._playerRefreshTimer);
    this._playerRefreshTimer = null;
    this._cancelTouchDrag();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      // Deep links: /fraimic?tab=frames&entry=<entry_id>.
      const query = new URLSearchParams(window.location.search);
      if (query.get("entry")) {
        this._highlightEntry = query.get("entry");
        this._tab = "frames";
      }
      if (query.get("tab")) this._tab = query.get("tab");
      this._renderShell();
      this._refreshAll();
      this._startPlayerRefresh();
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

  /* Grid thumbnails: defer signing until the image nears the viewport, then
   * run at most six sign+load jobs concurrently. */
  _lazyImg(img, path) {
    if (!this._thumbObserver) {
      this._setImgSrc(img, path);
      return;
    }
    img.dataset.signPath = path;
    this._thumbObserver.observe(img);
  }

  _enqueueSign(img) {
    this._signQueue.push(img);
    this._drainSignQueue();
  }

  _drainSignQueue() {
    while (this._signActive < 6 && this._signQueue.length) {
      const img = this._signQueue.shift();
      if (!img.isConnected) continue;
      this._signActive += 1;
      this._signedUrl(img.dataset.signPath)
        .then((url) => {
          img.src = url;
        })
        .catch(() => {
          img.alt = "unavailable";
        })
        .finally(() => {
          this._signActive -= 1;
          this._drainSignQueue();
        });
    }
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

  _onImageDims(img, callback) {
    // Natural dimensions of an <img>, whether it is still loading or was
    // already complete (cache hit) when we got here.
    const report = () => {
      if (img.naturalWidth) callback(img.naturalWidth, img.naturalHeight);
    };
    if (img.complete) report();
    else img.addEventListener("load", report, { once: true });
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

  _readStoredFrame() {
    try {
      return window.localStorage.getItem("fraimic:selected-frame");
    } catch (_err) {
      return null;
    }
  }

  _storeFrame(entryId) {
    try {
      window.localStorage.setItem("fraimic:selected-frame", entryId);
    } catch (_err) {
      /* localStorage may be unavailable in a hardened browser */
    }
  }

  _activeFrame() {
    return (
      this._frames.find((frame) => frame.entry_id === this._selectedFrameId) ||
      this._frames[0] ||
      null
    );
  }

  /* ---------------------------------------------------------------- data */

  async _refreshAll() {
    const packsPromise = this._loadPacks()
      .then(() => {
        if (this._tab === "packs") this._renderTab();
      })
      .catch((err) => this._toast(err.message, true));
    await Promise.all([
      this._loadLibrary(),
      this._loadFrames(),
      this._loadScenes(),
    ]).catch((err) => this._toast(err.message, true));
    await this._loadPlayer().catch((err) => this._toast(err.message, true));
    this._renderTab();
    await packsPromise;
  }

  async _loadLibrary() {
    const data = await this._api("library");
    this._images = data.images;
    this._albums = data.albums;
  }

  async _loadFrames() {
    const previousEntryId = this._selectedFrameId;
    this._frames = (await this._api("frames")).frames;
    if (!this._frames.some((frame) => frame.entry_id === this._selectedFrameId)) {
      this._selectedFrameId = this._frames[0]?.entry_id || null;
    }
    if (this._selectedFrameId) this._storeFrame(this._selectedFrameId);
    if (this._selectedFrameId !== previousEntryId) {
      this._playerGeneration += 1;
      this._player = null;
      this._renderPlayer();
      this._renderQueue();
    }
    this._renderFrameChips();
  }

  async _loadPlayer() {
    const frame = this._activeFrame();
    if (!frame) {
      this._player = null;
      this._renderPlayer();
      this._renderQueue();
      return;
    }
    const entryId = frame.entry_id;
    const generation = this._playerGeneration;
    const player = await this._api(
      `player?entry_id=${encodeURIComponent(frame.entry_id)}`
    );
    if (
      entryId !== this._selectedFrameId ||
      generation !== this._playerGeneration
    ) return null;
    this._player = player;
    this._renderPlayer();
    this._renderQueue();
    return player;
  }

  _startPlayerRefresh() {
    if (this._playerRefreshTimer || !this.isConnected) return;
    const delay = this._player?.sending ? 5 * 1000 : 60 * 1000;
    this._playerRefreshTimer = window.setTimeout(async () => {
      this._playerRefreshTimer = null;
      await this._refreshPlayerState();
      this._startPlayerRefresh();
    }, delay);
  }

  _restartPlayerRefresh() {
    clearTimeout(this._playerRefreshTimer);
    this._playerRefreshTimer = null;
    this._startPlayerRefresh();
  }

  async _refreshPlayerState() {
    if (this._playerRefreshInFlight || !this.isConnected) return;
    this._playerRefreshInFlight = true;
    try {
      await this._loadFrames();
      await this._loadPlayer();
    } catch (_err) {
      // The persistent bar keeps its last known state until the next poll.
    } finally {
      this._playerRefreshInFlight = false;
    }
  }

  async _loadScenes() {
    this._scenes = (await this._api("scenes")).scenes;
  }

  async _loadPacks(attempt = 0) {
    const data = await this._api("packs");
    this._packs = data.packs;
    if (this._packRefreshTimer) clearTimeout(this._packRefreshTimer);
    this._packRefreshTimer = null;
    if (
      data.reframed_refreshing &&
      this.isConnected &&
      attempt < PACK_REFRESH_MAX_ATTEMPTS
    ) {
      const delay = Math.min(
        1000 * 2 ** Math.floor(attempt / 5),
        PACK_REFRESH_MAX_DELAY
      );
      this._packRefreshTimer = setTimeout(async () => {
        this._packRefreshTimer = null;
        if (!this.isConnected) return;
        try {
          await this._loadPacks(attempt + 1);
          if (this._tab === "packs") this._renderTab();
        } catch (err) {
          this._toast(err.message, true);
        }
      }, delay);
    }
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
          color: var(--app-header-text-color, var(--primary-text-color));
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
          box-shadow: var(--ha-card-box-shadow);
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
        button.btn:hover { background: color-mix(in srgb, var(--primary-color) 10%, transparent); }
        button.btn.danger { color: var(--error-color); }
        button.btn.raised {
          background: var(--primary-color);
          color: var(--text-primary-color);
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
        .chip.warn {
          border-color: var(--warning-color, var(--primary-color));
          color: var(--primary-text-color);
        }
        .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }
        .dot.on { background: var(--success-color, var(--primary-color)); }
        .dot.off { background: var(--error-color); }
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
          box-shadow: var(--ha-card-box-shadow);
          padding: 12px 20px;
          max-width: 80vw;
          transition: transform 0.2s ease;
          z-index: 20;
        }
        #toast.show { transform: translateX(-50%) translateY(0); }
        #toast.error { border-left: 4px solid var(--error-color); }
        .overlay {
          position: fixed;
          inset: 0;
          background: color-mix(in srgb, var(--primary-background-color) 55%, transparent);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 10;
          padding: 16px;
        }
        .dialog {
          background: var(--card-background-color);
          border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow);
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
          box-shadow: 0 0 0 9999px color-mix(in srgb, var(--primary-background-color) 45%, transparent);
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
        .card.selectable { cursor: pointer; }
        .card.selected { outline: 3px solid var(--primary-color); }
        .checkmark {
          position: absolute;
          top: 8px;
          left: 8px;
          width: 22px;
          height: 22px;
          border-radius: 50%;
          background: var(--primary-color);
          color: var(--text-primary-color);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          z-index: 1;
        }
        .thumbwrap { position: relative; }
        .card.highlight { outline: 3px solid var(--primary-color); }
        .albumstrip {
          display: flex;
          gap: 12px;
          overflow-x: auto;
          padding-bottom: 12px;
          margin-bottom: 12px;
        }
        .albumcard {
          flex: 0 0 auto;
          width: 120px;
          cursor: pointer;
          background: var(--card-background-color);
          border-radius: 8px;
          box-shadow: var(--ha-card-box-shadow);
          overflow: hidden;
        }
        .albumcard img { width: 120px; height: 80px; object-fit: cover; display: block; background: var(--secondary-background-color); }
        .albumcard .cap {
          font-size: 12px;
          padding: 6px 8px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .albumcard .cap span { color: var(--secondary-text-color); }
        .chiprow { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
        .chiprow .fchip {
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: 14px;
          padding: 4px 12px;
          font-size: 13px;
          cursor: pointer;
        }
        .chiprow .fchip.active {
          background: var(--primary-color);
          border-color: var(--primary-color);
          color: var(--text-primary-color);
        }
        .gallery { text-align: center; }
        .gallery img {
          max-width: min(760px, 80vw);
          max-height: 60vh;
          border-radius: 6px;
          background: var(--secondary-background-color);
        }
        .gallery .caption { margin-top: 8px; font-size: 14px; }
        .gallery .caption span { color: var(--secondary-text-color); font-size: 12px; }
        .gallery .navrow { display: flex; justify-content: center; gap: 16px; margin-top: 8px; align-items: center; }
        .pack-progress { margin-top: 10px; }
        .pack-progress-meta {
          display: flex;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 5px;
          color: var(--secondary-text-color);
          font-size: 11px;
          font-variant-numeric: tabular-nums;
        }
        .pack-progress-track {
          height: 4px;
          overflow: hidden;
          background: var(--divider-color);
        }
        .pack-progress-fill {
          height: 100%;
          background: var(--primary-color);
          transition: width 180ms ease-out;
        }
        @media (prefers-reduced-motion: reduce) {
          .pack-progress-fill { transition: none; }
        }
        /* Screen editor */
        .dialog.wide { max-width: min(1280px, 96vw); width: 96vw; }
        .editor-grid { display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }
        .editor-form { flex: 1 1 340px; min-width: 300px; max-width: 480px; }
        .editor-preview { flex: 1 1 400px; min-width: 300px; position: sticky; top: 0; }
        .editor-preview img {
          width: 100%;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          min-height: 120px;
        }
        .editor-preview .status { font-size: 12px; color: var(--secondary-text-color); margin-top: 6px; min-height: 16px; white-space: pre-wrap; }
        .editor-preview .status.err { color: var(--error-color); }
        .slotbox {
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 10px 12px;
          margin: 10px 0;
        }
        .slotbox .slotname {
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: var(--secondary-text-color);
          margin-bottom: 6px;
        }
        .fieldrow { display: flex; align-items: center; gap: 8px; margin: 6px 0; flex-wrap: wrap; }
        .fieldrow label { min-width: 130px; font-size: 13px; }
        .fieldrow input[type="text"], .fieldrow input[type="number"], .fieldrow select, .fieldrow textarea {
          flex: 1;
          min-width: 120px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          padding: 5px 8px;
          font: inherit;
          font-size: 13px;
        }
        .fieldrow textarea { min-height: 56px; resize: vertical; }
        .fieldrow .help { flex-basis: 100%; font-size: 11px; color: var(--secondary-text-color); margin-left: 138px; }

        /* Phase 1 shell */
        * { box-sizing: border-box; }
        :host { overflow: hidden; font-size: 14px; }
        button, input, select, textarea { font-family: inherit; }
        button:focus-visible, input:focus-visible, select:focus-visible,
        [tabindex]:focus-visible {
          outline: 2px solid var(--primary-color);
          outline-offset: 2px;
        }
        #appShell {
          --frame-aspect: 4 / 3;
          position: relative;
          display: flex;
          flex-direction: column;
          height: 100%;
          min-width: 0;
          background: var(--primary-background-color);
        }
        .app-topbar {
          position: relative;
          z-index: 12;
          flex: 0 0 56px;
          display: flex;
          align-items: center;
          gap: 8px;
          height: 56px;
          padding: 0 16px;
          border-bottom: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        .brand-button, .top-action, .menu-item, .text-button {
          border: 0;
          background: transparent;
          color: var(--primary-text-color);
          cursor: pointer;
        }
        .brand-button {
          min-height: 44px;
          padding: 0;
          font-size: 15px;
          font-weight: 600;
          letter-spacing: -0.01em;
        }
        .frame-chips {
          display: flex;
          min-width: 0;
          gap: 8px;
          overflow-x: auto;
          scrollbar-width: none;
        }
        .frame-chips::-webkit-scrollbar { display: none; }
        .frame-chip {
          display: inline-flex;
          flex: none;
          align-items: center;
          gap: 6px;
          min-height: 32px;
          padding: 0 12px;
          border: 1px solid var(--divider-color);
          border-radius: 16px;
          background: transparent;
          color: var(--secondary-text-color);
          font-size: 13px;
          white-space: nowrap;
          cursor: pointer;
        }
        .frame-chip[aria-checked="true"] {
          border-color: var(--primary-color);
          background: var(--primary-color);
          color: var(--text-primary-color);
          font-weight: 600;
        }
        .frame-chip:disabled { cursor: default; opacity: 1; }
        .status-dot {
          width: 8px;
          height: 8px;
          flex: none;
          border-radius: 50%;
          background: var(--divider-color);
        }
        .status-dot.online { background: var(--success-color, var(--primary-color)); }
        .status-dot.charging { background: var(--warning-color, var(--primary-color)); }
        .shell-spacer { flex: 1 1 auto; }
        .top-action {
          min-height: 44px;
          padding: 0 8px;
          color: var(--secondary-text-color);
          font-size: 13px;
        }
        .top-action:hover, .brand-button:hover, .menu-item:hover, .text-button:hover {
          color: var(--primary-color);
        }
        .icon-button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 44px;
          height: 44px;
          flex: none;
          padding: 0;
          border: 0;
          background: transparent;
          color: var(--primary-text-color);
          cursor: pointer;
        }
        .icon-button ha-icon {
          width: 18px;
          height: 18px;
          padding: 6px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
        }
        .icon-button.primary ha-icon {
          border-color: var(--primary-color);
          background: var(--primary-color);
          color: var(--text-primary-color);
        }
        .icon-button:disabled { cursor: default; opacity: 0.4; }
        .shell-menu {
          position: absolute;
          z-index: 16;
          right: 12px;
          min-width: 248px;
          overflow: hidden;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          background: var(--card-background-color);
          box-shadow: var(--ha-card-box-shadow);
        }
        .app-menu { top: 50px; }
        .frame-menu { right: 8px; bottom: 58px; }
        .shell-menu[hidden] { display: none; }
        .menu-heading {
          padding: 8px 14px;
          border-bottom: 1px solid var(--divider-color);
          color: var(--secondary-text-color);
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.1em;
          text-transform: uppercase;
        }
        .menu-item {
          display: flex;
          align-items: center;
          width: 100%;
          min-height: 44px;
          padding: 8px 14px;
          border-bottom: 1px solid var(--divider-color);
          text-align: left;
          font-size: 13px;
        }
        .menu-item:last-child { border-bottom: 0; }
        #legacyViewport {
          flex: 1 1 auto;
          min-height: 0;
          overflow: auto;
        }
        #legacyViewport.queue-open {
          overflow: hidden;
          opacity: 0.35;
          pointer-events: none;
          user-select: none;
        }
        #legacyViewport nav { background: var(--primary-background-color); }
        #legacyViewport main { min-height: 100%; }
        .queue-backdrop {
          position: absolute;
          z-index: 7;
          inset: 56px 0 64px;
          border: 0;
          background: transparent;
        }
        .queue-backdrop[hidden] { display: none; }
        .queue-sheet {
          position: absolute;
          z-index: 10;
          right: 0;
          bottom: 64px;
          left: 0;
          max-height: 420px;
          overflow-y: auto;
          overscroll-behavior: contain;
          border-top: 1px solid var(--divider-color);
          background: var(--card-background-color);
          transition: max-height 160ms ease;
        }
        .queue-sheet[hidden] { display: none; }
        .queue-grab { display: none; }
        .queue-section-header {
          display: flex;
          align-items: center;
          gap: 8px;
          min-height: 44px;
          padding: 6px 16px;
        }
        .queue-section-title {
          flex: 1 1 auto;
          color: var(--secondary-text-color);
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.1em;
          text-transform: uppercase;
        }
        .queue-list { margin: 0; padding: 0; list-style: none; }
        .queue-row {
          position: relative;
          display: flex;
          align-items: center;
          gap: 12px;
          min-height: 72px;
          padding: 8px 16px;
          border-bottom: 1px solid var(--divider-color);
          background: var(--card-background-color);
        }
        .queue-row.dragging { opacity: 0.7; }
        .queue-row.insert-before { border-top: 2px solid var(--primary-color); }
        .queue-row.insert-after { border-bottom: 2px solid var(--primary-color); }
        .queue-row.insert-before::before, .queue-row.insert-after::after {
          position: absolute;
          left: 12px;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--primary-color);
          content: "";
        }
        .queue-row.insert-before::before { top: -5px; }
        .queue-row.insert-after::after { bottom: -5px; }
        .drag-grip {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 44px;
          flex: none;
          padding: 0;
          border: 0;
          background: transparent;
          color: var(--secondary-text-color);
          cursor: grab;
          touch-action: pan-y;
        }
        .drag-grip:active { cursor: grabbing; }
        .glass { aspect-ratio: var(--frame-aspect); }
        .frame-art {
          position: relative;
          width: 56px;
          flex: none;
          overflow: hidden;
          border-radius: 4px;
          background: #0d0d0d;
        }
        .frame-art img {
          display: block;
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .frame-art.loading::after {
          position: absolute;
          inset: 0;
          background: var(--divider-color);
          content: "";
        }
        .queue-copy { min-width: 0; flex: 1 1 auto; }
        .queue-copy strong, .player-copy strong {
          display: block;
          overflow: hidden;
          color: var(--primary-text-color);
          font-size: 13px;
          font-weight: 600;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .queue-copy span, .player-copy span {
          display: block;
          overflow: hidden;
          color: var(--secondary-text-color);
          font-size: 12px;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .row-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          padding: 4px 16px 8px 60px;
          border-bottom: 1px solid var(--divider-color);
          background: var(--card-background-color);
        }
        .text-button {
          min-height: 44px;
          padding: 0 8px;
          color: var(--secondary-text-color);
          font-size: 12px;
        }
        .text-button.danger { color: var(--error-color); }
        .small-tag {
          display: inline-flex;
          align-items: center;
          min-height: 26px;
          padding: 0 8px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          color: var(--secondary-text-color);
          font-size: 11px;
          white-space: nowrap;
        }
        .queue-note {
          padding: 8px 16px;
          border-bottom: 1px solid var(--divider-color);
          color: var(--secondary-text-color);
          font-size: 12px;
        }
        .queue-empty {
          padding: 32px 16px;
          color: var(--secondary-text-color);
          text-align: center;
          font-size: 13px;
        }
        .drag-ghost {
          position: fixed;
          z-index: 30;
          width: 120px;
          pointer-events: none;
          opacity: 0.7;
          transform: rotate(1.5deg);
          box-shadow: var(--ha-card-box-shadow);
        }
        .playerbar {
          position: relative;
          z-index: 11;
          display: flex;
          align-items: center;
          gap: 10px;
          height: 64px;
          flex: 0 0 64px;
          padding: 0 16px;
          border-top: 1px solid var(--divider-color);
          background: var(--card-background-color);
        }
        .playerbar.unreachable { border-top-color: var(--error-color); }
        .playerbar.asleep .frame-art { opacity: 0.45; }
        .player-copy { min-width: 0; flex: 0 1 auto; }
        .player-controls { display: flex; align-items: center; gap: 2px; }
        .player-progress {
          width: 160px;
          height: 3px;
          flex: none;
          overflow: hidden;
          border-radius: 2px;
          background: var(--divider-color);
        }
        .player-progress > span {
          display: block;
          height: 100%;
          background: var(--primary-text-color);
        }
        .player-progress.sending > span { background: var(--primary-color); }
        .queue-toggle {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          min-height: 44px;
          padding: 0 12px;
          border: 0;
          background: transparent;
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 13px;
          white-space: nowrap;
        }
        .queue-toggle::before {
          position: absolute;
          width: 100%;
          height: 32px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          content: "";
          pointer-events: none;
        }
        .queue-toggle { position: relative; }
        .player-action {
          display: inline-flex;
          align-items: center;
          min-height: 44px;
          padding: 0 12px;
          border: 0;
          background: transparent;
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 13px;
        }
        .player-action.primary {
          min-height: 32px;
          border: 1px solid var(--primary-color);
          border-radius: 4px;
          background: var(--primary-color);
          color: var(--text-primary-color);
          font-weight: 600;
        }
        #toast {
          bottom: 80px;
          left: 16px;
          max-width: min(520px, calc(100vw - 32px));
          border: 1px solid var(--divider-color);
          box-shadow: var(--ha-card-box-shadow);
          transform: translateY(96px);
        }
        #toast.show { transform: translateY(0); }
        #toast.error { border-color: var(--error-color); }
        .sr-only {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
          border: 0;
        }
        @media (max-width: 899px) {
          .player-progress, .overlay-tag { display: none; }
        }
        @media (max-width: 599px) {
          .app-topbar { padding: 0 12px; }
          .top-text-action { display: none; }
          .frame-chips { flex: 1 1 auto; }
          #legacyViewport main { padding: 12px; }
          .playerbar { gap: 8px; padding: 0 12px; }
          .playerbar .frame-art { width: 44px; }
          /* Phase 1 mobile player: artwork, title, play, and queue only. */
          .desktop-control, .frame-overflow { display: none; }
          .player-copy { flex: 1 1 auto; }
          .queue-toggle { padding: 0 10px; }
          .queue-toggle .queue-label { display: none; }
          .queue-sheet { top: 56px; bottom: 64px; max-height: none; }
          .queue-grab {
            display: block;
            width: 40px;
            height: 4px;
            margin: 8px auto 4px;
            border-radius: 2px;
            background: var(--divider-color);
          }
          .queue-section-header, .queue-row { padding-right: 12px; padding-left: 12px; }
        }
        @media (prefers-reduced-motion: reduce) {
          .queue-sheet, #toast { transition: none; }
          .drag-ghost { transform: none; }
        }
      </style>
      <div id="appShell">
        <header class="app-topbar">
          <button class="brand-button" id="brandButton">Fraimic</button>
          <div class="frame-chips" id="frameChips" role="radiogroup" aria-label="Frames"></div>
          <span class="shell-spacer"></span>
          <button class="top-action top-text-action" id="playlistsButton">Playlists</button>
          <button class="top-action top-text-action" id="uploadButton">Upload</button>
          <input id="shellUpload" type="file" accept="image/*" multiple hidden>
          <button class="icon-button" id="appMenuButton" aria-label="Open app menu" aria-expanded="false"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>
          <div class="shell-menu app-menu" id="appMenu" hidden></div>
        </header>
        <div id="legacyViewport">
          <nav id="tabs"></nav>
          <main id="content"></main>
        </div>
        <button class="queue-backdrop" id="queueBackdrop" aria-label="Close queue" hidden></button>
        <section class="queue-sheet" id="queueSheet" aria-label="Queue" tabindex="-1" hidden></section>
        <div class="sr-only" id="queueStatus" aria-live="polite"></div>
        <footer class="playerbar" id="playerBar"></footer>
        <div id="toast"></div>
        <div id="modal"></div>
      </div>
    `;
    const tabs = [
      ["library", "Library"],
      ["frames", "Frames"],
      ["scenes", "Scenes"],
      ["screens", "Screens"],
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
    this.shadowRoot.getElementById("brandButton").addEventListener("click", () => {
      this._tab = "library";
      this._renderTab();
    });
    this.shadowRoot.getElementById("playlistsButton").addEventListener("click", () => {
      this._openLegacySlides();
    });
    const uploadInput = this.shadowRoot.getElementById("shellUpload");
    this.shadowRoot.getElementById("uploadButton").addEventListener("click", () => {
      uploadInput.click();
    });
    uploadInput.addEventListener("change", async () => {
      await this._uploadFiles(uploadInput.files);
      uploadInput.value = "";
    });
    this.shadowRoot.getElementById("appMenuButton").addEventListener("click", () => {
      this._appMenuOpen = !this._appMenuOpen;
      this._frameMenuOpen = false;
      this._renderAppMenu();
      this._renderPlayer();
    });
    this.shadowRoot.getElementById("queueBackdrop").addEventListener("click", () => {
      this._setQueueOpen(false);
    });
    this.shadowRoot.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (this._queueOpen) this._setQueueOpen(false);
      this._appMenuOpen = false;
      this._frameMenuOpen = false;
      this._renderAppMenu();
      this._renderPlayer();
    });
    this._renderFrameChips();
    this._renderAppMenu();
    this._renderPlayer();
    this._renderQueue();
  }

  _renderFrameChips() {
    const root = this.shadowRoot.getElementById("frameChips");
    const shell = this.shadowRoot.getElementById("appShell");
    if (!root || !shell) return;
    const focus = this._captureFocus(root);
    root.innerHTML = "";
    const active = this._activeFrame();
    for (const frame of this._frames) {
      const selected = frame.entry_id === active?.entry_id;
      const dotState = frame.charging ? "charging" : frame.online ? "online" : "offline";
      const dot = this._el("span", { class: `status-dot ${dotState}` });
      const chip = this._el(
        "button",
        {
          class: "frame-chip",
          role: "radio",
          "aria-checked": String(selected),
          "aria-label": this._frameChipTitle(frame),
          title: this._frameChipTitle(frame),
          onclick: () => this._selectFrame(frame.entry_id),
        },
        [dot, document.createTextNode(frame.title)]
      );
      if (this._frames.length === 1) chip.disabled = true;
      root.appendChild(chip);
    }
    if (active) {
      const size = this._effectiveSize(active);
      const width = Number(size.width) || 4;
      const height = Number(size.height) || 3;
      shell.style.setProperty("--frame-aspect", `${width} / ${height}`);
    } else {
      shell.style.setProperty("--frame-aspect", "4 / 3");
    }
    this._restoreFocus(root, focus);
  }

  _captureFocus(root) {
    const active = this.shadowRoot.activeElement;
    if (!active || !root.contains(active)) return null;
    const controls = [...root.querySelectorAll("button, [href], input, select, textarea, [tabindex]")];
    return {
      id: active.id,
      ariaLabel: active.getAttribute("aria-label") || "",
      text: active.textContent.trim(),
      index: controls.indexOf(active),
    };
  }

  _restoreFocus(root, focus) {
    if (!focus) return;
    const controls = [...root.querySelectorAll("button, [href], input, select, textarea, [tabindex]")];
    const match = controls.find((control) =>
      (focus.id && control.id === focus.id) ||
      (focus.ariaLabel && control.getAttribute("aria-label") === focus.ariaLabel) ||
      (focus.text && control.textContent.trim() === focus.text)
    ) || controls[focus.index];
    match?.focus();
  }

  _frameChipTitle(frame) {
    const status = frame.charging
      ? "charging"
      : frame.online
        ? "online"
        : frame.asleep
          ? "asleep"
          : "unreachable";
    const battery = frame.battery == null ? "" : `, ${frame.battery}% battery`;
    return `${frame.title}, ${status}${battery}`;
  }

  async _selectFrame(entryId) {
    if (entryId === this._selectedFrameId) return;
    this._selectedFrameId = entryId;
    this._playerGeneration += 1;
    this._storeFrame(entryId);
    this._player = null;
    this._queueOpen = false;
    this._rowMenu = null;
    this._screensEntry = entryId;
    this._screensLoadedFor = null;
    this._renderFrameChips();
    this._renderPlayer();
    this._setQueueOpen(false);
    if (this._tab === "screens") this._renderTab();
    try {
      await this._loadPlayer();
    } catch (err) {
      this._toast(err.message, true);
    }
  }

  _openLegacySlides() {
    this._setQueueOpen(false);
    const frame = this._activeFrame();
    if (frame) {
      this._screensEntry = frame.entry_id;
      this._screensLoadedFor = null;
    }
    this._tab = "screens";
    this._renderTab();
  }

  _navigate(path) {
    window.history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed"));
  }

  _renderAppMenu() {
    const root = this.shadowRoot.getElementById("appMenu");
    const button = this.shadowRoot.getElementById("appMenuButton");
    if (!root || !button) return;
    root.hidden = !this._appMenuOpen;
    button.setAttribute("aria-expanded", String(this._appMenuOpen));
    root.innerHTML = "";
    if (!this._appMenuOpen) return;
    root.appendChild(this._el("div", { class: "menu-heading", text: "App menu" }));
    const add = (label, action) => {
      root.appendChild(
        this._el("button", {
          class: "menu-item",
          text: label,
          onclick: () => {
            this._appMenuOpen = false;
            this._renderAppMenu();
            action();
          },
        })
      );
    };
    add("Manage library", () => {
      this._tab = "library";
      this._renderTab();
    });
    add("Sources and API keys", () =>
      this._navigate("/config/integrations/integration/fraimic")
    );
    add("Reload sources", async () => {
      await this._refreshAll();
    });
    add("Add a frame", () =>
      this._navigate("/config/integrations/integration/fraimic")
    );
    add("Documentation", () =>
      window.open("https://github.com/kristofferR/ha-fraimic-eink", "_blank", "noopener")
    );
  }

  _iconButton(icon, label, onclick, { primary = false, disabled = false, className = "" } = {}) {
    const button = this._el(
      "button",
      {
        class: `icon-button${primary ? " primary" : ""}${className ? ` ${className}` : ""}`,
        "aria-label": label,
        title: label,
        onclick,
      },
      [this._el("ha-icon", { icon })]
    );
    button.disabled = disabled;
    return button;
  }

  _frameArtwork(url, alt = "") {
    const root = this._el("div", { class: "frame-art glass loading" });
    if (!url) return root;
    const img = this._el("img", { alt });
    img.addEventListener("load", () => root.classList.remove("loading"), { once: true });
    root.appendChild(img);
    if (/^https?:\/\//i.test(url)) img.src = url;
    else this._setImgSrc(img, url);
    return root;
  }

  _formatRemaining(seconds) {
    if (seconds == null) return "";
    if (seconds < 60) return `${Math.max(1, Math.ceil(seconds))} sec left`;
    const minutes = Math.ceil(seconds / 60);
    if (minutes < 60) return `${minutes} min left`;
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return rest ? `${hours} h ${rest} min left` : `${hours} h left`;
  }

  _formatInterval(seconds) {
    if (!seconds) return "";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `every ${minutes} min`;
    if (minutes % 60 === 0) {
      const hours = minutes / 60;
      return `every ${hours} ${hours === 1 ? "hour" : "hours"}`;
    }
    return `every ${minutes} min`;
  }

  _lastSeen(frame) {
    if (!frame?.last_seen) return "a few";
    return String(Math.max(1, Math.round((Date.now() / 1000 - frame.last_seen) / 60)));
  }

  _renderPlayer() {
    const root = this.shadowRoot.getElementById("playerBar");
    if (!root) return;
    const focus = this._captureFocus(root);
    this._renderPlayerContent(root);
    this._restoreFocus(root, focus);
  }

  _renderPlayerContent(root) {
    root.innerHTML = "";
    root.className = "playerbar";
    const frame = this._activeFrame();
    if (!frame) {
      root.append(
        this._frameArtwork(null),
        this._el("div", { class: "player-copy" }, [
          this._el("strong", { text: "No frames yet" }),
        ]),
        this._el("span", { class: "shell-spacer" }),
        this._el("button", {
          class: "player-action primary",
          text: "Add a frame",
          onclick: () => this._navigate("/config/integrations/integration/fraimic"),
        })
      );
      return;
    }
    if (!this._player) {
      root.append(
        this._frameArtwork(null),
        this._el("div", { class: "player-copy" }, [
          this._el("strong", { text: frame.title }),
        ])
      );
      return;
    }

    const player = this._player;
    const state = player.state;
    root.classList.add(state);
    let title = player.current?.title || "Nothing playing";
    let meta = "";
    if (state === "sending") {
      meta = "Sending · the panel takes about 30 seconds";
    } else if (state === "asleep") {
      meta = `${frame.title} is asleep · still showing this`;
    } else if (state === "unreachable") {
      title = `Could not reach ${frame.title}.`;
      meta = `Last seen ${this._lastSeen(frame)} minutes ago, check power and wifi.`;
    } else if (state === "idle") {
      title = "Nothing playing";
      meta = "Pick a playlist, or show a picture from the gallery";
    } else {
      const parts = [];
      if (player.current?.artist) parts.push(player.current.artist);
      if (player.playlist_name) parts.push(player.playlist_name);
      parts.push(player.paused ? "Paused" : this._formatRemaining(player.seconds_remaining));
      meta = parts.filter(Boolean).join(" · ");
    }
    root.appendChild(this._frameArtwork(player.current?.thumbnail_url, ""));
    root.appendChild(
      this._el("div", { class: "player-copy" }, [
        this._el("strong", { text: title }),
        this._el("span", { text: meta }),
      ])
    );

    if (player.transport_available && ["playing", "sending", "asleep"].includes(state)) {
      const disabled = state === "sending";
      const controls = this._el("div", { class: "player-controls" }, [
        this._iconButton(
          "mdi:skip-previous",
          "Previous",
          () => this._playerControl("previous"),
          { disabled, className: "desktop-control" }
        ),
        this._iconButton(
          player.paused ? "mdi:play" : "mdi:pause",
          player.paused ? "Play" : "Pause",
          () => this._playerControl(player.paused ? "play" : "pause"),
          { primary: !disabled, disabled }
        ),
        this._iconButton(
          "mdi:skip-next",
          "Next",
          () => this._playerControl("next"),
          { disabled, className: "desktop-control" }
        ),
      ]);
      root.appendChild(controls);
    }

    const progress = state === "sending"
      ? player.sending_progress
      : state === "playing" && player.interval
        ? Math.min(100, Math.round(((player.seconds_elapsed || 0) / player.interval) * 100))
        : null;
    if (progress != null && state !== "asleep") {
      root.appendChild(
        this._el(
          "div",
          {
            class: `player-progress${state === "sending" ? " sending" : ""}`,
            role: "progressbar",
            "aria-label": state === "sending" ? "Sending progress" : "Playlist progress",
            "aria-valuemin": "0",
            "aria-valuemax": "100",
            "aria-valuenow": String(progress),
          },
          [this._el("span", { style: `width:${progress}%` })]
        )
      );
    }
    root.appendChild(this._el("span", { class: "shell-spacer" }));

    if (state === "unreachable") {
      root.append(
        this._el("button", {
          class: "player-action",
          text: "Retry",
          onclick: () => this._playerControl("retry"),
        }),
        this._el("button", {
          class: "player-action desktop-control",
          text: "Device page",
          onclick: () => window.open(`http://${frame.host}/`, "_blank", "noopener"),
        })
      );
    } else if (state === "idle") {
      root.appendChild(
        this._el("button", {
          class: "player-action primary",
          text: "Choose a playlist",
          onclick: () => this._openLegacySlides(),
        })
      );
    } else {
      if (player.waiting_count) {
        root.appendChild(
          this._el("span", {
            class: "small-tag desktop-control",
            text: `${player.waiting_count} waiting`,
          })
        );
      }
      const queueButton = this._el(
        "button",
        {
          class: "queue-toggle",
          "aria-expanded": String(this._queueOpen),
          "aria-controls": "queueSheet",
          onclick: () => this._setQueueOpen(!this._queueOpen),
        },
        [
          this._el("span", { class: "queue-label", text: "Queue" }),
          document.createTextNode(String(player.queue_count)),
          this._el("ha-icon", {
            icon: this._queueOpen ? "mdi:chevron-down" : "mdi:chevron-up",
          }),
        ]
      );
      root.appendChild(queueButton);
    }
    root.appendChild(
      this._iconButton(
        "mdi:dots-horizontal",
        "Open frame menu",
        () => {
          this._frameMenuOpen = !this._frameMenuOpen;
          this._appMenuOpen = false;
          this._renderAppMenu();
          this._renderPlayer();
        },
        { className: "frame-overflow" }
      )
    );
    if (this._frameMenuOpen) root.appendChild(this._frameMenu(frame));
  }

  _frameMenu(frame) {
    const menu = this._el("div", { class: "shell-menu frame-menu" });
    menu.appendChild(this._el("div", { class: "menu-heading", text: frame.title }));
    const add = (label, action) => {
      menu.appendChild(
        this._el("button", {
          class: "menu-item",
          text: label,
          onclick: () => {
            this._frameMenuOpen = false;
            this._renderPlayer();
            action();
          },
        })
      );
    };
    add("Refresh panel now", () => this._playerControl("refresh"));
    if (!frame.charging) add("Put to sleep", () => this._playerControl("sleep"));
    add("Device page", () => window.open(`http://${frame.host}/`, "_blank", "noopener"));
    return menu;
  }

  async _playerControl(action) {
    const frame = this._activeFrame();
    if (!frame) return;
    const entryId = frame.entry_id;
    const generation = ++this._playerGeneration;
    const sending = ["previous", "next", "refresh"].includes(action);
    if (sending) this._beginOptimisticSend(this._player?.current?.title, frame);
    let player;
    try {
      player = await this._api("player/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entry_id: frame.entry_id, action }),
      });
    } catch (_err) {
      if (
        entryId === this._selectedFrameId &&
        generation === this._playerGeneration
      ) {
        await this._loadPlayer().catch(() => {});
        this._toast(`${frame.title} did not answer. Check the frame before trying again.`, true);
      }
      return;
    }
    if (
      entryId !== this._selectedFrameId ||
      generation !== this._playerGeneration
    ) return;
    this._player = player;
    if (player.state === "asleep" && sending) {
      this._toast(
        `${frame.title} is asleep. It will show this when it wakes.`
      );
    }
    this._renderPlayer();
    this._renderQueue();
    try {
      await this._loadFrames();
    } catch (_err) {
      // The command already succeeded. Keep its returned player state and let
      // the periodic refresh retry frame metadata without suggesting a resend.
    }
  }

  _beginOptimisticSend(title, frame = this._activeFrame()) {
    if (!frame) return;
    if (this._player && frame.entry_id === this._selectedFrameId) {
      this._player = {
        ...this._player,
        state: "sending",
        sending: true,
        sending_progress: 0,
        current: {
          ...this._player.current,
          title: title || this._player.current?.title,
        },
      };
      this._restartPlayerRefresh();
      this._renderPlayer();
    }
    this._toast(`Sending to ${frame.title}. The panel takes about 30 seconds.`);
  }

  _setQueueOpen(open) {
    const wasOpen = this._queueOpen;
    this._queueOpen = Boolean(open && this._player);
    this._rowMenu = null;
    const sheet = this.shadowRoot.getElementById("queueSheet");
    const backdrop = this.shadowRoot.getElementById("queueBackdrop");
    const content = this.shadowRoot.getElementById("legacyViewport");
    if (sheet) sheet.hidden = !this._queueOpen;
    if (backdrop) backdrop.hidden = !this._queueOpen;
    if (content) {
      content.classList.toggle("queue-open", this._queueOpen);
      content.inert = this._queueOpen;
    }
    this._renderQueue();
    this._renderPlayer();
    if (this._queueOpen) sheet?.focus();
    else if (wasOpen) this.shadowRoot.querySelector(".queue-toggle")?.focus();
  }

  _renderQueue() {
    const root = this.shadowRoot.getElementById("queueSheet");
    if (!root) return;
    const focus = this._captureFocus(root);
    this._renderQueueContent(root);
    this._restoreFocus(root, focus);
  }

  _renderQueueContent(root) {
    root.hidden = !this._queueOpen;
    root.innerHTML = "";
    if (!this._queueOpen || !this._player) return;
    root.appendChild(this._el("div", { class: "queue-grab", "aria-hidden": "true" }));
    const player = this._player;

    if (player.hand_queue.length) {
      root.appendChild(
        this._queueHeader("Next in queue · added by you, played once", [
          this._el("button", {
            class: "text-button",
            text: "Clear",
            onclick: () => this._safeQueueMutation({ action: "clear" }),
          }),
        ])
      );
      root.appendChild(this._queueList("queue", player.hand_queue, true));
    }

    const playlist = player.playlist;
    if (playlist.name) {
      const title = playlist.shuffle
        ? `Next from ${playlist.name}, shuffled`
        : `Next from ${playlist.name}`;
      const actions = [];
      if (playlist.interval) {
        actions.push(
          this._el("button", {
            class: "text-button small-tag",
            text: this._formatInterval(playlist.interval),
            onclick: () => this._openLegacySlides(),
          })
        );
      }
      actions.push(
        this._el("button", {
          class: "text-button",
          text: "Open playlist",
          onclick: () => this._openLegacySlides(),
        })
      );
      root.appendChild(this._queueHeader(title, actions));
      if (this._showPlaylistWarning) {
        root.appendChild(
          this._el("div", {
            class: "queue-note",
            text: "Reordering here changes the playlist.",
          })
        );
      }
      if (playlist.items.length) {
        root.appendChild(
          this._queueList("playlist", playlist.items, !playlist.shuffle)
        );
      }
    } else {
      const empty = this._el("div", { class: "queue-empty" }, [
        this._el("div", { text: "No playlist on this frame." }),
        this._el("button", {
          class: "player-action primary",
          text: "Choose a playlist",
          onclick: () => this._openLegacySlides(),
        }),
      ]);
      root.appendChild(empty);
    }
  }

  _queueHeader(title, actions = []) {
    return this._el("div", { class: "queue-section-header" }, [
      this._el("span", { class: "queue-section-title", text: title }),
      ...actions,
    ]);
  }

  _queueList(section, items, reorderable) {
    const list = this._el("ol", {
      class: "queue-list",
      "aria-label": section === "queue" ? "Next in queue" : "Next from playlist",
    });
    items.forEach((item, index) => {
      list.appendChild(this._queueRow(section, item, index, items.length, reorderable));
    });
    return list;
  }

  _queueRow(section, item, index, count, reorderable) {
    const grip = this._el("button", {
      class: "drag-grip",
      text: "⠿",
      "aria-label": `Reorder ${item.title}`,
      title: `Reorder ${item.title}`,
    });
    grip.disabled = !reorderable;
    const row = this._el("div", {
      class: "queue-row",
      "data-section": section,
      "data-index": String(index),
    });
    row.append(
      grip,
      this._frameArtwork(item.thumbnail_url, `${item.title}`),
      this._el("div", { class: "queue-copy" }, [
        this._el("strong", { text: item.title }),
        this._el("span", { text: item.meta }),
      ])
    );
    if (section === "queue") {
      row.appendChild(
        this._iconButton("mdi:close", `Remove ${item.title}`, () =>
          this._safeQueueMutation({ action: "remove", index, slide_id: item.id })
        )
      );
    }
    row.appendChild(
      this._iconButton("mdi:dots-horizontal", `Move ${item.title}`, () => {
        const key = `${section}:${index}`;
        this._rowMenu = this._rowMenu === key ? null : key;
        this._renderQueue();
      })
    );
    if (reorderable) this._wireQueueDrag(row, grip, section, index);

    const children = [row];
    if (this._rowMenu === `${section}:${index}`) {
      const actions = this._el("div", { class: "row-actions" });
      const add = (label, destination) => {
        const button = this._el("button", {
          class: "text-button",
          text: label,
          onclick: () => this._moveQueueItem(section, index, destination),
        });
        button.disabled = destination === index;
        actions.appendChild(button);
      };
      add("Move up", Math.max(0, index - 1));
      add("Move down", Math.min(count - 1, index + 1));
      add("Move to top", 0);
      add("Move to bottom", count - 1);
      children.push(actions);
    }
    return this._el("li", {}, children);
  }

  _wireQueueDrag(row, grip, section, index) {
    row.draggable = true;
    row.addEventListener("dragstart", (event) => {
      this._drag = { section, index };
      row.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", `${section}:${index}`);
      const ghost = row.cloneNode(true);
      ghost.className = "queue-row drag-ghost";
      ghost.style.left = "-1000px";
      ghost.style.top = "-1000px";
      this.shadowRoot.getElementById("appShell").appendChild(ghost);
      event.dataTransfer.setDragImage(ghost, 60, 36);
      window.setTimeout(() => ghost.remove(), 0);
    });
    row.addEventListener("dragover", (event) => {
      if (!this._drag || this._drag.section !== section) return;
      event.preventDefault();
      const after = event.clientY > row.getBoundingClientRect().top + row.offsetHeight / 2;
      this._markInsertion(row, after);
    });
    row.addEventListener("drop", (event) => {
      if (!this._drag || this._drag.section !== section) return;
      event.preventDefault();
      const after = event.clientY > row.getBoundingClientRect().top + row.offsetHeight / 2;
      let destination = index + (after ? 1 : 0);
      if (destination > this._drag.index) destination -= 1;
      const source = this._drag.index;
      this._clearInsertion();
      this._drag = null;
      this._moveQueueItem(section, source, destination);
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      this._clearInsertion();
      this._drag = null;
    });

    grip.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse") return;
      const touch = {
        pointerId: event.pointerId,
        section,
        index,
        row,
        grip,
        startX: event.clientX,
        startY: event.clientY,
        x: event.clientX,
        y: event.clientY,
        active: false,
        destination: index,
        scrollDirection: 0,
        ghost: null,
        timer: null,
      };
      this._cancelTouchDrag();
      this._touchDrag = touch;
      grip.setPointerCapture(event.pointerId);
      touch.timer = window.setTimeout(() => this._startTouchDrag(), 400);
    });
    grip.addEventListener("pointermove", (event) => this._moveTouchDrag(event));
    grip.addEventListener("pointerup", (event) => this._finishTouchDrag(event));
    grip.addEventListener("pointercancel", () => this._cancelTouchDrag());
  }

  _startTouchDrag() {
    const drag = this._touchDrag;
    if (!drag) return;
    drag.active = true;
    drag.row.classList.add("dragging");
    drag.ghost = drag.row.cloneNode(true);
    drag.ghost.className = "queue-row drag-ghost";
    this.shadowRoot.getElementById("appShell").appendChild(drag.ghost);
    this._positionTouchGhost();
    if (window.navigator.vibrate) window.navigator.vibrate(10);
  }

  _moveTouchDrag(event) {
    const drag = this._touchDrag;
    if (!drag || event.pointerId !== drag.pointerId) return;
    drag.x = event.clientX;
    drag.y = event.clientY;
    if (!drag.active) {
      if (Math.hypot(drag.x - drag.startX, drag.y - drag.startY) > 8) {
        this._cancelTouchDrag();
      }
      return;
    }
    event.preventDefault();
    this._positionTouchGhost();
    const target = this.shadowRoot
      .elementsFromPoint(drag.x, drag.y)
      .find((element) => element.classList?.contains("queue-row"));
    if (target && target.dataset.section === drag.section) {
      const targetIndex = Number(target.dataset.index);
      const after = drag.y > target.getBoundingClientRect().top + target.offsetHeight / 2;
      let destination = targetIndex + (after ? 1 : 0);
      if (destination > drag.index) destination -= 1;
      drag.destination = destination;
      this._markInsertion(target, after);
    }
    const sheet = this.shadowRoot.getElementById("queueSheet");
    const rect = sheet.getBoundingClientRect();
    drag.scrollDirection = drag.y < rect.top + 48 ? -1 : drag.y > rect.bottom - 48 ? 1 : 0;
    this._runTouchAutoscroll();
  }

  _positionTouchGhost() {
    const drag = this._touchDrag;
    if (!drag?.ghost) return;
    drag.ghost.style.left = `${drag.x - 60}px`;
    drag.ghost.style.top = `${drag.y - 36}px`;
  }

  _runTouchAutoscroll() {
    const drag = this._touchDrag;
    if (!drag?.active || !drag.scrollDirection || this._touchAutoScrollFrame) return;
    const tick = () => {
      this._touchAutoScrollFrame = null;
      const current = this._touchDrag;
      if (!current?.active || !current.scrollDirection) return;
      this.shadowRoot.getElementById("queueSheet").scrollTop +=
        current.scrollDirection * 12;
      this._touchAutoScrollFrame = window.requestAnimationFrame(tick);
    };
    this._touchAutoScrollFrame = window.requestAnimationFrame(tick);
  }

  _finishTouchDrag(event) {
    const drag = this._touchDrag;
    if (!drag || event.pointerId !== drag.pointerId) return;
    const { active, section, index, destination } = drag;
    this._cancelTouchDrag();
    if (active) this._moveQueueItem(section, index, destination);
  }

  _cancelTouchDrag() {
    const drag = this._touchDrag;
    if (drag) {
      window.clearTimeout(drag.timer);
      drag.row?.classList.remove("dragging");
      drag.ghost?.remove();
    }
    if (this._touchAutoScrollFrame) {
      window.cancelAnimationFrame(this._touchAutoScrollFrame);
      this._touchAutoScrollFrame = null;
    }
    this._touchDrag = null;
    this._clearInsertion();
  }

  _markInsertion(row, after) {
    this._clearInsertion();
    row.classList.add(after ? "insert-after" : "insert-before");
  }

  _clearInsertion() {
    for (const row of this.shadowRoot.querySelectorAll(
      ".queue-row.insert-before, .queue-row.insert-after"
    )) {
      row.classList.remove("insert-before", "insert-after");
    }
  }

  async _moveQueueItem(section, source, destination) {
    const items = section === "queue"
      ? this._player?.hand_queue
      : this._player?.playlist?.items;
    if (!items || source === destination || !items[source]) return;
    const entryId = this._selectedFrameId;
    destination = Math.max(0, Math.min(items.length - 1, destination));
    const snapshot = JSON.parse(JSON.stringify(this._player));
    const [moved] = items.splice(source, 1);
    items.splice(destination, 0, moved);
    this._rowMenu = null;
    if (section === "playlist" && !this._playlistWarningSeen()) {
      this._showPlaylistWarning = true;
      this._markPlaylistWarningSeen();
    }
    this._renderQueue();
    const generation = ++this._playerGeneration;
    try {
      const response = await this._queueMutation(
        {
          action: "reorder",
          section,
          ordered_ids: items.map((item) => item.id),
        },
        false,
        generation
      );
      if (response) this._player = response;
      this._renderPlayer();
      this._renderQueue();
      this._announceQueue("Queue reordered.");
    } catch (_err) {
      if (
        entryId !== this._selectedFrameId ||
        generation !== this._playerGeneration
      ) return;
      this._player = snapshot;
      this._renderPlayer();
      this._renderQueue();
      this._toast("The queue changed. Your previous order is restored.", true);
    }
  }

  _playlistWarningSeen() {
    const frame = this._activeFrame();
    if (!frame) return true;
    try {
      return window.localStorage.getItem(`fraimic:queue-warning:${frame.entry_id}`) === "1";
    } catch (_err) {
      return false;
    }
  }

  _markPlaylistWarningSeen() {
    const frame = this._activeFrame();
    if (!frame) return;
    try {
      window.localStorage.setItem(`fraimic:queue-warning:${frame.entry_id}`, "1");
    } catch (_err) {
      /* localStorage may be unavailable */
    }
  }

  async _queueMutation(payload, render = true, generation) {
    const frame = this._activeFrame();
    if (!frame) return null;
    const entryId = frame.entry_id;
    const response = await this._api("player/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entry_id: frame.entry_id, ...payload }),
    });
    if (
      entryId !== this._selectedFrameId ||
      generation !== this._playerGeneration
    ) return null;
    if (render) {
      this._player = response;
      this._rowMenu = null;
      this._renderPlayer();
      this._renderQueue();
    }
    return response;
  }

  async _safeQueueMutation(payload) {
    const entryId = this._selectedFrameId;
    const generation = ++this._playerGeneration;
    try {
      const player = await this._queueMutation(payload, true, generation);
      if (player) {
        this._announceQueue(payload.action === "clear" ? "Queue cleared." : "Removed from queue.");
      }
    } catch (_err) {
      if (
        entryId !== this._selectedFrameId ||
        generation !== this._playerGeneration
      ) return;
      this._toast("The queue changed. Try again.", true);
      await this._loadPlayer().catch(() => {});
    }
  }

  async _queueLegacySlide(slideId, playNext) {
    const frame = this._activeFrame();
    if (!frame) return;
    const entryId = frame.entry_id;
    const generation = ++this._playerGeneration;
    try {
      const player = await this._queueMutation(
        { action: "add", slide_id: slideId, play_next: playNext },
        false,
        generation
      );
      if (!player) return;
      this._player = player;
      this._renderPlayer();
      this._renderQueue();
      if (playNext) {
        this._toast(`Playing next on ${frame.title}.`);
        this._announceQueue("Added to play next.");
      } else {
        const waiting = this._player.hand_queue.length;
        this._toast(`Added to the queue, ${waiting} waiting.`);
        this._announceQueue("Added to queue.");
      }
    } catch (_err) {
      if (
        entryId !== this._selectedFrameId ||
        generation !== this._playerGeneration
      ) return;
      this._toast("The queue changed. Try again.", true);
    }
  }

  _announceQueue(message) {
    const status = this.shadowRoot.getElementById("queueStatus");
    if (!status) return;
    status.textContent = "";
    window.setTimeout(() => { status.textContent = message; }, 0);
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
    else if (this._tab === "screens") this._renderScreens(content);
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
        this._setAlbumFilter(ev.target.value);
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

    // Multi-select mode: checkbox overlays + bulk actions.
    if (this._images.length) {
      toolbar.appendChild(
        this._el("button", {
          class: "btn",
          text: this._selectMode ? "Done selecting" : "Select",
          onclick: () => {
            this._selectMode = !this._selectMode;
            this._selected.clear();
            this._renderTab();
          },
        })
      );
    }
    if (this._selectMode && this._selected.size) {
      toolbar.append(
        this._el("button", {
          class: "btn danger",
          text: `Delete (${this._selected.size})`,
          onclick: () => this._bulkDelete(),
        }),
        this._el("button", {
          class: "btn",
          text: `Add to album (${this._selected.size})`,
          onclick: () => this._bulkAddToAlbum(),
        })
      );
    }
    root.appendChild(toolbar);

    // Album strip with cover art (only on the unfiltered view).
    if (!this._albumFilter && this._albums.length > 1) {
      const strip = this._el("div", { class: "albumstrip" });
      for (const album of this._albums) {
        const inAlbum = this._images.filter((image) => image.albums.includes(album));
        if (!inAlbum.length) continue;
        const cover = this._el("img", { loading: "lazy" });
        this._lazyImg(cover, `${API}/library/thumb/${inAlbum[0].image_id}`);
        const cap = this._el("div", { class: "cap" });
        cap.append(document.createTextNode(`${album} `), this._el("span", { text: `(${inAlbum.length})` }));
        strip.appendChild(
          this._el(
            "div",
            {
              class: "albumcard",
              onclick: () => {
                this._setAlbumFilter(album);
                this._renderTab();
              },
            },
            [cover, cap]
          )
        );
      }
      if (strip.childElementCount) root.appendChild(strip);
    }

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

  _setAlbumFilter(album) {
    if (album === this._albumFilter) return;
    this._albumFilter = album;
    this._selected.clear();
  }

  _libraryCard(image) {
    const img = this._el("img", { loading: "lazy" });
    this._lazyImg(img, `${API}/library/thumb/${image.image_id}`);
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
    const thumbwrap = this._el("div", { class: "thumbwrap" }, [img]);
    const selected = this._selected.has(image.image_id);
    if (this._selectMode && selected) {
      thumbwrap.appendChild(this._el("div", { class: "checkmark", text: "✓" }));
    }
    const children = [thumbwrap, body];
    if (!this._selectMode) {
      children.push(
        this._el("div", { class: "actions" }, [
          this._el("button", {
            class: "btn",
            text: "Send",
            onclick: () => this._openCropEditor(image, { send: true }),
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
        ])
      );
    }
    const props = { class: "card" };
    if (this._selectMode) {
      props.class = `card selectable${selected ? " selected" : ""}`;
      props.onclick = () => {
        if (this._selected.has(image.image_id)) this._selected.delete(image.image_id);
        else this._selected.add(image.image_id);
        this._renderTab();
      };
    }
    return this._el("div", props, children);
  }

  async _bulkDelete() {
    const count = this._selected.size;
    if (!confirm(`Remove ${count} image${count === 1 ? "" : "s"} from the library? This can't be undone.`)) {
      return;
    }
    let failed = 0;
    for (const imageId of this._selected) {
      try {
        await this._api(`library/image/${imageId}`, { method: "DELETE" });
      } catch (_err) {
        failed += 1;
      }
    }
    this._selected.clear();
    this._selectMode = false;
    await Promise.all([this._loadLibrary(), this._loadScenes()]);
    this._renderTab();
    this._toast(failed ? `Deleted with ${failed} failure(s)` : `Deleted ${count} image${count === 1 ? "" : "s"}`, Boolean(failed));
  }

  async _bulkAddToAlbum() {
    const album = prompt("Add selected images to album:", this._albumFilter || "");
    if (!album || !album.trim()) return;
    const name = album.trim();
    let failed = 0;
    for (const imageId of this._selected) {
      const image = this._images.find((entry) => entry.image_id === imageId);
      if (!image || image.albums.includes(name)) continue;
      try {
        await this._api(`library/image/${imageId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ albums: [...image.albums, name] }),
        });
      } catch (_err) {
        failed += 1;
      }
    }
    this._selected.clear();
    this._selectMode = false;
    await this._loadLibrary();
    this._renderTab();
    this._toast(failed ? `Tagged with ${failed} failure(s)` : `Added to "${name}"`, Boolean(failed));
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

  /* Normalized 0-1 point maps between original space and a display rotated
   * ``r`` degrees clockwise. */
  static _rotatePoint(x, y, r) {
    if (r === 90) return [1 - y, x];
    if (r === 180) return [1 - x, 1 - y];
    if (r === 270) return [y, 1 - x];
    return [x, y];
  }

  static _mapBox(box, r, toDisplay) {
    const rot = toDisplay ? r : (360 - r) % 360;
    const [ax, ay] = FraimicPanel._rotatePoint(box[0], box[1], rot);
    const [bx, by] = FraimicPanel._rotatePoint(box[2], box[3], rot);
    return [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)];
  }

  /* The crop/rotate window. Options:
   *   send:  true makes the primary action save the crop and send the image
   *          to the selected frame (the flow every "choose an image" enters).
   *   frame: preselect a target frame (scene editor rows pass theirs).
   *   stack: open on top of the current dialog and return to it on close. */
  async _openCropEditor(image, { send = false, frame: presetFrame = null, stack = false } = {}) {
    if (!this._frames.length) {
      this._toast("No frames are loaded", true);
      return;
    }
    let frame = presetFrame || this._frames[0];
    const rotationFor = (f) => {
      const size = this._effectiveSize(f);
      const saved = image.rotations && image.rotations[`${size.width}x${size.height}`];
      return [90, 180, 270].includes(saved) ? saved : 0;
    };
    let rotation = rotationFor(frame);

    const img = this._el("img", { draggable: "false" });
    const box = this._el("div", { id: "cropBox" });
    for (const corner of ["nw", "ne", "sw", "se"]) {
      box.appendChild(this._el("div", { class: `handle ${corner}` }));
    }
    const stage = this._el("div", { id: "cropStage" }, [img, box]);

    const frameSelect = this._el("select", {
      onchange: () => {
        frame = this._frames[Number(frameSelect.value)];
        rotation = rotationFor(frame);
        if (previewing) {
          revokePreview();
          box.style.display = "";
          previewing = false;
          previewBtn.textContent = "Preview on e-ink";
        }
        renderStage();
      },
    });
    this._frames.forEach((f, index) => {
      const option = this._el("option", { value: String(index), text: this._frameLabel(f) });
      if (f === frame) option.selected = true;
      frameSelect.appendChild(option);
    });

    // Normalized box state [x0, y0, x1, y1] in DISPLAY space (the image as
    // shown, i.e. already rotated); converted to original space on save.
    let norm = null;
    let imageReady = false;
    let preserveOnLoad = false;
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

    img.addEventListener("load", () => {
      imageReady = true;
      placeBox(preserveOnLoad && norm ? [...norm] : this._initialBox(image, frame, rotation));
      preserveOnLoad = false;
    });
    img.addEventListener("error", () => {
      imageReady = false;
      box.style.display = "none";
      this._toast("Could not load a browser-renderable crop image", true);
    });

    // The rotated view is drawn locally: the base thumbnail is fetched once
    // and redrawn onto a canvas at the current rotation.
    const baseImg = new Image();
    const renderStage = () => {
      if (!baseImg.naturalWidth) return;
      let next = baseImg.src;
      if (rotation) {
        const swap = rotation === 90 || rotation === 270;
        const canvas = document.createElement("canvas");
        canvas.width = swap ? baseImg.naturalHeight : baseImg.naturalWidth;
        canvas.height = swap ? baseImg.naturalWidth : baseImg.naturalHeight;
        const ctx = canvas.getContext("2d");
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate((rotation * Math.PI) / 180);
        ctx.drawImage(baseImg, -baseImg.naturalWidth / 2, -baseImg.naturalHeight / 2);
        next = canvas.toDataURL("image/jpeg", 0.92);
      }
      if (img.src === next) {
        // Same pixels (e.g. frame changed, rotation didn't): the load event
        // won't refire, so place the box directly.
        placeBox(preserveOnLoad && norm ? [...norm] : this._initialBox(image, frame, rotation));
        preserveOnLoad = false;
        return;
      }
      img.src = next;
    };
    baseImg.addEventListener("load", renderStage);
    baseImg.addEventListener("error", () => {
      imageReady = false;
      box.style.display = "none";
      this._toast("Could not load a browser-renderable crop image", true);
    });
    this._signedUrl(`${API}/library/thumb/${image.image_id}`)
      .then((url) => {
        baseImg.src = url;
      })
      .catch(() => this._toast("Could not load the crop image", true));

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

    // "Preview on e-ink": server-renders the current box through the real
    // dither pipeline (nothing saved/uploaded) and swaps it into the stage.
    let previewing = false;
    let previewObjectUrl = null;
    const revokePreview = () => {
      if (previewObjectUrl) {
        URL.revokeObjectURL(previewObjectUrl);
        previewObjectUrl = null;
      }
    };
    const exitPreview = () => {
      preserveOnLoad = true;
      revokePreview();
      box.style.display = "";
      previewing = false;
      previewBtn.textContent = "Preview on e-ink";
      renderStage();
    };
    const previewBtn = this._el("button", {
      class: "btn",
      text: "Preview on e-ink",
      onclick: async () => {
        if (previewing) {
          exitPreview();
          return;
        }
        if (!imageReady || !norm) {
          this._toast("Crop image is not ready yet", true);
          return;
        }
        previewBtn.disabled = true;
        previewBtn.textContent = "Rendering…";
        try {
          const resp = await this._hass.fetchWithAuth(
            `${API}/library/image/${image.image_id}/preview`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                entry_id: frame.entry_id,
                box: FraimicPanel._mapBox(norm, rotation, false),
                rotate: rotation,
              }),
            }
          );
          if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.message || resp.statusText);
          }
          const blob = await resp.blob();
          preserveOnLoad = true;
          revokePreview();
          previewObjectUrl = URL.createObjectURL(blob);
          img.src = previewObjectUrl;
          box.style.display = "none";
          previewing = true;
          previewBtn.textContent = "Back to crop";
        } catch (err) {
          this._toast(err.message, true);
        } finally {
          previewBtn.disabled = false;
        }
      },
    });

    const rotateBtn = this._el("button", {
      class: "btn",
      text: "Rotate 90°",
      onclick: () => {
        if (previewing) exitPreview();
        rotation = (rotation + 90) % 360;
        rotateBtn.textContent = rotation ? `Rotate 90° (${rotation}°)` : "Rotate 90°";
        norm = null; // the box is re-fit for the new orientation on load
        renderStage();
      },
    });
    if (rotation) rotateBtn.textContent = `Rotate 90° (${rotation}°)`;

    const saveCrop = async () => {
      const size = this._effectiveSize(frame);
      await this._api(`library/image/${image.image_id}/crop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          width: size.width,
          height: size.height,
          box: FraimicPanel._mapBox(norm, rotation, false),
          rotate: rotation,
        }),
      });
    };
    const save = async () => {
      if (!imageReady || !norm) {
        this._toast("Crop image is not ready yet", true);
        return;
      }
      try {
        await saveCrop();
        this._closeDialog();
        await this._loadLibrary();
        this._renderTab();
        this._toast("Crop saved — cached renders for this size were invalidated");
      } catch (err) {
        this._toast(err.message, true);
      }
    };
    const saveAndSend = async (ev) => {
      if (!imageReady || !norm) {
        this._toast("Crop image is not ready yet", true);
        return;
      }
      ev.target.disabled = true;
      try {
        await saveCrop();
        this._closeDialog();
        this._beginOptimisticSend(image.filename, frame);
        const result = await this._api("library/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image_id: image.image_id,
            entry_ids: [frame.entry_id],
          }),
        });
        const failed = Object.values(result.results).filter((r) => !r.ok);
        if (failed.length) {
          this._toast(`${frame.title} did not answer. Check the frame before trying again.`, true);
          await this._loadPlayer().catch(() => {});
          return;
        }
        await Promise.all([this._loadPlayer(), this._loadFrames()]);
        const updatedFrame = this._frames.find(
          (candidate) => candidate.entry_id === frame.entry_id
        );
        if (updatedFrame?.asleep) {
          this._toast(`${frame.title} is asleep. It will show this when it wakes.`);
        }
        await this._loadLibrary();
        this._renderTab();
      } catch (_err) {
        await this._loadPlayer().catch(() => {});
        this._toast(`${frame.title} did not answer. Check the frame before trying again.`, true);
        ev.target.disabled = false;
      }
    };
    const clear = async () => {
      const size = this._effectiveSize(frame);
      try {
        await this._api(`library/image/${image.image_id}/crop`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ width: size.width, height: size.height, box: null, rotate: 0 }),
        });
        this._closeDialog();
        await this._loadLibrary();
        this._renderTab();
        this._toast("Crop and rotation cleared");
      } catch (err) {
        this._toast(err.message, true);
      }
    };

    const actions = [
      previewBtn,
      rotateBtn,
      this._el("button", { class: "btn", text: "Clear crop", onclick: clear }),
      this._el("button", { class: "btn", text: "Cancel", onclick: () => this._closeDialog() }),
    ];
    if (send) {
      actions.push(
        this._el("button", { class: "btn raised", text: "Save & send", onclick: saveAndSend })
      );
    } else {
      actions.push(this._el("button", { class: "btn raised", text: "Save", onclick: save }));
    }

    this._openDialog(
      `${send ? "Send" : "Crop"} — ${image.filename}`,
      [
        this._el("div", { class: "row" }, [
          this._el("label", { text: "Target frame" }),
          frameSelect,
        ]),
        stage,
      ],
      actions,
      false,
      revokePreview,
      stack
    );
  }

  _initialBox(image, frame, rotation = 0) {
    const size = this._effectiveSize(frame);
    const key = `${size.width}x${size.height}`;
    const savedRotation =
      image.rotations && [90, 180, 270].includes(image.rotations[key])
        ? image.rotations[key]
        : 0;
    // The saved crop was drawn at the saved rotation; at any other rotation
    // its aspect no longer matches the frame, so fall through to the default.
    if (rotation === savedRotation && image.crops && image.crops[key]) {
      return FraimicPanel._mapBox([...image.crops[key]], rotation, true);
    }
    // Default: the centered cover-crop the pipeline would use anyway, in
    // display space (source axes swap at 90°/270°).
    const target = size.width / size.height;
    const swap = rotation === 90 || rotation === 270;
    const sourceW = swap ? image.height : image.width;
    const sourceH = swap ? image.width : image.height;
    const source = sourceW && sourceH ? sourceW / sourceH : target;
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
          onclick: () => window.open(`http://${frame.host}/`, "_blank", "noopener"),
        }),
      ]);
      const highlight = frame.entry_id === this._highlightEntry;
      const card = this._el(
        "div",
        { class: highlight ? "card highlight" : "card" },
        [this._el("div", { class: "body" }, rows), actions]
      );
      grid.appendChild(card);
      if (highlight) setTimeout(() => card.scrollIntoView({ block: "center" }), 50);
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
        if (image) this._lazyImg(mini, `${API}/library/thumb/${image.image_id}`);
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
      select.addEventListener("change", () => {
        syncPreview();
        // Choosing an image is followed by the crop/rotate window for the
        // frame it was chosen for; closing it returns to this dialog.
        const chosen = this._images.find((entry) => entry.image_id === select.value);
        if (chosen) this._openCropEditor(chosen, { frame, stack: true });
      });
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
      const mappings = scene ? { ...scene.mappings } : {};
      for (const [entryId, select] of selects) {
        if (select.value) mappings[entryId] = select.value;
        else delete mappings[entryId];
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
    // Category filter chips.
    const categories = [...new Set(this._packs.map((pack) => pack.category))].sort();
    if (categories.length > 1) {
      const chiprow = this._el("div", { class: "chiprow" });
      const addChip = (label, value) => {
        chiprow.appendChild(
          this._el("button", {
            class: `fchip${this._packCategory === value ? " active" : ""}`,
            text: label,
            onclick: () => {
              this._packCategory = value;
              this._renderTab();
            },
          })
        );
      };
      addChip("All", "");
      for (const category of categories) addChip(category, category);
      root.appendChild(chiprow);
    }
    const packs = this._packCategory
      ? this._packs.filter((pack) => pack.category === this._packCategory)
      : this._packs;

    const grid = this._el("div", { class: "grid" });
    for (const pack of packs) {
      const imageCount = pack.image_count ?? pack.images.length;
      const installing = this._installingPacks.has(pack.id);
      const cover = this._el("img", { loading: "lazy", alt: pack.name });
      // Pack art is hot-linkable (GitHub raw / Commons thumb): no signing.
      cover.src = pack.cover_url || (pack.images[0] && pack.images[0].preview_url) || "";
      const thumbAttrs = {
        class: "thumbwrap",
        style: "cursor: zoom-in",
        onclick: () => this._openPackGallery(pack),
      };
      const thumbwrap = this._el("div", thumbAttrs, [cover]);
      const body = this._el("div", { class: "body" }, [
        this._el("div", { class: "title", text: pack.name }),
        this._el("span", { class: "chip", text: pack.category }),
        this._el("span", { class: "chip", text: `${imageCount} images` }),
        this._el("div", { class: "sub", text: pack.description || "" }),
        this._el("div", {
          class: "sub pack-installed-count",
          text: `${pack.installed_count}/${imageCount} installed · ${pack.attribution}`,
        }),
      ]);
      if (installing) {
        const progress = Math.min(pack.installed_count, imageCount);
        const percent = imageCount ? (progress / imageCount) * 100 : 0;
        body.appendChild(
          this._el(
            "div",
            {
              class: "pack-progress",
              "data-pack-progress": pack.id,
              role: "progressbar",
              "aria-label": `Installing ${pack.name}`,
              "aria-valuemin": "0",
              "aria-valuemax": String(imageCount),
              "aria-valuenow": String(progress),
            },
            [
              this._el("div", { class: "pack-progress-meta" }, [
                this._el("span", { text: "Downloading" }),
                this._el("span", {
                  class: "pack-progress-count",
                  text: `${progress} / ${imageCount}`,
                }),
              ]),
              this._el("div", { class: "pack-progress-track" }, [
                this._el("div", {
                  class: "pack-progress-fill",
                  style: `width:${percent}%`,
                }),
              ]),
            ]
          )
        );
      }
      // Remote-catalog covers hot-link the actual pack image, so the loaded
      // cover reveals the pack's true resolution for free. Some community
      // packs are thumbnail-sized (TV title cards ~300 px) and upscale badly
      // on the panel — badge them before the user installs.
      if (pack.images.some((image) => image.url === cover.src)) {
        this._onImageDims(cover, (width, height) => {
          if (Math.min(width, height) >= LOW_RES_SHORT_EDGE) return;
          body.insertBefore(
            this._el("span", {
              class: "chip warn",
              title: "These images are smaller than the frame's panel and will look soft",
              text: `Low resolution (${width}×${height})`,
            }),
            body.children[3]
          );
        });
      }
      const installBtn = this._el("button", {
        class: "btn raised",
        text: installing
          ? "Installing…"
          : pack.installed
            ? "Reinstall missing"
            : pack.installed_count
              ? "Resume install"
              : "Install",
        onclick: () => this._installPack(pack),
      });
      installBtn.disabled = installing;
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
      actions.appendChild(
        this._el("button", {
          class: "btn",
          text: "Gallery",
          onclick: () => this._openPackGallery(pack),
        })
      );
      grid.appendChild(this._el("div", { class: "card" }, [thumbwrap, body, actions]));
    }
    root.appendChild(grid);
  }

  async _installPack(pack) {
    if (this._installingPacks.has(pack.id)) return;
    this._packProgressAttempts = 0;
    this._installingPacks.add(pack.id);
    this._renderTab();
    this._schedulePackProgressPoll();
    this._toast(`Installing ${pack.name} — downloads are throttled, this can take a minute`);
    try {
      const result = await this._api(`packs/${pack.id}/install`, { method: "POST" });
      const failures = result.failed.length ? `, ${result.failed.length} failed` : "";
      this._toast(
        `${pack.name}: ${result.installed_count}/${result.total} installed${failures}`,
        Boolean(result.failed.length)
      );
    } catch (err) {
      this._toast(err.message, true);
    } finally {
      this._installingPacks.delete(pack.id);
      if (!this._installingPacks.size) {
        clearTimeout(this._packProgressTimer);
        this._packProgressTimer = null;
        this._packProgressAttempts = 0;
      }
      if (this.isConnected) {
        try {
          await Promise.all([this._loadLibrary(), this._loadScenes(), this._loadPacks()]);
        } catch (err) {
          this._toast(err.message, true);
        }
        if (this._tab === "packs") this._renderTab();
      }
    }
  }

  _schedulePackProgressPoll() {
    if (
      !this.isConnected ||
      this._packProgressTimer ||
      !this._installingPacks.size ||
      this._packProgressAttempts >= PACK_PROGRESS_MAX_ATTEMPTS
    ) {
      return;
    }
    this._packProgressTimer = setTimeout(async () => {
      this._packProgressTimer = null;
      if (!this.isConnected) return;
      this._packProgressAttempts += 1;
      try {
        const data = await this._api("packs/progress");
        if (!this.isConnected || !this._installingPacks.size) return;
        const progressById = data.packs || {};
        const packsById = new Map(this._packs.map((pack) => [pack.id, pack]));
        for (const progressNode of this.shadowRoot.querySelectorAll(
          "[data-pack-progress]"
        )) {
          const current = packsById.get(progressNode.dataset.packProgress);
          if (!current) continue;
          const update = progressById[current.id];
          const total = update?.total ?? current.image_count ?? current.images.length;
          const completed = Math.min(
            update?.installed_count ?? current.installed_count,
            total
          );
          const percent = total ? (completed / total) * 100 : 0;
          current.installed_count = completed;
          progressNode.setAttribute("aria-valuemax", String(total));
          progressNode.setAttribute("aria-valuenow", String(completed));
          progressNode.querySelector(".pack-progress-count").textContent =
            `${completed} / ${total}`;
          progressNode.querySelector(".pack-progress-fill").style.width = `${percent}%`;
          progressNode.parentElement.querySelector(".pack-installed-count").textContent =
            `${completed}/${total} installed · ${current.attribution}`;
        }
      } catch (_err) {
        // The install request owns error reporting; a missed poll is harmless.
      } finally {
        if (this.isConnected) this._schedulePackProgressPoll();
      }
    }, 1000);
  }

  /* Pre-install browsing: a simple prev/next carousel over the pack's
   * hot-linkable preview URLs, with per-image source attribution. */
  async _openPackGallery(pack) {
    if (!pack.images.length) {
      this._toast(`Loading ${pack.name} gallery…`);
      try {
        const result = await this._api(`packs/${pack.id}`);
        Object.assign(pack, result.pack);
      } catch (err) {
        this._toast(err.message, true);
        return;
      }
    }
    if (!pack.images.length) {
      this._toast(`${pack.name} currently has no artwork`, true);
      return;
    }
    let index = 0;
    const img = this._el("img", { alt: pack.name });
    const caption = this._el("div", { class: "caption" });
    const counter = this._el("span", { class: "sub" });

    const show = () => {
      const image = pack.images[index];
      img.src = image.preview_url || image.url;
      caption.innerHTML = "";
      caption.appendChild(document.createTextNode(image.title + " "));
      if (image.source_url) {
        caption.appendChild(
          this._el("a", { href: image.source_url, target: "_blank", text: "source" })
        );
      }
      counter.textContent = `${index + 1} / ${pack.images.length}`;
      // Remote packs preview the full image, so its natural size is the real
      // resolution — surface it (with a low-res nudge) while browsing.
      if ((image.preview_url || image.url) === image.url) {
        const current = index;
        this._onImageDims(img, (width, height) => {
          if (index !== current) return; // user already navigated away
          const soft = Math.min(width, height) < LOW_RES_SHORT_EDGE ? " · low res" : "";
          counter.textContent = `${index + 1} / ${pack.images.length} · ${width}×${height}${soft}`;
        });
      }
    };
    show();

    const nav = (delta) => {
      index = (index + delta + pack.images.length) % pack.images.length;
      show();
    };
    const gallery = this._el("div", { class: "gallery" }, [
      img,
      caption,
      this._el("div", { class: "navrow" }, [
        this._el("button", { class: "btn", text: "‹ Prev", onclick: () => nav(-1) }),
        counter,
        this._el("button", { class: "btn", text: "Next ›", onclick: () => nav(1) }),
      ]),
    ]);
    this._openDialog(pack.name, [gallery], [
      this._el("button", { class: "btn", text: "Close", onclick: () => this._closeDialog() }),
    ]);
  }

  /* ------------------------------------------------------------- screens */

  async _loadScreens() {
    if (!this._frames.length) {
      this._screens = [];
      return;
    }
    if (!this._screensEntry || !this._frames.some((f) => f.entry_id === this._screensEntry)) {
      this._screensEntry = this._activeFrame()?.entry_id || this._frames[0].entry_id;
    }
    if (!this._descriptors) {
      this._descriptors = await this._api("screens/descriptors");
    }
    this._screens = (await this._api(`screens?entry_id=${this._screensEntry}`)).screens;
  }

  _renderScreens(root) {
    if (!this._frames.length) {
      root.appendChild(this._el("div", { class: "empty", text: "No frames are loaded." }));
      return;
    }
    // Loaded lazily: screens are per-frame and need the descriptor metadata.
    if (!this._descriptors || this._screensLoadedFor !== this._screensEntry) {
      root.appendChild(this._el("div", { class: "empty", text: "Loading…" }));
      this._loadScreens()
        .then(() => {
          this._screensLoadedFor = this._screensEntry;
          if (this._tab === "screens") this._renderTab();
        })
        .catch((err) => this._toast(err.message, true));
      return;
    }

    const toolbar = this._el("div", { class: "toolbar" });
    if (this._frames.length > 1) {
      const frameSelect = this._el("select", {
        onchange: () => {
          this._selectFrame(frameSelect.value);
        },
      });
      for (const frame of this._frames) {
        const option = this._el("option", { value: frame.entry_id, text: this._frameLabel(frame) });
        if (frame.entry_id === this._screensEntry) option.selected = true;
        frameSelect.appendChild(option);
      }
      toolbar.appendChild(frameSelect);
    }
    toolbar.appendChild(
      this._el("button", {
        class: "btn raised",
        text: "New screen",
        onclick: () => this._openScreenEditor(null),
      })
    );
    root.appendChild(toolbar);

    if (!this._screens.length) {
      root.appendChild(
        this._el("div", {
          class: "empty",
          text: "No stored screens on this frame yet. A screen renders Home Assistant data (clock, weather, agenda, charts…) as e-ink artwork.",
        })
      );
      return;
    }
    const grid = this._el("div", { class: "grid" });
    for (const screen of this._screens) {
      const data = screen.data || {};
      const body = this._el("div", { class: "body" }, [
        this._el("div", { class: "title", text: screen.title }),
        this._el("span", { class: "chip", text: data.kind === "picture" ? "picture" : data.layout || "layout" }),
        this._el("span", {
          class: "chip",
          text: data.enabled === false ? "not in playlist" : `every ${Math.round((data.interval || 1800) / 60)} min`,
        }),
        this._el("div", {
          class: "sub",
          text:
            data.kind === "picture"
              ? data.url || data.entity || ""
              : (data.widgets || []).map((w) => w.type).join(" · "),
        }),
      ]);
      const actions = this._el("div", { class: "actions" }, [
        this._el("button", {
          class: "btn raised",
          text: "Edit",
          onclick: () => this._openScreenEditor(screen),
        }),
        this._el("button", {
          class: "btn",
          text: "Play next",
          onclick: () => this._queueLegacySlide(screen.screen_id, true),
        }),
        this._el("button", {
          class: "btn",
          text: "Add to queue",
          onclick: () => this._queueLegacySlide(screen.screen_id, false),
        }),
        this._el("button", {
          class: "btn",
          text: "Send now",
          onclick: async (ev) => {
            ev.target.disabled = true;
            const frame = this._frames.find(
              (candidate) => candidate.entry_id === this._screensEntry
            );
            if (!frame) {
              ev.target.disabled = false;
              this._toast("That frame is no longer loaded.", true);
              return;
            }
            this._beginOptimisticSend(screen.title, frame);
            try {
              await this._api("screens/send", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ entry_id: frame.entry_id, screen_id: screen.screen_id }),
              });
              await Promise.all([this._loadPlayer(), this._loadFrames()]);
              const updatedFrame = this._frames.find(
                (candidate) => candidate.entry_id === frame.entry_id
              );
              if (updatedFrame?.asleep) {
                this._toast(`${frame.title} is asleep. It will show this when it wakes.`);
              }
            } catch (_err) {
              await this._loadPlayer().catch(() => {});
              this._toast(`${frame.title} did not answer. Check the frame before trying again.`, true);
            } finally {
              ev.target.disabled = false;
            }
          },
        }),
        this._el("button", {
          class: "btn danger",
          text: "Delete",
          onclick: async () => {
            if (!confirm(`Delete screen "${screen.title}"?`)) return;
            try {
              await this._api(`screens/${screen.screen_id}?entry_id=${this._screensEntry}`, {
                method: "DELETE",
              });
              this._screensLoadedFor = null;
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

  /* The WYSIWYG editor: form on the left, a live server-rendered preview on
   * the right. Every change re-renders the actual e-ink output (debounced)
   * through the same pipeline that feeds the frame — what you see is exactly
   * what gets uploaded. */
  _openScreenEditor(stored) {
    const descriptors = this._descriptors;
    const layouts = descriptors.layouts;
    const defaultLayout = layouts.quadrant ? "quadrant" : Object.keys(layouts)[0];

    // Editor state. `slots` maps slot name -> {type, values} (dashboard kind).
    const def = stored
      ? JSON.parse(JSON.stringify(stored.data))
      : {
          name: "New screen",
          kind: "dashboard",
          layout: "quadrant",
          background: "white",
          accent: "red",
          padding: 32,
          show_header: true,
          interval: 1800,
          enabled: true,
        };
    def.kind = def.kind || "dashboard";
    if (!layouts[def.layout]) def.layout = defaultLayout;
    if (!Array.isArray(def.widgets)) def.widgets = [];
    const slots = {};
    for (const widget of def.widgets || []) {
      const { type, slot, ...values } = widget;
      slots[slot] = { type, values };
    }
    const picture = { url: def.url || "", entity: def.entity || "", fit: def.fit || "", mode: def.mode || "" };

    // ---- collect(): form state -> screen dict (SCREEN_SCHEMA shape).
    const collect = () => {
      const screen = {
        name: def.name,
        kind: def.kind,
        background: def.background,
        accent: def.accent,
        padding: Number(def.padding) || 0,
        show_header: Boolean(def.show_header),
        interval: Number(def.interval) || 1800,
        enabled: Boolean(def.enabled),
      };
      if (def.windows) screen.windows = def.windows;
      if (def.kind === "picture") {
        if (picture.url) screen.url = picture.url;
        if (picture.entity) screen.entity = picture.entity;
        if (picture.fit) screen.fit = picture.fit;
        if (picture.mode) screen.mode = picture.mode;
        return screen;
      }
      screen.layout = def.layout;
      screen.widgets = [];
      for (const slot of layouts[def.layout]) {
        const assigned = slots[slot];
        if (!assigned || !assigned.type) continue;
        const widget = { type: assigned.type, slot };
        const fields = descriptors.widgets[assigned.type].fields;
        for (const field of fields) {
          const value = assigned.values[field.key];
          if (value === undefined || value === "" || value === null) continue;
          widget[field.key] = value;
        }
        screen.widgets.push(widget);
      }
      return screen;
    };

    // ---- live preview.
    const previewImg = this._el("img", { alt: "preview" });
    const status = this._el("div", { class: "status" });
    let previewTimer = null;
    let previewSeq = 0;
    let previewObjectUrl = null;
    const revokeScreenPreview = () => {
      if (previewObjectUrl) {
        URL.revokeObjectURL(previewObjectUrl);
        previewObjectUrl = null;
      }
    };
    const cleanupPreview = () => {
      clearTimeout(previewTimer);
      previewTimer = null;
      previewSeq += 1;
      revokeScreenPreview();
    };
    const renderPreview = async () => {
      const seq = ++previewSeq;
      status.className = "status";
      status.textContent = "Rendering…";
      try {
        const resp = await this._hass.fetchWithAuth(`${API}/screens/preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entry_id: this._screensEntry, screen: collect() }),
        });
        if (!resp.ok) {
          let message;
          try {
            message = (await resp.json()).message;
          } catch (_err) {
            message = await resp.text().catch(() => resp.statusText);
          }
          throw new Error(message || resp.statusText);
        }
        const blob = await resp.blob();
        if (seq !== previewSeq) return; // a newer render superseded this one
        revokeScreenPreview();
        previewObjectUrl = URL.createObjectURL(blob);
        previewImg.src = previewObjectUrl;
        status.textContent = "Live preview — exactly what the frame will show";
      } catch (err) {
        if (seq !== previewSeq) return;
        status.className = "status err";
        status.textContent = err.message;
      }
    };
    const schedulePreview = () => {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(renderPreview, 900);
    };

    // ---- form building blocks.
    const entityListId = "fraimic-entity-list";
    const datalist = this._el("datalist", { id: entityListId });
    const interesting = /^(sensor|binary_sensor|weather|calendar|todo|camera|image|climate|light|switch|person|sun|media_player|cover|lock|number|counter|input_)/;
    for (const entityId of Object.keys(this._hass.states)
      .filter((id) => interesting.test(id))
      .sort()
      .slice(0, 3000)) {
      datalist.appendChild(this._el("option", { value: entityId }));
    }

    const fieldInput = (field, values) => {
      const current = values[field.key] ?? field.default ?? "";
      let input;
      if (field.type === "select") {
        input = this._el("select");
        input.appendChild(this._el("option", { value: "", text: "—" }));
        for (const option of field.options) {
          const el = this._el("option", { value: option, text: option });
          if (String(current) === option) el.selected = true;
          input.appendChild(el);
        }
        input.addEventListener("change", () => {
          values[field.key] = input.value || undefined;
          schedulePreview();
        });
      } else if (field.type === "bool") {
        input = this._el("input", { type: "checkbox" });
        input.checked = Boolean(current);
        input.addEventListener("change", () => {
          values[field.key] = input.checked;
          schedulePreview();
        });
      } else if (field.type === "number") {
        input = this._el("input", { type: "number", value: current === "" ? "" : String(current) });
        if (field.min !== undefined) input.min = field.min;
        if (field.max !== undefined) input.max = field.max;
        input.addEventListener("input", () => {
          values[field.key] = input.value === "" ? undefined : Number(input.value);
          schedulePreview();
        });
      } else if (field.type === "textarea" || field.type === "entity_list") {
        input = this._el("textarea");
        input.value = Array.isArray(current) ? current.map((e) => (typeof e === "string" ? e : e.entity)).join("\n") : current;
        if (field.type === "entity_list") input.placeholder = "one entity id per line";
        input.addEventListener("input", () => {
          if (field.type === "entity_list") {
            const lines = input.value.split("\n").map((line) => line.trim()).filter(Boolean);
            values[field.key] = lines.length ? lines : undefined;
          } else {
            values[field.key] = input.value || undefined;
          }
          schedulePreview();
        });
      } else {
        input = this._el("input", { type: "text", value: String(current) });
        if (field.type === "entity") input.setAttribute("list", entityListId);
        input.addEventListener("input", () => {
          values[field.key] = input.value || undefined;
          schedulePreview();
        });
      }
      const row = this._el("div", { class: "fieldrow" }, [
        this._el("label", { text: field.label + (field.required ? " *" : "") }),
        input,
      ]);
      if (field.help) row.appendChild(this._el("div", { class: "help", text: field.help }));
      return row;
    };

    // ---- slot editors (dashboard kind).
    const slotsContainer = this._el("div");
    const renderSlots = () => {
      slotsContainer.innerHTML = "";
      for (const slot of layouts[def.layout]) {
        const assigned = slots[slot] || (slots[slot] = { type: "", values: {} });
        const box = this._el("div", { class: "slotbox" });
        box.appendChild(this._el("div", { class: "slotname", text: slot.replace(/_/g, " ") }));
        const typeSelect = this._el("select");
        typeSelect.appendChild(this._el("option", { value: "", text: "— empty —" }));
        for (const [type, meta] of Object.entries(descriptors.widgets)) {
          const option = this._el("option", { value: type, text: meta.label });
          if (assigned.type === type) option.selected = true;
          typeSelect.appendChild(option);
        }
        const fieldsBox = this._el("div");
        const renderFields = () => {
          fieldsBox.innerHTML = "";
          if (!assigned.type) return;
          for (const field of descriptors.widgets[assigned.type].fields) {
            fieldsBox.appendChild(fieldInput(field, assigned.values));
          }
        };
        typeSelect.addEventListener("change", () => {
          assigned.type = typeSelect.value;
          assigned.values = {};
          renderFields();
          schedulePreview();
        });
        renderFields();
        box.append(this._el("div", { class: "fieldrow" }, [this._el("label", { text: "Widget" }), typeSelect]), fieldsBox);
        slotsContainer.appendChild(box);
      }
    };

    // ---- top-level fields.
    const nameInput = this._el("input", { type: "text", value: def.name });
    nameInput.addEventListener("input", () => {
      def.name = nameInput.value;
      schedulePreview();
    });

    const kindSelect = this._el("select");
    for (const [value, label] of [["dashboard", "Dashboard (widgets)"], ["picture", "Picture (URL / camera)"]]) {
      const option = this._el("option", { value, text: label });
      if (def.kind === value) option.selected = true;
      kindSelect.appendChild(option);
    }

    const layoutSelect = this._el("select");
    for (const layout of Object.keys(layouts)) {
      const option = this._el("option", {
        value: layout,
        text: `${layout.replace(/_/g, " ")} (${layouts[layout].length} slot${layouts[layout].length > 1 ? "s" : ""})`,
      });
      if (def.layout === layout) option.selected = true;
      layoutSelect.appendChild(option);
    }
    layoutSelect.addEventListener("change", () => {
      def.layout = layoutSelect.value;
      renderSlots();
      schedulePreview();
    });

    const dashboardSection = this._el("div");
    const pictureSection = this._el("div");
    for (const field of descriptors.picture_fields) {
      pictureSection.appendChild(fieldInput(field, picture));
    }
    const screenFieldsBox = this._el("div");
    for (const field of descriptors.screen_fields) {
      screenFieldsBox.appendChild(fieldInput(field, def));
    }
    const syncKind = () => {
      dashboardSection.style.display = def.kind === "dashboard" ? "" : "none";
      pictureSection.style.display = def.kind === "picture" ? "" : "none";
    };
    kindSelect.addEventListener("change", () => {
      def.kind = kindSelect.value;
      syncKind();
      schedulePreview();
    });

    dashboardSection.append(
      this._el("div", { class: "fieldrow" }, [this._el("label", { text: "Layout" }), layoutSelect]),
      slotsContainer
    );
    renderSlots();
    syncKind();

    const form = this._el("div", { class: "editor-form" }, [
      datalist,
      this._el("div", { class: "fieldrow" }, [this._el("label", { text: "Name" }), nameInput]),
      this._el("div", { class: "fieldrow" }, [this._el("label", { text: "Kind" }), kindSelect]),
      dashboardSection,
      pictureSection,
      screenFieldsBox,
    ]);
    const preview = this._el("div", { class: "editor-preview" }, [
      previewImg,
      status,
      this._el("button", { class: "btn", text: "Refresh preview", onclick: renderPreview }),
    ]);

    let screenId = stored ? stored.screen_id : null;
    const save = async (andSend) => {
      try {
        const body = { entry_id: this._screensEntry, screen: collect() };
        if (screenId) body.screen_id = screenId;
        const result = await this._api("screens/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        screenId = result.screen_id;
        if (andSend) {
          this._toast("Saved — sending to the frame (~30 s refresh)");
          await this._api("screens/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ entry_id: this._screensEntry, screen_id: screenId }),
          });
        }
        this._closeDialog();
        this._screensLoadedFor = null;
        this._renderTab();
        this._toast(andSend ? "Saved and sent ✓" : "Screen saved");
      } catch (err) {
        this._toast(err.message, true);
      }
    };

    this._openDialog(
      stored ? `Edit screen — ${stored.title}` : "New screen",
      [this._el("div", { class: "editor-grid" }, [form, preview])],
      [
        this._el("button", { class: "btn", text: "Cancel", onclick: () => this._closeDialog() }),
        this._el("button", { class: "btn", text: "Save & send", onclick: () => save(true) }),
        this._el("button", { class: "btn raised", text: "Save", onclick: () => save(false) }),
      ],
      true,
      cleanupPreview
    );
    renderPreview();
  }

  /* -------------------------------------------------------------- dialog */

  /* Dialogs stack: opening one over another (e.g. the crop window on top of
   * the scene editor) detaches the current overlay — DOM state and all — and
   * restores it when the top dialog closes. */
  _openDialog(title, contentNodes, actionNodes, wide = false, onClose = null, stack = false) {
    const modal = this.shadowRoot.getElementById("modal");
    if (stack && modal.firstChild) {
      this._dialogStack.push({
        overlay: modal.firstChild,
        cleanup: this._dialogCleanup,
      });
      modal.firstChild.remove();
    } else {
      const cleanup = this._dialogCleanup;
      if (cleanup) cleanup();
      this._dialogStack = [];
      modal.innerHTML = "";
    }
    this._dialogCleanup = onClose;
    const dialog = this._el("div", { class: wide ? "dialog wide" : "dialog" }, [
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
    const cleanup = this._dialogCleanup;
    this._dialogCleanup = null;
    if (cleanup) cleanup();
    const modal = this.shadowRoot.getElementById("modal");
    modal.innerHTML = "";
    const previous = this._dialogStack.pop();
    if (previous) {
      this._dialogCleanup = previous.cleanup;
      modal.appendChild(previous.overlay);
    }
  }
}

customElements.define("fraimic-panel", FraimicPanel);
