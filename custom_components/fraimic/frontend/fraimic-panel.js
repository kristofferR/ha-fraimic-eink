/* Fraimic panel. Native web component, no build step or external runtime. */

const API = "/api/fraimic";
const SEARCH_DELAY = 350;
const SOURCE_LIMIT = 40;
const ALL_SOURCES_LIMIT = 8;
const INITIAL_RENDER_LIMIT = 60;
const RENDER_PAGE_SIZE = 60;
const SIGNED_PATH_LIMIT = 512;
const QUEUE_SNAPS = [220, 320, 420];
const PALETTE = ["black", "white", "yellow", "red", "blue", "green", "neutral"];
const PLATE_THEME = {
  black: ["var(--primary-text-color)", "var(--primary-background-color)"],
  white: ["var(--primary-background-color)", "var(--primary-text-color)"],
  yellow: ["var(--warning-color)", "var(--primary-text-color)"],
  red: ["var(--error-color)", "var(--text-primary-color)"],
  blue: ["var(--primary-color)", "var(--text-primary-color)"],
  green: ["var(--success-color)", "var(--primary-text-color)"],
};
const ANCHORS = [
  "top_left", "top", "top_right", "left", "center", "right",
  "bottom_left", "bottom", "bottom_right",
];
const OVERLAY_TYPES = [
  "clock", "date", "todo", "agenda", "weather", "stat",
  "entities", "chart", "gauge", "text", "caption",
];

const h = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const storedArray = (key, fallback = []) => {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : fallback;
  } catch (_error) { return fallback; }
};

const storeValue = (key, value) => {
  try { localStorage.setItem(key, value); } catch (_error) { /* storage is optional */ }
};

const css = String.raw`
  :host {
    --frame-aspect: 4 / 3;
    --top-h: 56px;
    --filter-h: 48px;
    --player-h: 64px;
    --panel-left: 0px;
    --panel-right: 0px;
    --chrome: var(--app-header-background-color, var(--card-background-color));
    --surface: var(--card-background-color, var(--secondary-background-color));
    --text: var(--primary-text-color);
    --muted: var(--secondary-text-color);
    --line: var(--divider-color);
    --accent: var(--primary-color);
    --accent-text: var(--text-primary-color, var(--primary-background-color));
    display: block;
    min-height: 100%;
    color: var(--text);
    background: var(--primary-background-color);
    font-family: var(--paper-font-body1_-_font-family, system-ui, sans-serif);
  }
  * { box-sizing: border-box; }
  button, input, select, textarea { font: inherit; color: inherit; }
  button, [role="button"], input, select, textarea { min-height: 44px; }
  button:focus-visible, input:focus-visible, select:focus-visible,
  textarea:focus-visible, [tabindex]:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  button { border: 0; background: none; cursor: pointer; }
  .shell { min-height: 100vh; padding-bottom: var(--player-h); }
  .top {
    position: sticky; top: 0; z-index: 30; height: var(--top-h);
    display: flex; align-items: center; gap: 8px; padding: 0 16px;
    background: var(--chrome); border-bottom: 1px solid var(--line);
  }
  .brand, .crumb { font-size: 17px; font-weight: 650; letter-spacing: -.02em; white-space: nowrap; }
  .crumb { color: var(--muted); }
  .spacer { flex: 1 1 auto; }
  .frames { display: flex; align-items: center; gap: 6px; overflow-x: auto; scrollbar-width: none; }
  .frames::-webkit-scrollbar { display: none; }
  .chip, .btn, .icon-btn, .seg button {
    border: 1px solid var(--line); border-radius: 4px; background: var(--surface);
  }
  .chip { border-radius: 16px; }
  .chip, .btn { height: 32px; min-height: 32px; padding: 0 10px; display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; }
  .chip.selected, .btn.primary, .seg button.selected {
    background: var(--accent); color: var(--accent-text); border-color: var(--accent);
  }
  .btn.quiet { border-color: transparent; background: transparent; }
  .btn.small { height: 28px; min-height: 28px; font-size: 12px; }
  .icon-btn { width: 44px; height: 44px; display: inline-grid; place-items: center; border-color: transparent; background: transparent; }
  ha-icon { --mdc-icon-size: 20px; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--disabled-text-color); flex: none; }
  .dot.online { background: var(--success-color); }
  .dot.charging { background: var(--warning-color); }
  .filter {
    position: sticky; top: var(--top-h); z-index: 25; min-height: var(--filter-h);
    display: flex; align-items: center; gap: 7px; padding: 7px 16px;
    background: var(--chrome); border-bottom: 1px solid var(--line); flex-wrap: nowrap;
    overflow-x: auto; scrollbar-width: none;
  }
  .filter::-webkit-scrollbar { display: none; }
  .search { position: relative; width: min(340px, 32vw); min-width: 220px; }
  .search ha-icon { position: absolute; left: 10px; top: 12px; color: var(--muted); pointer-events: none; }
  .search input, .field input, .field select, .field textarea {
    width: 100%; border: 1px solid var(--line); border-radius: 6px;
    background: var(--surface); padding: 0 10px;
  }
  .search input { height: 34px; min-height: 34px; padding-left: 36px; }
  .counter { color: var(--muted); font-size: 12px; white-space: nowrap; }
  main { min-height: calc(100vh - var(--top-h) - var(--player-h)); }
  .browse-layout { display: grid; grid-template-columns: 232px minmax(0, 1fr); min-height: calc(100vh - var(--top-h) - var(--filter-h) - var(--player-h)); }
  .browse-results { min-width: 0; }
  .source-rail {
    position: sticky; top: calc(var(--top-h) + var(--filter-h)); align-self: start;
    height: calc(100vh - var(--top-h) - var(--filter-h) - var(--player-h));
    overflow-y: auto; padding: 9px 7px 18px; border-right: 1px solid var(--line);
    background: var(--chrome);
  }
  .source-group-label {
    padding: 11px 9px 5px; color: var(--muted); font-size: 10px;
    font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
  }
  .source-tree { position: relative; }
  .source-tree.drag-over::before { content: ""; position: absolute; z-index: 2; left: 6px; right: 6px; top: 0; height: 2px; background: var(--accent); }
  .source-tree-row { display: flex; align-items: center; min-width: 0; }
  .source-grip { width: 22px; min-height: 36px; display: grid; place-items: center; color: var(--muted); cursor: grab; opacity: .45; }
  .source-tree:hover > .source-tree-row > .source-grip, .source-grip:focus-visible { opacity: 1; }
  .source-expand { width: 26px; min-height: 36px; display: grid; place-items: center; color: var(--muted); }
  .source-expand ha-icon { transition: transform 140ms ease; }
  .source-expand[aria-expanded="true"] ha-icon { transform: rotate(90deg); }
  .source-expand-placeholder { width: 26px; flex: none; }
  .source-option {
    min-width: 0; min-height: 38px; flex: 1; display: flex; align-items: center; gap: 7px;
    padding: 5px 7px; border-left: 2px solid transparent; color: var(--muted);
    text-align: left;
  }
  .source-option:hover { color: var(--text); background: var(--secondary-background-color); }
  .source-option.selected { border-left-color: var(--accent); color: var(--text); background: var(--secondary-background-color); }
  .source-option:disabled { color: var(--disabled-text-color); cursor: default; }
  .source-option span:first-of-type { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .source-option .source-meta { margin-left: auto; color: var(--muted); font-size: 10px; }
  .source-option ha-icon { --mdc-icon-size: 16px; flex: none; }
  .source-children { display: none; padding-left: 32px; }
  .source-children.open { display: block; }
  .source-child-row { display: grid; grid-template-columns: 22px minmax(0, 1fr); align-items: center; min-width: 0; }
  .source-child-row .source-expand { width: 22px; }
  .source-child-row .source-expand-placeholder { width: 22px; }
  .source-child-row .source-option { min-height: 34px; padding-top: 3px; padding-bottom: 3px; font-size: 12px; }
  .source-child-row > .source-children { grid-column: 2; width: 100%; padding-left: 12px; }
  .source-divider { height: 1px; margin: 10px 7px 3px; background: var(--line); }
  .content { padding: 18px 16px 28px; }
  .failure {
    display: flex; align-items: center; gap: 8px; padding: 10px 16px;
    border-bottom: 1px solid var(--line); color: var(--muted); font-size: 13px;
  }
  .row-head { display: flex; align-items: baseline; gap: 10px; margin: 18px 0 9px; }
  .row-head h2 { margin: 0; font-size: 15px; font-weight: 650; }
  .row-head .sub { color: var(--muted); font-size: 12px; }
  .strip { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(150px, 190px); gap: 12px; overflow-x: auto; padding: 2px 2px 8px; }
  .masonry { columns: 180px; column-gap: 14px; }
  .tile {
    display: inline-block; width: 100%; margin: 0 0 17px;
    break-inside: avoid; border-radius: 8px; contain: paint;
  }
  .tile:focus-visible {
    outline: 0;
    box-shadow: inset 0 0 0 2px var(--accent);
  }
  .strip .tile { display: block; margin: 0; }
  .art {
    position: relative; width: 100%; aspect-ratio: var(--art-aspect, 4 / 3);
    overflow: hidden; border-radius: 8px; background: #0d0d0d;
  }
  .art img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .glass { aspect-ratio: var(--frame-aspect); border-radius: 4px; background: #0d0d0d; overflow: hidden; }
  .glass img { width: 100%; height: 100%; object-fit: cover; }
  img.image-failed { visibility: hidden; }
  .cap { padding-top: 7px; min-width: 0; line-height: 1.35; }
  .cap b, .cap span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cap b { font-size: 13px; font-weight: 600; }
  .cap span { color: var(--muted); font-size: 12px; }
  .actions {
    position: absolute; left: 0; right: 0; bottom: 0; padding: 24px 8px 8px;
    display: flex; gap: 6px; align-items: center; opacity: 0;
    background: linear-gradient(transparent, color-mix(in srgb, #0d0d0d 88%, transparent));
  }
  .tile:hover .actions, .tile:focus-within .actions { opacity: 1; }
  .actions .btn { height: 26px; min-height: 26px; padding: 0 7px; font-size: 11px; }
  .actions .icon-btn { width: 28px; height: 28px; min-height: 28px; color: var(--primary-text-color); }
  .badge { position: absolute; top: 7px; padding: 3px 6px; border-radius: 4px; background: var(--surface); color: var(--text); font-size: 10px; }
  .badge.right { right: 7px; }
  .loading-grid { columns: 180px; column-gap: 14px; }
  .placeholder { display: inline-block; width: 100%; margin-bottom: 14px; break-inside: avoid; }
  .block { aspect-ratio: var(--skeleton-aspect); background: var(--divider-color); border-radius: 8px; }
  .block-line { height: 11px; width: 68%; margin-top: 8px; border-radius: 3px; background: var(--divider-color); }
  .empty { max-width: 620px; margin: 0 auto; padding: 72px 24px; text-align: center; }
  .empty h2 { margin: 0 0 8px; font-size: 22px; }
  .empty p { color: var(--muted); line-height: 1.5; }
  .empty-actions { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin-top: 18px; }
  .adding-bar { position: sticky; top: calc(var(--top-h) + var(--filter-h)); z-index: 20; display: flex; align-items: center; gap: 8px; min-height: 42px; padding: 6px 16px; background: var(--surface); border-bottom: 1px solid var(--line); }
  .load-more { display: flex; justify-content: center; padding: 12px 0 4px; }
  .shell.queue-open main { opacity: .35; pointer-events: none; }
  .player {
    position: fixed; z-index: 50; left: var(--panel-left); right: var(--panel-right); bottom: 0; height: var(--player-h);
    display: flex; align-items: center; gap: 10px; padding: 0 16px;
    background: var(--chrome); border-top: 1px solid var(--line);
  }
  .player.asleep .player-art, .player.unreachable .player-art { opacity: .45; }
  .player.unreachable { border-top-color: var(--error-color); }
  .player-art { width: 52px; flex: none; }
  .player-copy { min-width: 0; max-width: 340px; }
  .player-copy b, .player-copy span { display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .player-copy b { font-size: 13px; } .player-copy span { font-size: 12px; color: var(--muted); }
  .transport { display: flex; align-items: center; }
  .progress { width: min(220px, 18vw); height: 2px; background: var(--line); }
  .progress i { display: block; height: 100%; background: var(--accent); }
  .menu {
    position: fixed; z-index: 90; width: min(300px, calc(100vw - 24px)); padding: 6px;
    background: var(--surface); border: 1px solid var(--line); border-radius: 8px;
    box-shadow: var(--ha-card-box-shadow, none);
  }
  .menu.top-menu { top: 52px; right: 12px; }
  .menu.player-menu { right: 12px; bottom: 60px; }
  .menu h3 { margin: 8px 10px; font-size: 13px; }
  .menu button { width: 100%; display: flex; align-items: center; gap: 9px; padding: 0 10px; text-align: left; border-radius: 5px; }
  .menu button:hover { background: var(--secondary-background-color); }
  .menu button span:last-child { margin-left: auto; color: var(--muted); font-size: 12px; }
  .queue-sheet {
    position: fixed; z-index: 45; left: var(--panel-left); right: var(--panel-right); bottom: var(--player-h);
    height: var(--queue-height, 420px); max-height: min(420px, calc(100vh - var(--top-h) - var(--player-h)));
    background: var(--surface); border-top: 1px solid var(--line); overflow: auto;
    transition: height 180ms ease-out;
  }
  .queue-sheet.dragging { transition: none; user-select: none; }
  .queue-handle { position: sticky; top: 0; z-index: 2; height: 28px; display: grid; place-items: center; background: var(--surface); cursor: ns-resize; }
  .queue-handle::after { content: ""; width: 42px; height: 4px; border-radius: 4px; background: var(--disabled-text-color); }
  .queue-head { display: flex; align-items: center; gap: 8px; padding: 8px 16px; }
  .queue-head h2 { margin: 0; font-size: 14px; }
  .queue-interval { height: 38px; min-height: 38px; align-items: flex-start; flex-direction: column; justify-content: center; gap: 0; line-height: 1.1; }
  .queue-interval small { color: var(--muted); font-size: 9px; font-weight: 500; }
  .queue-interval b { font-size: 12px; }
  .queue-interval-menu { width: 230px; margin: 0 60px 8px auto; padding: 6px; border: 1px solid var(--line); border-radius: 8px; background: var(--chrome); }
  .queue-interval-menu h3 { margin: 7px 10px; font-size: 13px; }
  .queue-interval-menu button { width: 100%; min-height: 40px; display: flex; align-items: center; padding: 0 10px; text-align: left; }
  .queue-interval-menu button:hover { background: var(--secondary-background-color); }
  .queue-interval-menu button span { margin-left: auto; color: var(--muted); font-size: 11px; }
  .queue-list { margin: 0; padding: 0; list-style: none; }
  .queue-row { min-height: 68px; display: flex; align-items: center; gap: 10px; padding: 7px 16px; border-bottom: 1px solid var(--line); }
  .queue-row.drag-over { border-top: 2px solid var(--accent); }
  .grip { color: var(--muted); cursor: grab; }
  .row-art { width: 52px; flex: none; }
  .row-copy { min-width: 0; flex: 1; }
  .row-copy b, .row-copy span { display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .row-copy b { font-size: 13px; } .row-copy span { color: var(--muted); font-size: 12px; }
  .row-actions { display: flex; }
  .playlist-head { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 18px; }
  .playlist-head h1 { margin: 0; font-size: 24px; }
  .playlist-head p { margin: 5px 0 0; color: var(--muted); }
  .playlist-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
  .playlist-card { border-top: 1px solid var(--line); padding: 14px 0; text-align: left; }
  .mosaic { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3px; aspect-ratio: var(--frame-aspect); margin-bottom: 10px; }
  .mosaic .glass { width: 100%; height: 100%; border-radius: 2px; }
  .playlist-card h2 { margin: 0; font-size: 16px; }
  .playlist-card p { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
  .slide-row { display: flex; align-items: center; gap: 12px; min-height: 80px; border-bottom: 1px solid var(--line); }
  .slide-row .number { width: 26px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .slide-row .row-art { width: 64px; }
  .modal-backdrop { position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; padding: 24px; background: color-mix(in srgb, var(--primary-background-color) 72%, transparent); }
  .dialog { width: min(880px, 92vw); max-height: 90vh; overflow: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 9px; }
  .dialog-title { min-height: 56px; display: flex; align-items: center; gap: 10px; padding: 9px 16px; border-bottom: 1px solid var(--line); }
  .dialog-heading { min-width: 0; }
  .dialog-title h2 { margin: 0; font-size: 16px; }
  .dialog-subtitle { display: flex; align-items: center; gap: 5px; margin-top: 4px; color: var(--muted); font-size: 12px; }
  .dialog-header-actions { display: flex; align-items: center; gap: 2px; }
  .dialog-body { padding: 16px; }
  .dialog-actions { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--line); flex-wrap: wrap; }
  .dialog.detail-dialog { width: min(1120px, 94vw); }
  .detail-dialog .dialog-body { padding: 0; }
  .detail-grid { display: grid; grid-template-columns: minmax(0, 1.85fr) minmax(280px, .62fr); }
  .detail-workspace { min-width: 0; padding: 20px; border-right: 1px solid var(--line); }
  .detail-inspector { min-width: 0; padding: 20px; background: var(--secondary-background-color); }
  .detail-section-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .detail-section-head h3 { margin: 0; font-size: 13px; }
  .crop-stage { position: relative; width: 100%; aspect-ratio: var(--art-aspect, 4 / 3); border-radius: 8px; overflow: hidden; background: #0d0d0d; }
  .crop-stage > img { width: 100%; height: 100%; object-fit: fill; display: block; }
  .crop-window { position: absolute; border: 2px solid var(--primary-text-color); box-shadow: 0 3px 16px color-mix(in srgb, #0d0d0d 35%, transparent); cursor: move; touch-action: none; }
  .crop-window::after { content: attr(data-label); position: absolute; left: 0; bottom: 0; padding: 3px 5px; color: #fff; background: color-mix(in srgb, #0d0d0d 78%, transparent); font-size: 10px; white-space: nowrap; pointer-events: none; }
  .crop-resize { position: absolute; right: -8px; bottom: -8px; width: 18px; height: 18px; border: 2px solid var(--primary-text-color); background: var(--accent); cursor: nwse-resize; touch-action: none; }
  .crop-tools { display: flex; gap: 8px; flex-wrap: wrap; margin: 26px 0 8px; }
  .crop-hint { display: flex; align-items: center; gap: 5px; margin: 8px 0 0; color: var(--muted); font-size: 12px; }
  .detail-setting { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 15px 0; border-bottom: 1px solid var(--line); }
  .detail-setting-copy { min-width: 0; }
  .detail-setting h3, .artwork-details h3 { margin: 0; font-size: 13px; }
  .detail-setting p { margin: 3px 0 0; color: var(--muted); font-size: 11px; }
  .detail-select { width: 116px; min-height: 36px; height: 36px; padding: 0 8px; border: 1px solid var(--line); border-radius: 5px; background: var(--surface); flex: none; }
  .artwork-details { padding-top: 18px; }
  .detail-meta-list { margin: 10px 0 0; }
  .detail-meta-row { display: grid; grid-template-columns: 68px minmax(0, 1fr); gap: 10px; padding: 4px 0; font-size: 12px; line-height: 1.4; }
  .detail-meta-row dt { color: var(--muted); }
  .detail-meta-row dd { margin: 0; min-width: 0; }
  .detail-text-link { min-height: auto; padding: 0; color: var(--accent); text-align: left; }
  .detail-text-link:hover { text-decoration: underline; text-underline-offset: 2px; }
  .dialog-subtitle .detail-text-link { color: inherit; }
  .detail-description { margin: 12px 0 0; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .detail-links { display: flex; align-items: flex-start; gap: 5px; flex-direction: column; margin-top: 12px; }
  .detail-links .btn { justify-content: flex-start; padding-left: 0; }
  .favorite-btn[aria-pressed="true"] { color: var(--warning-color); }
  .favorite-btn[aria-pressed="true"] ha-icon { --mdc-icon-size: 22px; }
  .detail-ready { color: var(--muted); font-size: 12px; }
  .field { margin-bottom: 14px; }
  .field label { display: block; margin-bottom: 5px; color: var(--muted); font-size: 12px; }
  .field textarea { min-height: 82px; padding-top: 8px; }
  .seg { display: flex; gap: 4px; }
  .seg button { min-height: 34px; height: 34px; padding: 0 10px; }
  .toast { position: fixed; z-index: 120; left: 16px; bottom: calc(var(--player-h) + 16px); max-width: min(520px, calc(100vw - 32px)); display: flex; gap: 10px; align-items: center; padding: 11px 13px; background: var(--surface); border: 1px solid var(--line); border-radius: 7px; box-shadow: var(--ha-card-box-shadow, none); }
  .toast.error { border-color: var(--error-color); }
  .toast button { min-height: 28px; color: var(--accent); }
  .overlay-editor { position: fixed; z-index: 80; inset: 0 0 var(--player-h); background: var(--primary-background-color); overflow: auto; }
  .editor-top { height: var(--top-h); position: sticky; top: 0; z-index: 5; display: flex; align-items: center; gap: 8px; padding: 0 16px; background: var(--chrome); border-bottom: 1px solid var(--line); }
  .editor-grid { min-height: calc(100% - var(--top-h)); display: grid; grid-template-columns: minmax(0, 1fr) 360px; }
  .canvas-pane { padding: 24px; min-width: 0; }
  .canvas-row { display: flex; align-items: flex-start; gap: 18px; }
  .canvas { position: relative; width: min(460px, 100%); aspect-ratio: var(--frame-aspect); background: #0d0d0d; overflow: hidden; flex: none; }
  .canvas.dragging { background-image: linear-gradient(to right, var(--line) 1px, transparent 1px), linear-gradient(to bottom, var(--line) 1px, transparent 1px); background-size: calc(100% / 12) calc(100% / 8); }
  .canvas > img { width: 100%; height: 100%; object-fit: cover; }
  .overlay-box { position: absolute; display: grid; place-items: center; overflow: hidden; border: 1px solid var(--accent); cursor: move; color: var(--plate-text, var(--text)); }
  .overlay-box.panel { background: var(--plate-color, var(--surface)); }
  .overlay-box.outline { box-shadow: inset 0 0 0 2px var(--plate-color, var(--surface)); }
  .overlay-box.selected { outline: 2px solid var(--accent); outline-offset: 2px; }
  .overlay-box .resize { position: absolute; right: 0; bottom: 0; width: 16px; height: 16px; background: var(--accent); cursor: nwse-resize; }
  .editor-hint { max-width: 250px; color: var(--muted); font-size: 13px; line-height: 1.5; }
  .preview-strip { display: flex; gap: 8px; margin-top: 16px; overflow-x: auto; }
  .preview-thumb { width: 84px; flex: none; padding: 0; border: 2px solid transparent; }
  .preview-thumb.selected { border-color: var(--accent); }
  .inspector { border-left: 1px solid var(--line); background: var(--surface); overflow: auto; }
  .inspector-section { padding: 14px; border-bottom: 1px solid var(--line); }
  .inspector-section h3 { margin: 0 0 9px; font-size: 13px; }
  .layer { display: flex; align-items: center; min-height: 52px; gap: 8px; padding: 5px 8px; border-left: 2px solid transparent; }
  .layer.selected { border-left-color: var(--accent); background: var(--secondary-background-color); }
  .layer-copy { flex: 1; min-width: 0; }
  .layer-copy b, .layer-copy span { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .layer-copy span { color: var(--muted); font-size: 11px; }
  .anchor-grid { width: 110px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; aspect-ratio: var(--frame-aspect); }
  .anchor-grid button { min-height: 28px; border: 1px solid var(--line); background: var(--primary-background-color); }
  .anchor-grid button.selected { background: var(--accent); }
  .preset-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .type-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 12px; }
  .type-grid button { min-width: 0; padding: 5px; border: 1px solid var(--line); border-radius: 4px; }
  .weekday-row, .check-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .weekday-row button { min-width: 36px; min-height: 36px; border: 1px solid var(--line); border-radius: 4px; }
  .weekday-row button.selected { background: var(--accent); color: var(--accent-text); }
  .check-row input { min-height: auto; }
  .preset { min-height: 72px; padding: 8px; text-align: left; border: 1px solid var(--line); border-radius: 6px; }
  .danger { color: var(--error-color); }
  .upload-row { display: flex; gap: 10px; align-items: center; min-height: 62px; border-bottom: 1px solid var(--line); }
  .drop-active { outline: 2px dashed var(--accent); outline-offset: -8px; }
  @media (hover: none) { .actions { opacity: 1; } }
  @media (max-width: 900px) {
    .progress, .overlay-tag { display: none; }
    .browse-layout { grid-template-columns: 190px minmax(0, 1fr); }
    .editor-grid { grid-template-columns: 1fr; }
    .detail-grid { grid-template-columns: minmax(0, 1.45fr) minmax(260px, .7fr); }
    .inspector { border-left: 0; border-top: 1px solid var(--line); }
  }
  @media (max-width: 599px) {
    .top, .filter, .content, .player, .queue-row, .queue-head { padding-left: 12px; padding-right: 12px; }
    .top .nav-label, .player .previous, .player .next, .player .frame-more { display: none; }
    .frames { min-width: 0; }
    .filter { flex-wrap: nowrap; overflow-x: auto; }
    .browse-layout { display: block; }
    .source-rail {
      position: sticky; top: calc(var(--top-h) + var(--filter-h)); z-index: 19;
      height: auto; display: flex; gap: 3px; overflow-x: auto; padding: 6px 12px;
      border-right: 0; border-bottom: 1px solid var(--line); scrollbar-width: none;
    }
    .source-rail::-webkit-scrollbar { display: none; }
    .source-group, .source-tree, .source-tree-row { display: contents; }
    .source-group-label { display: none; }
    .source-grip, .source-expand, .source-expand-placeholder, .source-children, .source-divider { display: none; }
    .source-option { width: auto; min-width: max-content; border-left: 0; border-bottom: 2px solid transparent; }
    .source-option.selected { border-bottom-color: var(--accent); }
    .search { min-width: 44px; width: 44px; }
    .search input { width: 44px; color: transparent; padding: 0; }
    .search:focus-within { position: absolute; left: 8px; right: 8px; width: auto; z-index: 2; }
    .search:focus-within input { width: 100%; color: var(--text); padding-left: 36px; }
    .masonry, .loading-grid { columns: 140px; }
    .strip { grid-auto-columns: 145px; }
    .player-art { width: 44px; }
    .player-copy { max-width: 42vw; }
    .queue-sheet { height: calc(100vh - var(--player-h)) !important; max-height: calc(100vh - var(--player-h)); }
    .detail-grid { grid-template-columns: 1fr; }
    .detail-workspace { border-right: 0; border-bottom: 1px solid var(--line); }
    .modal-backdrop { padding: 0; align-items: end; }
    .dialog { width: 100%; max-height: calc(100vh - 12px); border-radius: 9px 9px 0 0; }
    .playlist-head { flex-direction: column; }
    .editor-top { padding: 0 10px; }
    .canvas-pane { padding: 12px; }
    .canvas-row { display: block; }
    .editor-hint { max-width: none; margin-top: 12px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .queue-sheet { transition: none; }
  }
`;

class FraimicPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._frames = [];
    this._selectedFrameId = localStorage.getItem("fraimic-frame") || null;
    this._sources = [];
    this._sourceOrder = storedArray("fraimic-source-order");
    this._expandedSources = new Set(storedArray("fraimic-expanded-sources", ["saved", "reframed", "@playlists"]));
    this._sourceChildren = new Map();
    this._sourceNodeMeta = new Map();
    this._sourceTreeLoading = new Set();
    this._galleryBySource = new Map();
    this._galleryCursorBySource = new Map();
    this._galleryTotalBySource = new Map();
    this._sourceStatus = new Map();
    this._facets = { artists: [], colours: [], collections: [], eras: [] };
    this._query = "";
    this._selectedSource = "all";
    this._selectedBrowseId = "";
    this._galleryTitle = "";
    this._colours = new Set();
    this._artist = "";
    this._era = "";
    this._fits = false;
    this._rendersWell = false;
    this._galleryLoading = false;
    this._galleryGeneration = 0;
    this._galleryRequestKey = null;
    this._galleryLoadedAt = 0;
    this._sourcesGeneration = 0;
    this._playerGeneration = 0;
    this._detailGeneration = 0;
    this._renderLimit = INITIAL_RENDER_LIMIT;
    this._route = "browse";
    this._playlistId = null;
    this._playlists = [];
    this._playlist = null;
    this._player = null;
    this._queueOpen = false;
    this._queueHeight = 420;
    this._queueDragging = false;
    this._menu = null;
    this._modal = null;
    this._toast = null;
    this._toastTimer = null;
    this._detail = null;
    this._detailOptions = null;
    this._favoriteBusy = false;
    this._cropDrafts = new Map();
    this._uploads = [];
    this._addingToPlaylist = null;
    this._overlaysOpen = false;
    this._overlayData = null;
    this._overlayDraft = [];
    this._overlaySaved = "[]";
    this._selectedOverlayId = null;
    this._selectedPreview = null;
    this._dropActive = false;
    this._initialized = false;
    this._refreshTimer = null;
    this._searchTimer = null;
    this._loadingMore = false;
    this._draggedArt = null;
    this._signedPaths = new Map();
    this._signedPathPromises = new Map();
    this._imageObserver = null;
    this._boundsObserver = null;
    this._playerSignature = null;
    this._onPop = () => { this._syncRoute(); this._loadRoute(); };
    this._onShadowKeyDown = (event) => this._handleKeyDown(event);
    this._onWindowResize = () => this._syncPanelBounds();
  }

  connectedCallback() {
    window.addEventListener("popstate", this._onPop);
    window.addEventListener("resize", this._onWindowResize);
    this.shadowRoot.addEventListener("keydown", this._onShadowKeyDown);
    this._syncPanelBounds();
    if ("ResizeObserver" in window) {
      this._boundsObserver ||= new ResizeObserver(() => this._syncPanelBounds());
      this._boundsObserver.observe(this);
    }
    if (this._initialized) this._startRefresh();
  }

  disconnectedCallback() {
    window.removeEventListener("popstate", this._onPop);
    window.removeEventListener("resize", this._onWindowResize);
    this.shadowRoot.removeEventListener("keydown", this._onShadowKeyDown);
    clearInterval(this._refreshTimer);
    clearTimeout(this._searchTimer);
    clearTimeout(this._toastTimer);
    this._imageObserver?.disconnect();
    this._boundsObserver?.disconnect();
  }

  set hass(value) {
    this._hass = value;
    if (this._initialized) return;
    this._initialized = true;
    this._syncRoute();
    this._render();
    this._loadAll();
    this._startRefresh();
  }

  set narrow(value) { this._narrow = value; }

  get _frame() {
    return this._frames.find((frame) => frame.id === this._selectedFrameId) || this._frames[0] || null;
  }

  _syncPanelBounds() {
    const bounds = this.getBoundingClientRect();
    this.style.setProperty("--panel-left", `${Math.max(0, bounds.left)}px`);
    this.style.setProperty("--panel-right", `${Math.max(0, window.innerWidth - bounds.right)}px`);
  }

  get _basePath() {
    return window.location.pathname.startsWith("/fraimic_panel") ? "/fraimic_panel" : "/fraimic";
  }

  get _frameAspect() {
    const frame = this._frame;
    if (!frame?.width || !frame?.height) return "4 / 3";
    return [90, 270].includes(frame.rotation)
      ? `${frame.height} / ${frame.width}`
      : `${frame.width} / ${frame.height}`;
  }

  async _api(path, options = {}) {
    const response = await this._hass.fetchWithAuth(`${API}/${path}`, options);
    let body = null;
    try { body = await response.json(); } catch (_error) { /* empty response */ }
    if (!response.ok) throw new Error(body?.message || response.statusText || "Request did not complete");
    return body;
  }

  _json(body) {
    return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  }

  _syncRoute() {
    const suffix = window.location.pathname.slice(this._basePath.length).replace(/^\/+|\/+$/g, "");
    const parts = suffix.split("/").filter(Boolean);
    if (parts[0] === "playlists") {
      this._route = parts[1] ? "playlist" : "playlists";
      this._playlistId = parts[1] ? decodeURIComponent(parts[1]) : null;
    } else {
      this._route = "browse";
      this._playlistId = null;
    }
  }

  _navigate(path) {
    if (this._overlaysOpen && this._overlaysDirty() && !confirm("Discard unsaved overlay changes?")) return;
    if (this._overlaysOpen) this._closeOverlayEditor();
    history.pushState({}, "", `${this._basePath}${path}`);
    window.dispatchEvent(new Event("location-changed"));
    this._syncRoute();
    this._menu = null;
    this._loadRoute();
  }

  _haNavigate(path) {
    history.pushState({}, "", path);
    window.dispatchEvent(new Event("location-changed"));
  }

  async _loadAll() {
    try {
      const previousFrameId = this._selectedFrameId;
      const { frames } = await this._api("frames");
      this._frames = frames;
      if (!frames.some((frame) => frame.id === this._selectedFrameId)) {
        this._selectedFrameId = frames[0]?.id || null;
      }
      if (this._selectedFrameId !== previousFrameId) {
        this._queueOpen = false;
        this._player = null;
      }
      if (this._selectedFrameId) localStorage.setItem("fraimic-frame", this._selectedFrameId);
      await Promise.all([this._loadPlayer(false), this._loadPlaylists(), this._loadSources()]);
      await this._loadRoute();
    } catch (error) {
      this._notify(this._friendlyError(error), { error: true });
      this._render();
    }
  }

  async _loadRoute() {
    if (this._route === "browse") return this._loadGallery();
    if (this._route === "playlists") await this._loadPlaylists();
    if (this._route === "playlist" && this._playlistId) await this._loadPlaylist(this._playlistId);
    this._render();
  }

  async _loadSources() {
    if (!this._selectedFrameId) return;
    const entryId = this._selectedFrameId;
    const generation = ++this._sourcesGeneration;
    const data = await this._api(`gallery/sources?entry_id=${encodeURIComponent(entryId)}`);
    if (generation !== this._sourcesGeneration || entryId !== this._selectedFrameId) return;
    this._sources = data.sources || [];
    for (const source of this._sources) {
      if (!Array.isArray(source.children)) continue;
      const key = this._sourceNodeKey(source.key, "");
      this._sourceChildren.set(key, source.children);
      this._sourceNodeMeta.set(key, { hasItems: Boolean(source.count), hasChildren: source.children.length > 0, loaded: true, title: source.name });
    }
    const current = new Set(this._sources.map((source) => source.key));
    this._sourceOrder = [
      ...this._sourceOrder.filter((key) => current.has(key)),
      ...this._sources.map((source) => source.key).filter((key) => !this._sourceOrder.includes(key)),
    ];
    const preload = this._sources
      .filter((source) => source.hierarchical && this._expandedSources.has(source.key) && !this._sourceChildren.has(this._sourceNodeKey(source.key, "")))
      .map((source) => this._loadSourceNode(source.key, "", false));
    if (preload.length) void Promise.all(preload).then(() => {
      if (generation === this._sourcesGeneration && entryId === this._selectedFrameId) this._renderPreservingFocus();
    });
  }

  async _loadPlaylists() {
    if (!this._selectedFrameId) return;
    const data = await this._api(`playlists?entry_id=${encodeURIComponent(this._selectedFrameId)}`);
    this._playlists = data.playlists || [];
  }

  async _loadPlaylist(id) {
    try {
      const playlist = await this._api(`playlists/${encodeURIComponent(id)}`);
      if (this._route === "playlist" && this._playlistId === id) this._playlist = playlist;
    } catch (error) {
      if (this._route !== "playlist" || this._playlistId !== id) return;
      this._notify(this._friendlyError(error), { error: true });
      this._navigate("/playlists");
    }
  }

  async _loadPlayer(render = true) {
    if (!this._selectedFrameId) { this._player = null; if (render) this._render(); return; }
    const entryId = this._selectedFrameId;
    const generation = ++this._playerGeneration;
    try {
      const player = await this._api(`player?entry_id=${encodeURIComponent(entryId)}`);
      if (generation !== this._playerGeneration || entryId !== this._selectedFrameId) return;
      const signature = this._playerRenderSignature(player);
      const changed = signature !== this._playerSignature;
      this._player = player;
      this._playerSignature = signature;
      if (render && changed && !this._modal && !this._overlaysOpen && !this._queueDragging) {
        this._renderPreservingFocus();
      } else if (render && !changed) {
        this._updatePlayerTiming();
      }
    } catch (_error) { /* a frame may be reloading */ }
  }

  _playerRenderSignature(player) {
    const copy = structuredClone(player);
    // The fixed player bar does not justify rebuilding every gallery image
    // whenever its five-second poll advances a timer.
    if (copy?.seconds_elapsed != null) delete copy.seconds_elapsed;
    if (copy?.seconds_remaining != null) delete copy.seconds_remaining;
    return JSON.stringify(copy);
  }

  _updatePlayerTiming() {
    const player = this._player;
    const current = player?.current || {};
    const state = player?.state || "idle";
    const meta = this.shadowRoot?.querySelector("[data-player-meta]");
    if (meta && current.title && !["sending", "asleep", "unreachable"].includes(state)) {
      meta.textContent = [
        current.artist,
        player.playlist_name,
        player.paused ? "Paused" : this._timeLeft(player.seconds_remaining),
      ].filter(Boolean).join(" · ");
    }
    const progress = this.shadowRoot?.querySelector("[data-player-progress]");
    if (progress && player?.interval && state !== "sending") {
      const percent = Math.min(100, Math.max(0, (player.seconds_elapsed || 0) / player.interval * 100));
      progress.style.width = `${percent}%`;
    }
  }

  _startRefresh() {
    clearInterval(this._refreshTimer);
    this._refreshTimer = setInterval(() => this._loadPlayer(), 5000);
  }

  async _loadGallery(force = false) {
    if (!this._selectedFrameId) return;
    const entryId = this._selectedFrameId;
    const generation = ++this._galleryGeneration;
    const sources = this._selectedSource === "all"
      ? this._sources.filter((source) => source.available)
      : this._sources.filter((source) => source.key === this._selectedSource);
    const query = this._query.trim();
    const requestKey = `${entryId}\u0000${this._selectedSource}\u0000${this._selectedBrowseId}\u0000${query}`;
    const replacesVisibleQuery = requestKey !== this._galleryRequestKey;
    if (!force && !replacesVisibleQuery && this._galleryBySource.size
      && Date.now() - this._galleryLoadedAt < 5 * 60 * 1000) {
      this._galleryLoading = false;
      this._renderPreservingFocus();
      return;
    }
    this._loadingMore = false;
    this._renderLimit = INITIAL_RENDER_LIMIT;
    this._galleryRequestKey = requestKey;
    this._galleryLoading = true;
    // A manual refresh keeps the existing grid in place. A different query or
    // source gets one stable skeleton and one atomic result swap; individual
    // provider responses no longer repeatedly reorder the masonry.
    if (replacesVisibleQuery) {
      this._galleryBySource = new Map();
      this._galleryCursorBySource = new Map();
      this._galleryTotalBySource = new Map();
      this._sourceStatus = new Map();
      this._facets = { artists: [], colours: [], collections: [], eras: [] };
      this._galleryTitle = this._selectedBrowseId ? this._galleryTitle : "";
      this._renderPreservingFocus();
    }
    const nextBySource = new Map();
    const nextCursorBySource = new Map();
    const nextTotalBySource = new Map();
    const nextStatus = new Map();
    const nextFacets = { artists: [], colours: [], collections: [], eras: [] };
    const limit = this._selectedSource === "all" ? ALL_SOURCES_LIMIT : SOURCE_LIMIT;
    await Promise.all(sources.map(async (source) => {
      try {
        const params = new URLSearchParams({ entry_id: entryId, source: source.key, limit: String(limit) });
        if (this._selectedSource !== "all" && this._selectedBrowseId) params.set("browse_id", this._selectedBrowseId);
        if (query) params.set("q", query);
        if (force) params.set("refresh", "1");
        const data = await this._api(`gallery?${params}`);
        if (generation !== this._galleryGeneration || entryId !== this._selectedFrameId) return;
        nextBySource.set(source.key, data.results || []);
        nextCursorBySource.set(source.key, data.next_cursor ?? null);
        nextTotalBySource.set(source.key, data.total ?? (data.results || []).length);
        nextStatus.set(source.key, data.source_status?.[0] || { source: source.key, status: "ready" });
        if (this._selectedSource !== "all" && data.title) this._galleryTitle = data.title;
        this._mergeFacetsInto(nextFacets, data.facets || {});
      } catch (error) {
        if (generation !== this._galleryGeneration) return;
        nextStatus.set(source.key, { source: source.key, status: "error", detail: error.message });
      }
    }));
    if (generation !== this._galleryGeneration || entryId !== this._selectedFrameId) return;
    this._galleryBySource = nextBySource;
    this._galleryCursorBySource = nextCursorBySource;
    this._galleryTotalBySource = nextTotalBySource;
    this._sourceStatus = nextStatus;
    this._facets = nextFacets;
    this._galleryLoading = false;
    this._galleryLoadedAt = Date.now();
    if (query) localStorage.setItem("fraimic-last-search", query);
    this._renderPreservingFocus();
  }

  async _loadMoreGallery() {
    if (this._loadingMore || this._galleryLoading) return;
    if (this._renderLimit < this._filteredItems.length) {
      this._renderLimit += RENDER_PAGE_SIZE;
      this._renderPreservingFocus();
      return;
    }
    const pending = [...this._galleryCursorBySource.entries()].filter(([, cursor]) => cursor !== null && cursor !== undefined);
    if (!pending.length) return;
    const generation = this._galleryGeneration;
    this._loadingMore = true;
    this._renderPreservingFocus();
    await Promise.all(pending.map(async ([source, cursor]) => {
      try {
        const limit = this._selectedSource === "all" ? ALL_SOURCES_LIMIT : SOURCE_LIMIT;
        const params = new URLSearchParams({ entry_id: this._selectedFrameId, source, limit: String(limit), cursor: String(cursor) });
        if (this._selectedSource !== "all" && this._selectedBrowseId) params.set("browse_id", this._selectedBrowseId);
        if (this._query.trim()) params.set("q", this._query.trim());
        const data = await this._api(`gallery?${params}`);
        if (generation !== this._galleryGeneration) return;
        const existing = this._galleryBySource.get(source) || [];
        const seen = new Set(existing.map((item) => item.id));
        this._galleryBySource.set(source, [...existing, ...(data.results || []).filter((item) => !seen.has(item.id))]);
        this._galleryCursorBySource.set(source, data.next_cursor ?? null);
        this._galleryTotalBySource.set(source, data.total ?? existing.length + (data.results || []).length);
        this._mergeFacets(data.facets || {});
      } catch (error) {
        if (generation !== this._galleryGeneration) return;
        this._sourceStatus.set(source, { source, status: "error", detail: error.message });
      }
    }));
    if (generation !== this._galleryGeneration) return;
    this._loadingMore = false;
    this._renderPreservingFocus();
  }

  _mergeFacets(next) {
    this._mergeFacetsInto(this._facets, next);
  }

  _mergeFacetsInto(target, next) {
    for (const key of Object.keys(target)) {
      const values = new Map(target[key].map((item) => [item.value, item.count]));
      for (const item of next[key] || []) values.set(item.value, (values.get(item.value) || 0) + item.count);
      target[key] = [...values].map(([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count);
    }
  }

  get _allGalleryItems() {
    const seen = new Set();
    const items = [];
    for (const sourceItems of this._galleryBySource.values()) {
      for (const item of sourceItems) {
        const key = `${item.source}:${item.id}`;
        if (!seen.has(key)) { seen.add(key); items.push(item); }
      }
    }
    return items;
  }

  get _filteredItems() {
    return this._allGalleryItems.filter((item) => {
      if (this._colours.size && !this._colours.has(item.colour)) return false;
      if (this._artist && item.artist !== this._artist) return false;
      if (this._era && String(item.year) !== this._era) return false;
      if (this._fits && this._aspectDifference(item) > 0.15) return false;
      if (this._rendersWell && Number(item.palette_score) < 0.75) return false;
      return true;
    }).sort((a, b) => {
      const aDifference = this._aspectDifference(a);
      const bDifference = this._aspectDifference(b);
      const aUnknown = !Number.isFinite(aDifference);
      const bUnknown = !Number.isFinite(bDifference);
      if (aUnknown !== bUnknown) return aUnknown ? 1 : -1;
      const fitOrder = Number(aDifference > 0.15) - Number(bDifference > 0.15);
      if (fitOrder) return fitOrder;
      if (this._rendersWell && b.palette_score !== a.palette_score) return b.palette_score - a.palette_score;
      return aUnknown ? 0 : aDifference - bDifference;
    });
  }

  _aspectDifference(item) {
    if (!item.dimensions_known || !item.width || !item.height) return Number.POSITIVE_INFINITY;
    const frame = this._frame;
    const frameAspect = frame?.width && frame?.height
      ? ([90, 270].includes(frame.rotation) ? frame.height / frame.width : frame.width / frame.height)
      : 4 / 3;
    return Math.abs((item.width / item.height) / frameAspect - 1);
  }

  _mergeRouteTitle() {
    if (this._route === "playlist") return `<button class="btn quiet crumb-back" data-nav="/playlists">Playlists</button><span class="crumb">›</span><span class="brand">${h(this._playlist?.name || "Playlist")}</span>`;
    if (this._route === "playlists") return `<button class="btn quiet crumb-back" data-nav="/">Fraimic</button><span class="crumb">›</span><span class="brand">Playlists</span>`;
    return `<button class="btn quiet brand" data-nav="/">Fraimic</button>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    this.style.setProperty("--frame-aspect", this._frameAspect);
    const html = `
      <style>${css}</style>
      <div class="shell${this._dropActive ? " drop-active" : ""}${this._queueOpen ? " queue-open" : ""}">
        ${this._topTemplate()}
        ${this._route === "browse" ? this._filterTemplate() : ""}
        <main ${this._queueOpen ? "inert" : ""}>${this._mainTemplate()}</main>
        ${this._playerTemplate()}
        ${this._queueOpen ? this._queueTemplate() : ""}
        ${this._menuTemplate()}
        ${this._modalTemplate()}
        ${this._overlaysOpen ? this._overlayEditorTemplate() : ""}
        ${this._toast ? `<div class="toast${this._toast.error ? " error" : ""}" role="status" aria-live="polite"><span>${h(this._toast.text)}</span>${this._toast.action ? `<button data-toast-action>${h(this._toast.action)}</button>` : ""}</div>` : ""}
        <input id="upload" type="file" accept="image/*" multiple hidden>
      </div>`;
    this.shadowRoot.innerHTML = html;
    this._bind();
    this._signImages();
  }

  _renderPreservingFocus() {
    const active = this.shadowRoot.activeElement;
    const controls = [...this.shadowRoot.querySelectorAll("button, [href], input, select, textarea, [tabindex]")];
    const focus = active ? {
      id: active.id,
      ariaLabel: active.getAttribute("aria-label") || "",
      text: active.textContent.trim(),
      index: controls.indexOf(active),
    } : null;
    const start = active?.selectionStart;
    this._render();
    if (!focus) return;
    const replacements = [...this.shadowRoot.querySelectorAll("button, [href], input, select, textarea, [tabindex]")];
    const replacement = replacements.find((control) =>
      (focus.id && control.id === focus.id) ||
      (focus.ariaLabel && control.getAttribute("aria-label") === focus.ariaLabel) ||
      (focus.text && control.textContent.trim() === focus.text)
    ) || replacements[focus.index];
    replacement?.focus();
    if (typeof start === "number") replacement?.setSelectionRange?.(start, start);
  }

  _topTemplate() {
    const frames = this._frames.map((frame) => {
      const content = `<span class="dot ${frame.charging ? "charging" : frame.online ? "online" : ""}"></span>${h(frame.name)}`;
      const status = frame.charging ? "charging" : frame.online ? "online" : frame.asleep ? "asleep" : "unreachable";
      const label = `${frame.name}, ${status}${frame.battery == null ? "" : `, ${frame.battery}% battery`}`;
      return this._frames.length === 1
        ? `<span class="chip selected" aria-label="${h(label)}">${content}</span>`
        : `<button class="chip${frame.id === this._selectedFrameId ? " selected" : ""}" data-frame="${h(frame.id)}" role="radio" aria-checked="${frame.id === this._selectedFrameId}" aria-label="${h(label)}">${content}</button>`;
    }).join("");
    return `<header class="top">
      ${this._mergeRouteTitle()}
      <div class="frames" ${this._frames.length > 1 ? `role="radiogroup" aria-label="Frames"` : ""}>${frames}</div>
      <span class="spacer"></span>
      <button class="btn quiet" data-nav="/playlists"><ha-icon icon="mdi:playlist-music"></ha-icon><span class="nav-label">Playlists</span></button>
      <button class="btn quiet" data-upload><ha-icon icon="mdi:upload"></ha-icon><span class="nav-label">Upload</span></button>
      <button class="icon-btn" data-menu="app" aria-label="App menu"><ha-icon icon="mdi:dots-vertical"></ha-icon></button>
    </header>`;
  }

  _filterTemplate() {
    const colourLabel = this._colours.size ? `Colour: ${[...this._colours].join(", ")}` : "Colour";
    const activeFilters = this._colours.size || this._artist || this._era || this._fits || this._rendersWell || this._selectedSource !== "all";
    return `<div class="filter">
      <div class="search"><ha-icon icon="mdi:magnify"></ha-icon><input id="gallery-search" value="${h(this._query)}" placeholder="Search art, artist, subject, colour" aria-label="Search art, artist, subject, colour"></div>
      ${this._facets.colours.length || this._colours.size ? `<button class="chip${this._colours.size ? " selected" : ""}" data-menu="colour">${h(colourLabel)}</button>` : ""}
      <button class="chip${this._artist ? " selected" : ""}" data-menu="artist">${h(this._artist || "Artist")}</button>
      ${this._facets.eras.length ? `<button class="chip${this._era ? " selected" : ""}" data-menu="era">${h(this._era || "Era")}</button>` : ""}
      <button class="chip${this._fits ? " selected" : ""}" data-toggle="fits">Fits ${h(this._frame?.name || "frame")}</button>
      <button class="chip${this._rendersWell ? " selected" : ""}" data-toggle="renders" title="Ranked by frame aspect and source resolution.">Renders well</button>
      <span class="spacer"></span><span class="counter">${this._galleryCounter()}</span>
      ${activeFilters ? `<button class="btn quiet small" data-clear-filters>Clear filters</button>` : ""}
    </div>`;
  }

  _sourceNodeKey(source, browseId = "") { return `${source}\u0000${browseId}`; }

  _orderedSources() {
    const order = new Map(this._sourceOrder.map((key, index) => [key, index]));
    return [...this._sources].sort((a, b) =>
      (order.get(a.key) ?? Number.MAX_SAFE_INTEGER) - (order.get(b.key) ?? Number.MAX_SAFE_INTEGER));
  }

  _sourceChildrenTemplate(source, browseId = "", depth = 0) {
    if (depth > 4) return "";
    const parentKey = this._sourceNodeKey(source.key, browseId);
    const children = this._sourceChildren.get(parentKey);
    if (!children) return this._sourceTreeLoading.has(parentKey)
      ? `<div class="source-option" aria-live="polite"><span>Loading…</span></div>` : "";
    return children.map((child) => {
      const childId = child.id || "";
      const childKey = this._sourceNodeKey(source.key, childId);
      const childMeta = this._sourceNodeMeta.get(childKey);
      const canExpand = source.key !== "saved" && !(childMeta?.loaded && !childMeta.hasChildren);
      const expanded = this._expandedSources.has(childKey);
      const selected = this._selectedSource === source.key && this._selectedBrowseId === childId;
      return `<div class="source-child-row">
        ${canExpand ? `<button class="source-expand" data-source-expand="${h(source.key)}" data-browse-id="${h(childId)}" aria-label="${expanded ? "Collapse" : "Expand"} ${h(child.title)}" aria-expanded="${expanded}"><ha-icon icon="mdi:chevron-right"></ha-icon></button>` : `<span class="source-expand-placeholder"></span>`}
        <button class="source-option${selected ? " selected" : ""}" data-source-node="${h(source.key)}" data-browse-id="${h(childId)}" data-source-title="${h(child.title)}" aria-current="${selected ? "true" : "false"}"><span>${h(child.title)}</span>${child.count == null ? "" : `<span class="source-meta">${child.count}</span>`}</button>
        ${expanded ? `<div class="source-children open">${this._sourceChildrenTemplate(source, childId, depth + 1)}</div>` : ""}
      </div>`;
    }).join("");
  }

  _sourceRailTemplate() {
    const available = this._sources.filter((source) => source.available).length;
    const trees = this._orderedSources().map((source) => {
      const status = this._sourceStatus.get(source.key)?.status;
      const warning = status === "error" ? `<ha-icon icon="mdi:alert-circle-outline" title="Source unavailable"></ha-icon>` : "";
      const expanded = this._expandedSources.has(source.key);
      const selected = this._selectedSource === source.key && !this._selectedBrowseId;
      const icon = source.group === "library" ? "image-multiple-outline" : source.group === "photography" ? "camera-outline" : source.group === "daily" ? "calendar-star" : source.group === "collections" ? "palette-outline" : "image-outline";
      const meta = source.requires_key ? "key" : source.count;
      return `<div class="source-tree" data-source-tree="${h(source.key)}">
        <div class="source-tree-row">
          <button class="source-grip" draggable="true" data-source-move-handle="${h(source.key)}" aria-label="Reorder ${h(source.name)}"><ha-icon icon="mdi:drag-vertical"></ha-icon></button>
          ${source.hierarchical ? `<button class="source-expand" data-source-expand="${h(source.key)}" data-browse-id="" aria-label="${expanded ? "Collapse" : "Expand"} ${h(source.name)}" aria-expanded="${expanded}"><ha-icon icon="mdi:chevron-right"></ha-icon></button>` : `<span class="source-expand-placeholder"></span>`}
          <button class="source-option${selected ? " selected" : ""}" data-source="${h(source.key)}" ${source.available ? "" : "disabled"} aria-current="${selected ? "true" : "false"}"><ha-icon icon="mdi:${icon}"></ha-icon><span>${h(source.name)}</span><span class="source-meta">${warning}${meta == null ? "" : h(meta)}</span></button>
        </div>
        ${source.hierarchical && expanded ? `<div class="source-children open">${this._sourceChildrenTemplate(source)}</div>` : ""}
      </div>`;
    }).join("");
    const playlistsExpanded = this._expandedSources.has("@playlists");
    return `<nav class="source-rail" aria-label="Artwork navigation">
      <div class="source-group"><div class="source-group-label">Sources</div>
        <div class="source-tree-row"><span class="source-grip"></span><span class="source-expand-placeholder"></span><button class="source-option${this._selectedSource === "all" ? " selected" : ""}" data-source="all" aria-current="${this._selectedSource === "all" ? "true" : "false"}"><ha-icon icon="mdi:view-grid-outline"></ha-icon><span>All sources</span><span class="source-meta">${available}</span></button></div>
        ${trees}
      </div>
      <div class="source-divider"></div>
      <div class="source-group"><div class="source-group-label">Playlists</div>
        <div class="source-tree-row"><span class="source-grip"></span><button class="source-expand" data-static-expand="@playlists" aria-label="${playlistsExpanded ? "Collapse" : "Expand"} saved playlists" aria-expanded="${playlistsExpanded}"><ha-icon icon="mdi:chevron-right"></ha-icon></button><button class="source-option" data-nav="/playlists"><ha-icon icon="mdi:playlist-music-outline"></ha-icon><span>Saved playlists</span><span class="source-meta">${this._playlists.length}</span></button></div>
        ${playlistsExpanded ? `<div class="source-children open">${this._playlists.map((playlist) => `<div class="source-child-row"><span class="source-expand-placeholder"></span><button class="source-option" data-nav="/playlists/${encodeURIComponent(playlist.id)}"><span>${h(playlist.name)}</span><span class="source-meta">${playlist.slide_count}</span></button></div>`).join("")}</div>` : ""}
      </div>
    </nav>`;
  }

  async _loadSourceNode(source, browseId = "", renderLoading = true) {
    const key = this._sourceNodeKey(source, browseId);
    const existing = this._sourceNodeMeta.get(key);
    if (existing?.loaded) return existing;
    if (this._sourceTreeLoading.has(key)) return existing || null;
    this._sourceTreeLoading.add(key);
    if (renderLoading) this._renderPreservingFocus();
    try {
      const params = new URLSearchParams({ entry_id: this._selectedFrameId, source });
      if (browseId) params.set("browse_id", browseId);
      const data = await this._api(`gallery/tree?${params}`);
      const folders = data.folders || [];
      const meta = { hasItems: Boolean(data.has_items), hasChildren: folders.length > 0, loaded: true, title: data.title || "" };
      this._sourceChildren.set(key, folders);
      this._sourceNodeMeta.set(key, meta);
      return meta;
    } catch (error) {
      this._notify(this._friendlyError(error), { error: true });
      return null;
    } finally {
      this._sourceTreeLoading.delete(key);
    }
  }

  _persistExpandedSources() {
    storeValue("fraimic-expanded-sources", JSON.stringify([...this._expandedSources]));
  }

  async _toggleSourceNode(source, browseId = "") {
    const expansionKey = browseId ? this._sourceNodeKey(source, browseId) : source;
    if (this._expandedSources.has(expansionKey)) {
      this._expandedSources.delete(expansionKey);
      this._persistExpandedSources();
      this._renderPreservingFocus();
      return;
    }
    const meta = await this._loadSourceNode(source, browseId);
    if (!meta) return;
    this._expandedSources.add(expansionKey);
    this._persistExpandedSources();
    this._renderPreservingFocus();
  }

  async _activateSourceNode(source, browseId, title) {
    if (source === "saved") return this._setSource(source, browseId, title);
    const meta = await this._loadSourceNode(source, browseId);
    if (!meta) return;
    if (meta.hasItems || !meta.hasChildren) return this._setSource(source, browseId, meta.title || title);
    const expansionKey = this._sourceNodeKey(source, browseId);
    this._expandedSources.add(expansionKey);
    this._persistExpandedSources();
    this._renderPreservingFocus();
  }

  _toggleStaticSource(key) {
    this._expandedSources.has(key) ? this._expandedSources.delete(key) : this._expandedSources.add(key);
    this._persistExpandedSources();
    this._renderPreservingFocus();
  }

  _reorderSource(sourceKey, targetKey) {
    if (sourceKey === targetKey) return;
    const order = [...this._sourceOrder];
    const from = order.indexOf(sourceKey), to = order.indexOf(targetKey);
    if (from < 0 || to < 0) return;
    order.splice(to, 0, order.splice(from, 1)[0]);
    this._sourceOrder = order;
    storeValue("fraimic-source-order", JSON.stringify(order));
    this._renderPreservingFocus();
  }

  _galleryCounter() {
    if (this._galleryLoading) {
      const total = this._selectedSource === "all" ? this._sources.filter((source) => source.available).length : 1;
      const answered = this._sourceStatus.size;
      return `Searching ${Math.max(0, total - answered)} sources`;
    }
    const total = [...this._galleryTotalBySource.values()].reduce((sum, value) => sum + Number(value || 0), 0);
    return `${Math.max(total, this._filteredItems.length).toLocaleString()} results`;
  }

  _mainTemplate() {
    if (!this._frames.length) return `<div class="empty"><h2>No frames yet</h2><p>Fraimic finds frames on your network automatically. If yours is asleep, wake it by pressing the button on the back, then try again.</p><div class="empty-actions"><button class="btn primary" data-add-frame>Add a frame</button><button class="btn" data-reload-frames>Search again</button></div></div>`;
    if (this._route === "playlists") return this._playlistsTemplate();
    if (this._route === "playlist") return this._playlistTemplate();
    return this._browseTemplate();
  }

  _failureTemplate() {
    const failed = [...this._sourceStatus.entries()].filter(([, status]) => status.status === "error");
    const needsKey = [...this._sourceStatus.entries()].filter(([, status]) => status.status === "needs_key");
    if (needsKey.length && this._selectedSource !== "all") {
      const source = this._sources.find((item) => item.key === needsKey[0][0]);
      return `<div class="empty"><h2>${h(source?.name)} needs a free API key</h2><p>Add it once in the integration options and ${h(source?.name)} joins the gallery like any other source.</p><div class="empty-actions"><button class="btn primary" data-options>Open integration options</button></div></div>`;
    }
    if (!failed.length) return "";
    const names = failed.map(([key]) => this._sources.find((source) => source.key === key)?.name || key);
    return `<div class="failure"><span class="dot charging"></span><span>${h(names.join(" and "))} did not answer. Results are missing from those.</span><span class="spacer"></span><button class="btn small" data-retry>Retry</button><button class="btn quiet small" data-dismiss-failures>Dismiss</button></div>`;
  }

  _browseTemplate() {
    const failure = this._failureTemplate();
    const items = this._filteredItems;
    const visibleItems = items.slice(0, this._renderLimit);
    const layout = (body) => `<div class="browse-layout">${this._sourceRailTemplate()}<div class="browse-results">${failure}${body}</div></div>`;
    if (this._galleryLoading && !items.length) return layout(`<div class="content">${this._loadingTemplate()}</div>`);
    if (!items.length && !this._galleryLoading) return layout(`<div class="empty"><h2>Nothing matched</h2><p>Try all sources, or drop the Fits filter to include more art.</p><div class="empty-actions"><button class="btn primary" data-source="all">Search all sources</button><button class="btn" data-clear-filters>Clear filters</button></div></div>`);
    const discovering = !this._query.trim() && !this._colours.size && !this._artist && !this._era && !this._fits && !this._rendersWell;
    const rows = discovering ? this._discoveryRows(items) : "";
    const adding = this._addingToPlaylist ? this._playlists.find((playlist) => playlist.id === this._addingToPlaylist) : null;
    const firstRun = this._player?.state === "idle" && !localStorage.getItem(`fraimic-shown-${this._selectedFrameId}`)
      ? `<div class="empty" style="padding:44px 24px 20px"><h2>${h(this._frame.name)} is showing nothing yet</h2><p>Tap any picture below to put it on the wall, or start a playlist so it changes through the day.</p></div>` : "";
    return layout(`${adding ? `<div class="adding-bar"><b>Adding to ${h(adding.name)}</b><span class="spacer"></span><button class="btn quiet small" data-stop-adding>Done</button></div>` : ""}${firstRun}<div class="content">${rows}
      <div class="row-head"><h2>${discovering ? (this._galleryTitle || "Everything, newest first") : this._query ? this._query : (this._galleryTitle || "Results")}</h2><span class="spacer"></span><button class="btn quiet small" data-save-results>Save as playlist</button></div>
      <div class="masonry">${visibleItems.map((item) => this._tileTemplate(item)).join("")}</div>
      ${visibleItems.length < items.length || [...this._galleryCursorBySource.values()].some((cursor) => cursor != null) ? `<div class="load-more"><button class="btn" data-load-more ${this._loadingMore ? "disabled" : ""}>${this._loadingMore ? "Loading more" : "Load more"}</button></div>` : ""}
    </div>`);
  }

  _loadingTemplate() {
    const aspects = ["3/2", "3/4", "4/3", "1/1", "2/3", "16/9", "3/4", "5/4"];
    return `<div class="loading-grid">${aspects.map((aspect) => `<div class="placeholder"><div class="block" style="--skeleton-aspect:${aspect}"></div><div class="block-line"></div></div>`).join("")}</div>`;
  }

  _discoveryRows(items) {
    const library = items.filter((item) => item.source === "saved").slice(0, 20);
    const madeFor = [...items].sort((a, b) => {
      const difference = this._aspectDifference(a) - this._aspectDifference(b);
      return difference || b.palette_score - a.palette_score;
    }).slice(0, 20);
    const facets = this._facets.colours.slice(0, 2).map((facet) => ({ title: facet.value[0].toUpperCase() + facet.value.slice(1), items: items.filter((item) => item.colour === facet.value).slice(0, 20) }));
    const last = localStorage.getItem("fraimic-last-search");
    const rows = [
      { title: `Made for ${this._frame?.name}`, sub: "matched to the frame aspect and source resolution", items: madeFor },
      ...(last ? [{ title: "Continue where you left off", sub: last, items: items.filter((item) => `${item.title} ${item.artist || ""}`.toLowerCase().includes(last.toLowerCase())).slice(0, 20) }] : []),
      ...facets,
      { title: "Your library", sub: `${library.length} pictures`, items: library, manage: true },
    ];
    this._rowItemsByTitle = new Map(rows.map((row) => [row.title, row.items]));
    return rows.filter((row) => row.items.length >= 3).map((row) => `
      <div class="row-head"><h2>${h(row.title)}</h2>${row.sub ? `<span class="sub">${h(row.sub)}</span>` : ""}<span class="spacer"></span>${row.manage ? `<button class="btn quiet small" data-source="saved">Manage</button>` : `<button class="btn quiet small" data-save-row="${h(row.title)}">Save as playlist</button>`}</div>
      <div class="strip">${row.items.map((item) => this._tileTemplate(item, true)).join("")}</div>`).join("");
  }

  _tileTemplate(item, compact = false) {
    const aspect = `${Math.max(1, item.width || 4)} / ${Math.max(1, item.height || 3)}`;
    const src = this._imageAttrs(item.thumbnail_url, `${item.title}${item.artist ? `, ${item.artist}` : ""}`);
    return `<article class="tile" tabindex="0" draggable="true" data-item="${h(item.source)}:${h(item.id)}" data-keyboard-item>
      <div class="art" style="--art-aspect:${aspect}" data-detail="${h(item.source)}:${h(item.id)}">
        <img ${src} width="${Math.max(1, item.width || 4)}" height="${Math.max(1, item.height || 3)}" loading="lazy" decoding="async">
        ${item.queued ? `<span class="badge right">queued</span>` : ""}
        <div class="actions">
          <button class="btn primary" data-art-action="show_now" data-source-id="${h(item.source)}" data-item-id="${h(item.id)}">Show now</button>
          <button class="btn" data-art-action="queue" data-source-id="${h(item.source)}" data-item-id="${h(item.id)}">${item.queued ? "Queued" : "+ Queue"}</button>
          ${compact ? "" : `<button class="icon-btn" data-quick-playlist data-source-id="${h(item.source)}" data-item-id="${h(item.id)}" aria-label="Add to playlist"><ha-icon icon="mdi:playlist-plus"></ha-icon></button>`}
          <button class="icon-btn" data-detail="${h(item.source)}:${h(item.id)}" aria-label="Picture details"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>
        </div>
      </div>
      ${compact ? "" : `<div class="cap"><b>${h(item.title)}</b>${item.artist ? `<span>${h(item.artist)}</span>` : ""}</div>`}
    </article>`;
  }

  _playlistsTemplate() {
    if (!this._playlists.length) return `<div class="empty"><h2>No playlists yet. A playlist is a list of art that rotates on your frame.</h2><div class="empty-actions"><button class="btn primary" data-create-playlist>Create playlist</button><button class="btn" data-nav="/">Browse art</button></div></div>`;
    return `<div class="content"><div class="playlist-head"><div><h1>Playlists</h1><p>Art that rotates on your frames.</p></div><span class="spacer"></span><button class="btn primary" data-create-playlist>Create playlist</button></div>
      <div class="playlist-grid">${this._playlists.map((playlist) => this._playlistCard(playlist)).join("")}</div></div>`;
  }

  _playlistCard(playlist) {
    const thumbs = [...(playlist.thumbnails || []), null, null, null, null].slice(0, 4);
    return `<article class="playlist-card" data-playlist-drop="${h(playlist.id)}">
      <button data-nav="/playlists/${encodeURIComponent(playlist.id)}" style="width:100%;text-align:left;padding:0">
        <div class="mosaic">${thumbs.map((thumb) => `<div class="glass">${thumb ? `<img ${this._imageAttrs(thumb, "")}>` : ""}</div>`).join("")}</div>
        <h2>${h(playlist.name)}</h2><p>${playlist.slide_count} pictures · ${this._formatInterval(playlist.interval)}${playlist.shuffle ? " · shuffle" : ""}</p>
        ${playlist.playing?.length ? `<p>Playing on ${h(playlist.playing.map((frame) => frame.name).join(", "))}</p>` : ""}
      </button>
      <div class="row-actions"><button class="btn small" data-play-playlist="${h(playlist.id)}">Play</button><button class="icon-btn" data-playlist-menu="${h(playlist.id)}" aria-label="Playlist menu"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button></div>
    </article>`;
  }

  _playlistTemplate() {
    const playlist = this._playlist;
    if (!playlist) return this._loadingTemplate();
    const slides = playlist.slides || [];
    return `<div class="content"><div class="playlist-head"><div><h1>${h(playlist.name)}</h1><p>${slides.length} pictures · changes every ${this._formatInterval(playlist.interval)}${playlist.shuffle ? " · shuffle" : ""}</p></div><span class="spacer"></span><button class="btn" data-play-playlist="${h(playlist.id)}">Play on ${h(this._frame?.name)}</button><button class="btn primary" data-add-from-browse="${h(playlist.id)}">Add art</button><button class="icon-btn" data-playlist-menu="${h(playlist.id)}" aria-label="Playlist menu"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button></div>
      ${slides.length ? `<ol class="queue-list">${slides.map((slide, index) => this._slideTemplate(slide, index, playlist)).join("")}</ol>` : `<div class="empty"><h2>This playlist is empty. Add art from the gallery, or drop pictures here.</h2><div class="empty-actions"><button class="btn primary" data-add-from-browse="${h(playlist.id)}">Add art</button></div></div>`}
    </div>`;
  }

  _slideTemplate(slide, index, playlist) {
    const movement = playlist.shuffle ? "" : `<button class="icon-btn" data-move-slide="top" data-slide-index="${index}" aria-label="Move to top" ${index === 0 ? "disabled" : ""}><ha-icon icon="mdi:chevron-double-up"></ha-icon></button><button class="icon-btn" data-move-slide="up" data-slide-index="${index}" aria-label="Move up" ${index === 0 ? "disabled" : ""}><ha-icon icon="mdi:chevron-up"></ha-icon></button><button class="icon-btn" data-move-slide="down" data-slide-index="${index}" aria-label="Move down" ${index === playlist.slides.length - 1 ? "disabled" : ""}><ha-icon icon="mdi:chevron-down"></ha-icon></button><button class="icon-btn" data-move-slide="bottom" data-slide-index="${index}" aria-label="Move to bottom" ${index === playlist.slides.length - 1 ? "disabled" : ""}><ha-icon icon="mdi:chevron-double-down"></ha-icon></button>`;
    return `<li class="slide-row" ${playlist.shuffle ? "" : "draggable=\"true\""} data-slide-id="${h(slide.id)}" data-slide-index="${index}">
      <span class="grip" aria-hidden="true"><ha-icon icon="mdi:drag"></ha-icon></span><span class="number">${index + 1}</span>
      <div class="row-art glass">${slide.thumbnail_url ? `<img ${this._imageAttrs(slide.thumbnail_url, "")}>` : ""}</div>
      <div class="row-copy"><b>${h(slide.title)}</b><span>${h(slide.meta)}${slide.overlays === "inherit" && this._player?.overlay_count ? ` · Inheriting ${this._player.overlay_count} overlays from ${this._frame?.name}` : ""}</span></div>
      <div class="row-actions">${movement}<button class="icon-btn" data-slide-settings="${h(slide.id)}" aria-label="Slide settings"><ha-icon icon="mdi:tune"></ha-icon></button><button class="icon-btn" data-remove-slide="${h(slide.id)}" aria-label="Remove"><ha-icon icon="mdi:close"></ha-icon></button></div>
    </li>`;
  }

  _playerTemplate() {
    const player = this._player;
    if (!this._frame) return `<footer class="player"><div class="player-copy"><b>Nothing playing</b><span>Pick a playlist, or show a picture from the gallery</span></div></footer>`;
    const current = player?.current || {};
    const state = player?.state || "idle";
    let title = current.title || "Nothing playing";
    let meta = "Pick a playlist, or show a picture from the gallery";
    if (state === "sending") meta = `Sending to ${this._frame.name}. The panel takes about 30 seconds.`;
    else if (state === "asleep") meta = `${this._frame.name} is asleep · still showing this`;
    else if (state === "unreachable") {
      title = `Could not reach ${this._frame.name}`;
      meta = `Last seen ${this._lastSeenMinutes(this._frame.last_seen)} minutes ago, check power and wifi.`;
    } else if (current.title) meta = [current.artist, player.playlist_name, player.paused ? "Paused" : this._timeLeft(player.seconds_remaining)].filter(Boolean).join(" · ");
    const progress = state === "sending"
      ? Number(player.sending_progress || 0)
      : player?.interval ? Math.min(100, Math.max(0, (player.seconds_elapsed || 0) / player.interval * 100)) : 0;
    const transport = player?.transport_available && !["idle", "unreachable"].includes(state)
      ? `<div class="transport"><button class="icon-btn previous" data-player-action="previous" aria-label="Previous" ${state === "sending" ? "disabled" : ""}><ha-icon icon="mdi:skip-previous"></ha-icon></button><button class="btn primary" data-player-action="${player?.paused ? "play" : "pause"}" aria-label="${player?.paused ? "Play" : "Pause"}" ${state === "sending" ? "disabled" : ""}><ha-icon icon="mdi:${player?.paused ? "play" : "pause"}"></ha-icon></button><button class="icon-btn next" data-player-action="next" aria-label="Next" ${state === "sending" ? "disabled" : ""}><ha-icon icon="mdi:skip-next"></ha-icon></button></div>`
      : "";
    const stateActions = state === "idle"
      ? `<button class="btn primary" data-change-playlist>Choose a playlist</button>`
      : state === "unreachable"
        ? `<button class="btn" data-player-action="retry">Retry</button><button class="btn quiet" data-device>Device page</button>`
        : "";
    return `<footer class="player ${h(state)}" tabindex="0" data-player>
      <div class="player-art glass">${current.thumbnail_url ? `<img ${this._imageAttrs(current.thumbnail_url, "")}>` : ""}</div>
      <div class="player-copy"><b>${h(title)}</b><span data-player-meta>${h(meta)}</span></div>
      ${!["idle", "asleep", "unreachable"].includes(state) ? `<div class="progress"><i data-player-progress style="width:${progress}%"></i></div>` : ""}
      ${transport}${state === "asleep" && player?.waiting_count ? `<span class="counter">${player.waiting_count} waiting</span>` : ""}
      <span class="spacer"></span>${stateActions}${player?.overlay_count && state !== "unreachable" ? `<button class="chip overlay-tag" data-overlays>${player.overlay_count} overlays</button>` : ""}<button class="btn" data-queue-toggle>Queue ${player?.queue_count || 0} <ha-icon icon="mdi:chevron-${this._queueOpen ? "down" : "up"}"></ha-icon></button><button class="icon-btn frame-more" data-menu="frame" aria-label="Frame menu"><ha-icon icon="mdi:dots-vertical"></ha-icon></button>
    </footer>`;
  }

  _queueTemplate() {
    const player = this._player || {};
    const hand = player.hand_queue || [];
    const playlist = player.playlist?.items || [];
    const shuffled = Boolean(player.playlist?.shuffle);
    const interval = this._formatInterval(player.interval).replace(/^every /, "");
    const intervalControl = player.playlist_id ? `<button class="btn queue-interval${this._menu === "interval" ? " selected" : ""}" data-menu="interval" aria-expanded="${this._menu === "interval"}"><small>Changes every</small><b>${h(interval)} <ha-icon icon="mdi:chevron-down"></ha-icon></b></button>` : "";
    return `<section class="queue-sheet" style="--queue-height:${this._queueHeight}px" aria-label="Queue" tabindex="-1">
      <div class="queue-handle" data-queue-handle aria-label="Resize queue"></div>
      <div class="queue-head"><h2>Queue</h2><span class="spacer"></span>${intervalControl}<button class="icon-btn" data-queue-size="smaller" aria-label="Make queue smaller"><ha-icon icon="mdi:chevron-down"></ha-icon></button><button class="icon-btn" data-queue-size="larger" aria-label="Make queue larger"><ha-icon icon="mdi:chevron-up"></ha-icon></button><button class="icon-btn" data-queue-toggle aria-label="Close queue"><ha-icon icon="mdi:close"></ha-icon></button></div>
      ${this._menu === "interval" && player.playlist_id ? this._intervalMenuTemplate("queue-interval-menu") : ""}
      ${hand.length ? `<div class="queue-head"><h2>Next in queue · added by you, played once</h2><span class="spacer"></span><button class="btn small" data-clear-queue>Clear</button></div><ol class="queue-list" data-art-drop="queue">${hand.map((item, index) => this._queueRow(item, index, "queue", hand.length, true)).join("")}</ol>` : `<div class="queue-head counter" data-art-drop="queue">Drop a picture here to play it next</div>`}
      ${player.playlist_id ? `<div class="queue-head"><h2>Next from ${h(player.playlist_name || "playlist")}${shuffled ? ", shuffled" : ""}</h2><span class="spacer"></span><button class="btn quiet small" data-nav="/playlists/${encodeURIComponent(player.playlist_id)}">Open playlist</button></div>${playlist.length ? `${shuffled ? "" : `<div class="failure">Reordering here changes the playlist.</div>`}<ol class="queue-list" data-art-drop="playlist">${playlist.map((item, index) => this._queueRow(item, index, "playlist", playlist.length, !shuffled)).join("")}</ol>` : ""}` : `<div class="empty" style="padding:24px"><p>No playlist on this frame.</p><button class="btn primary" data-change-playlist>Choose a playlist</button></div>`}
    </section>`;
  }

  _queueRow(item, index, section, count, reorderable) {
    const movement = reorderable ? `<button class="icon-btn" data-move-queue="top" data-section="${section}" data-index="${index}" aria-label="Move to top" ${index === 0 ? "disabled" : ""}><ha-icon icon="mdi:chevron-double-up"></ha-icon></button><button class="icon-btn" data-move-queue="up" data-section="${section}" data-index="${index}" aria-label="Move up" ${index === 0 ? "disabled" : ""}><ha-icon icon="mdi:chevron-up"></ha-icon></button><button class="icon-btn" data-move-queue="down" data-section="${section}" data-index="${index}" aria-label="Move down" ${index === count - 1 ? "disabled" : ""}><ha-icon icon="mdi:chevron-down"></ha-icon></button><button class="icon-btn" data-move-queue="bottom" data-section="${section}" data-index="${index}" aria-label="Move to bottom" ${index === count - 1 ? "disabled" : ""}><ha-icon icon="mdi:chevron-double-down"></ha-icon></button>` : "";
    return `<li class="queue-row" ${reorderable ? `draggable="true" data-queue-section="${section}"` : ""} data-queue-index="${index}" data-queue-id="${h(item.id)}"><span class="grip"><ha-icon icon="mdi:drag"></ha-icon></span><div class="row-art glass">${item.thumbnail_url ? `<img ${this._imageAttrs(item.thumbnail_url, "")}>` : ""}</div><div class="row-copy"><b>${h(item.title)}</b><span>${h(item.meta)}</span></div><div class="row-actions"><button class="icon-btn" data-play-queue data-section="${section}" data-index="${index}" data-slide-id="${h(item.id)}" aria-label="Play now" ${this._player?.sending ? "disabled" : ""}><ha-icon icon="mdi:play"></ha-icon></button>${movement}${section === "queue" ? `<button class="icon-btn" data-remove-queue="${index}:${h(item.id)}" aria-label="Remove"><ha-icon icon="mdi:close"></ha-icon></button>` : ""}</div></li>`;
  }

  _menuTemplate() {
    if (!this._menu) return "";
    if (this._menu === "app") return `<div class="menu top-menu"><h3>App menu</h3><button data-source="saved">Manage library <span>${this._galleryBySource.get("saved")?.length || ""}</span></button><button data-options>Sources, cache and performance</button><button data-reload>Reload sources</button><button data-add-frame>Add a frame</button><button data-docs>Documentation</button></div>`;
    if (this._menu === "frame") return `<div class="menu player-menu"><h3>${h(this._frame?.name)}</h3><button data-overlays>Overlays <span>${this._player?.overlay_count || 0} on</span></button><button data-change-playlist>Change playlist <span>›</span></button><button data-toggle-shuffle>Shuffle <span>${this._player?.playlist?.shuffle ? "on" : "off"}</span></button><button data-menu="interval">Changes every <span>${h(this._formatInterval(this._player?.interval))}</span></button><button data-options>Image, cache and performance <span>›</span></button><button data-player-action="refresh">Refresh panel now</button>${this._frame?.charging ? "" : `<button data-player-action="sleep">Put to sleep</button>`}<button data-device>Device page</button></div>`;
    if (this._menu === "interval") {
      return this._queueOpen ? "" : this._intervalMenuTemplate("menu player-menu");
    }
    if (["colour", "artist", "era"].includes(this._menu)) return this._facetMenu();
    return "";
  }

  _intervalMenuTemplate(className) {
    const values = [[900,"15 minutes"],[1800,"30 minutes"],[2700,"45 minutes"],[3600,"1 hour"],[7200,"2 hours"],[14400,"4 hours"],[43200,"12 hours"],[86400,"Once a day"]];
    return `<div class="${className}"><h3>Changes every</h3>${values.map(([value,label]) => `<button data-interval="${value}">${label}<span>${value === this._player?.interval ? "current" : ""}</span></button>`).join("")}<div class="failure">Each change costs a 30 second refresh and a little battery.</div></div>`;
  }

  _facetMenu() {
    const key = this._menu;
    const items = key === "colour" ? PALETTE.map((value) => ({ value, count: this._facets.colours.find((item) => item.value === value)?.count || 0 })) : this._facets[`${key}s`] || [];
    return `<div class="menu top-menu"><h3>${key[0].toUpperCase() + key.slice(1)}</h3>${items.slice(0, 100).map((item) => {
      const selected = key === "colour" ? this._colours.has(item.value) : this[`_${key}`] === String(item.value);
      return `<button data-facet="${key}" data-facet-value="${h(item.value)}"><ha-icon icon="mdi:${selected ? "checkbox-marked" : "checkbox-blank-outline"}"></ha-icon>${h(item.value)}<span>${item.count}</span></button>`;
    }).join("")}</div>`;
  }

  _modalTemplate() {
    if (!this._modal) return "";
    const { title, body, actions = "", subtitle = "", headerActions = "", className = "" } = this._modal;
    return `<div class="modal-backdrop" data-modal-backdrop><section class="dialog${className ? ` ${h(className)}` : ""}" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><div class="dialog-title"><div class="dialog-heading"><h2 id="dialog-title">${h(title)}</h2>${subtitle ? `<div class="dialog-subtitle">${subtitle}</div>` : ""}</div><span class="spacer"></span><div class="dialog-header-actions">${headerActions}<button class="icon-btn" data-close-modal aria-label="Close"><ha-icon icon="mdi:close"></ha-icon></button></div></div><div class="dialog-body">${body}</div>${actions ? `<div class="dialog-actions">${actions}</div>` : ""}</section></div>`;
  }

  _overlayEditorTemplate() {
    const data = this._overlayData;
    if (!data) return `<section class="overlay-editor">${this._loadingTemplate()}</section>`;
    const selected = this._overlayDraft.find((overlay) => overlay.id === this._selectedOverlayId);
    const preview = data.preview_thumbnails.find((item) => item.id === this._selectedPreview) || data.preview_thumbnails[0];
    return `<section class="overlay-editor">
      <header class="editor-top"><span class="brand">${h(this._frame?.name)}</span><span class="crumb">›</span><span class="brand">Overlays</span><span class="counter">${h(this._frame?.width)} × ${h(this._frame?.height)}</span><span class="spacer"></span>${this._frames.length > 1 ? `<button class="btn quiet" data-copy-overlays>Copy to ${h(this._frames.find((frame) => frame.id !== this._selectedFrameId)?.name)}</button>` : ""}<button class="btn" data-discard-overlays>Discard</button><button class="btn primary" data-save-overlays>Save</button></header>
      <div class="editor-grid"><div class="canvas-pane"><div class="canvas-row"><div class="canvas">${preview?.thumbnail_url ? `<img ${this._imageAttrs(preview.thumbnail_url, "")}>` : ""}${this._overlayDraft.filter((overlay) => overlay.enabled).map((overlay) => this._overlayBox(overlay)).join("")}</div><div class="editor-hint"><b>Preview over</b><p>Check legibility against the darkest and lightest art in the playlist.</p><p>The panel has six colours and no transparency, so a plate is solid or nothing.</p></div></div>
      <div class="preview-strip">${data.preview_thumbnails.map((item) => `<button class="preview-thumb glass${item.id === preview?.id ? " selected" : ""}" data-preview="${h(item.id)}" title="${h(item.title)}${item.darkest ? " · darkest" : item.lightest ? " · lightest" : ""}">${item.thumbnail_url ? `<img ${this._imageAttrs(item.thumbnail_url, "")}>` : ""}</button>`).join("")}</div></div>
      <aside class="inspector"><div class="inspector-section"><h3>Overlays on this frame</h3>${this._overlayDraft.map((overlay, index) => this._layerTemplate(overlay, index)).join("")}<button class="btn quiet" data-add-overlay>+ Add overlay</button></div>${selected ? this._inspectorTemplate(selected) : this._presetTemplate()}</aside></div>
    </section>`;
  }

  _overlayBox(overlay) {
    const label = overlay.type === "clock" ? "09:41" : overlay.type === "caption" ? "Title · Artist · Source" : overlay.type[0].toUpperCase() + overlay.type.slice(1);
    const [plateColour, plateText] = PLATE_THEME[overlay.plate_color] || PLATE_THEME.white;
    return `<div class="overlay-box ${h(overlay.plate)}${overlay.id === this._selectedOverlayId ? " selected" : ""}" style="--plate-color:${plateColour};--plate-text:${plateText};left:${overlay.x / 12 * 100}%;top:${overlay.y / 8 * 100}%;width:${overlay.w / 12 * 100}%;height:${overlay.h / 8 * 100}%" data-overlay-box="${h(overlay.id)}"><span>${h(label)}</span><span class="resize" data-overlay-resize="${h(overlay.id)}"></span></div>`;
  }

  _layerTemplate(overlay, index) {
    return `<div class="layer${overlay.id === this._selectedOverlayId ? " selected" : ""}" draggable="true" data-layer-index="${index}" data-select-overlay="${h(overlay.id)}"><button class="icon-btn" data-toggle-overlay="${h(overlay.id)}" aria-label="${overlay.enabled ? "Disable" : "Enable"}"><ha-icon icon="mdi:${overlay.enabled ? "toggle-switch" : "toggle-switch-off-outline"}"></ha-icon></button><div class="layer-copy"><b>${h(overlay.type[0].toUpperCase() + overlay.type.slice(1))}</b><span>${h(overlay.anchor.replaceAll("_", " "))} · ${h(overlay.visibility?.mode || "always")}</span></div><button class="icon-btn" data-layer-move="up:${h(overlay.id)}" aria-label="Move up" ${index === 0 ? "disabled" : ""}><ha-icon icon="mdi:chevron-up"></ha-icon></button><button class="icon-btn" data-layer-move="down:${h(overlay.id)}" aria-label="Move down" ${index === this._overlayDraft.length - 1 ? "disabled" : ""}><ha-icon icon="mdi:chevron-down"></ha-icon></button></div>`;
  }

  _inspectorTemplate(overlay) {
    return `<div class="inspector-section"><h3>Selected: ${h(overlay.type[0].toUpperCase() + overlay.type.slice(1))}</h3>
      ${this._overlayOptionsTemplate(overlay)}
    </div>
    <div class="inspector-section"><h3>Position</h3><div class="anchor-grid">${ANCHORS.map((anchor) => `<button class="${overlay.anchor === anchor ? "selected" : ""}" data-anchor="${anchor}" aria-label="${anchor.replaceAll("_", " ")}"></button>`).join("")}</div><div class="seg" style="margin-top:8px">${["s","m","l"].map((size) => `<button class="${overlay.size === size ? "selected" : ""}" data-overlay-size="${size}">${size.toUpperCase()}</button>`).join("")}</div><p class="counter">Or drag on the canvas. Snaps to a 12 by 8 grid.</p></div>
    <div class="inspector-section"><h3>Plate</h3><div class="seg">${["none","panel","outline"].map((plate) => `<button class="${overlay.plate === plate ? "selected" : ""}" data-overlay-plate="${plate}">${plate[0].toUpperCase() + plate.slice(1)}</button>`).join("")}</div><div class="field"><label>Colour</label><select data-overlay-field="plate_color">${PALETTE.slice(0,6).map((colour) => `<option value="${colour}" ${overlay.plate_color === colour ? "selected" : ""}>${colour}</option>`).join("")}</select></div></div>
    <div class="inspector-section"><h3>Text size</h3><div class="seg">${["s","m","l"].map((size) => `<button class="${overlay.text_size === size ? "selected" : ""}" data-text-size="${size}">${size.toUpperCase()}</button>`).join("")}</div></div>
    <div class="inspector-section"><h3>Show</h3><div class="seg">${["always","times","condition"].map((mode) => `<button class="${overlay.visibility?.mode === mode ? "selected" : ""}" data-visibility="${mode}">${mode[0].toUpperCase() + mode.slice(1)}</button>`).join("")}</div>${overlay.visibility?.mode === "times" ? `<div class="field"><label>From</label><input type="time" data-visibility-field="from" value="${h(overlay.visibility.from)}"></div><div class="field"><label>To</label><input type="time" data-visibility-field="to" value="${h(overlay.visibility.to)}"></div><div class="weekday-row">${[["mon","M"],["tue","T"],["wed","W"],["thu","T"],["fri","F"],["sat","S"],["sun","S"]].map(([day,label]) => `<button class="${overlay.visibility?.days?.includes(day) ? "selected" : ""}" data-weekday="${day}" aria-label="${day}">${label}</button>`).join("")}</div>` : ""}${overlay.visibility?.mode === "condition" ? `<div class="field"><label>Entity</label><input data-visibility-field="entity" value="${h(overlay.visibility.entity || "")}"></div><div class="field"><label>State</label><input data-visibility-field="state" value="${h(overlay.visibility.state || "on")}"></div>` : ""}${["todo","agenda","entities"].includes(overlay.type) ? `<label class="check-row"><input type="checkbox" data-visibility-check="hide_when_empty" ${overlay.visibility?.hide_when_empty ? "checked" : ""}> Hide when empty</label>` : ""}</div>
    <div class="inspector-section"><button class="btn danger" data-remove-overlay>Remove this overlay</button></div>`;
  }

  _overlayOptionsTemplate(overlay) {
    const options = overlay.options || {};
    const entity = (domain, label = "Entity", value = options.entity) => `<div class="field"><label>${label}</label><select data-overlay-option="entity"><option value="">Choose entity</option>${(this._overlayData.entities?.[domain] || []).map((item) => `<option value="${h(item)}" ${value === item ? "selected" : ""}>${h(item)}</option>`).join("")}</select></div>`;
    const number = (key, label, value, min, max) => `<div class="field"><label>${label}</label><input type="number" min="${min}" max="${max}" data-overlay-option="${key}" value="${h(value)}"></div>`;
    const text = (key, label, value = "") => `<div class="field"><label>${label}</label><input data-overlay-option="${key}" value="${h(value)}"></div>`;
    if (overlay.type === "clock" || overlay.type === "date") return `<div class="field"><label>Format</label><input data-overlay-option="format" value="${h(options.format || (overlay.type === "clock" ? "%H:%M" : "%A, %-d %B"))}"></div>${overlay.type === "clock" ? `<p class="counter">Updates when the picture changes, not every minute. E-ink refreshes cost battery.</p>` : ""}`;
    if (overlay.type === "todo") return `${entity("todo")}${number("max_items", "Max items", options.max_items || 6, 1, 20)}<label class="check-row"><input type="checkbox" data-overlay-option="show_title" ${options.show_title !== false ? "checked" : ""}> Show title</label>`;
    if (overlay.type === "agenda") return `<div class="field"><label>Calendars</label><input data-overlay-option-list="entities" value="${h((options.entities || []).join(", "))}"></div>${number("days", "Days ahead", options.days || 3, 1, 14)}${number("max_events", "Max events", options.max_events || 6, 1, 20)}`;
    if (overlay.type === "weather") return `${entity("weather")}<div class="field"><label>View</label><select data-overlay-option="view"><option value="current" ${options.view !== "forecast" ? "selected" : ""}>Current</option><option value="forecast" ${options.view === "forecast" ? "selected" : ""}>Forecast</option></select></div>${options.view === "forecast" ? number("count", "Count", options.count || 5, 1, 8) : ""}`;
    if (overlay.type === "stat") return `${entity("sensor")}${text("name", "Name", options.name)}${text("unit", "Unit", options.unit)}${number("precision", "Precision", options.precision ?? 1, 0, 3)}<label class="check-row"><input type="checkbox" data-overlay-option="trend" ${options.trend ? "checked" : ""}> Trend</label>`;
    if (overlay.type === "entities") return `<div class="field"><label>Entity list</label><input data-overlay-option-list="entities" value="${h((options.entities || []).map((item) => typeof item === "string" ? item : item.entity).join(", "))}"></div>${number("max_rows", "Max rows", options.max_rows || 6, 1, 30)}`;
    if (overlay.type === "chart") return `<div class="field"><label>Entities</label><input data-overlay-option-list="entities" value="${h((options.entities || []).join(", "))}"></div>${number("hours", "Hours", options.hours || 24, 1, 168)}<div class="field"><label>Style</label><select data-overlay-option="style">${["line","area","bar"].map((style) => `<option value="${style}" ${options.style === style ? "selected" : ""}>${style}</option>`).join("")}</select></div>${number("min", "Minimum", options.min ?? 0, -100000, 100000)}${number("max", "Maximum", options.max ?? 100, -100000, 100000)}`;
    if (overlay.type === "gauge") return `${entity("sensor")}${number("min", "Minimum", options.min ?? 0, -100000, 100000)}${number("max", "Maximum", options.max ?? 100, -100000, 100000)}<div class="field"><label>Thresholds</label><textarea data-overlay-thresholds>${h(JSON.stringify(options.thresholds || []))}</textarea></div>`;
    if (overlay.type === "text") return `<div class="field"><label>Template</label><textarea data-overlay-option="template">${h(options.template || "")}</textarea></div><div class="field"><label>Align</label><select data-overlay-option="align"><option value="left" ${options.align !== "center" ? "selected" : ""}>Left</option><option value="center" ${options.align === "center" ? "selected" : ""}>Centre</option></select></div><div class="field"><label>Size</label><select data-overlay-option="size">${["s","m","l"].map((size) => `<option value="${size}" ${options.size === size ? "selected" : ""}>${size.toUpperCase()}</option>`).join("")}</select></div>`;
    if (overlay.type === "caption") return `<div class="check-row">${["title","artist","source","year"].map((field) => `<label><input type="checkbox" data-caption-field="${field}" ${(options.fields || []).includes(field) ? "checked" : ""}> ${field}</label>`).join("")}</div>`;
    return "";
  }

  _presetTemplate() {
    const presets = [["clock","Clock corner","Time, top left"],["todo","Todo corner","A list, bottom right"],["info","Info strip","Clock, weather, date"],["side","Side panel","Agenda and stats"],["caption","Caption","Title, artist, source"],["morning","Morning panel","Full dashboard, 06:00 to 09:00"]];
    return `<div class="inspector-section"><h3>${this._overlayDraft.length ? "Add overlay" : "No overlays yet"}</h3><div class="preset-grid">${presets.map(([id,name,meta]) => `<button class="preset" data-preset="${id}"><b>${name}</b><span class="cap"><span>${meta}</span></span></button>`).join("")}</div><h3 style="margin-top:16px">One overlay</h3><div class="type-grid">${OVERLAY_TYPES.map((type) => `<button data-preset="${type}">${type[0].toUpperCase() + type.slice(1)}</button>`).join("")}</div><button class="btn quiet" data-start-empty>Start from nothing</button></div>`;
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-nav]").forEach((node) => node.onclick = () => this._navigate(node.dataset.nav));
    root.querySelectorAll("[data-frame]").forEach((node) => node.onclick = () => this._selectFrame(node.dataset.frame));
    root.querySelectorAll("[data-source]").forEach((node) => node.onclick = () => this._setSource(node.dataset.source));
    root.querySelectorAll("[data-source-node]").forEach((node) => node.onclick = () => this._activateSourceNode(node.dataset.sourceNode, node.dataset.browseId || "", node.dataset.sourceTitle || ""));
    root.querySelectorAll("[data-source-expand]").forEach((node) => node.onclick = () => this._toggleSourceNode(node.dataset.sourceExpand, node.dataset.browseId || ""));
    root.querySelectorAll("[data-static-expand]").forEach((node) => node.onclick = () => this._toggleStaticSource(node.dataset.staticExpand));
    root.querySelectorAll("[data-menu]").forEach((node) => node.onclick = (event) => { event.stopPropagation(); this._menu = this._menu === node.dataset.menu ? null : node.dataset.menu; this._renderPreservingFocus(); });
    root.querySelector("#gallery-search")?.addEventListener("input", (event) => this._search(event.target.value));
    root.querySelector("[data-toggle='fits']")?.addEventListener("click", () => { this._fits = !this._fits; this._render(); });
    root.querySelector("[data-toggle='renders']")?.addEventListener("click", () => { this._rendersWell = !this._rendersWell; this._render(); });
    root.querySelectorAll("[data-clear-filters]").forEach((node) => node.onclick = () => this._clearFilters());
    root.querySelectorAll("[data-facet]").forEach((node) => node.onclick = () => this._setFacet(node.dataset.facet, node.dataset.facetValue));
    root.querySelectorAll("[data-detail]").forEach((node) => node.onclick = (event) => { event.stopPropagation(); const [source, ...rest] = node.dataset.detail.split(":"); this._openDetail(source, rest.join(":"), node); });
    root.querySelectorAll("[data-art-action]").forEach((node) => node.onclick = (event) => { event.stopPropagation(); if (node.dataset.artAction === "show_now") this._showNow(node.dataset.sourceId, node.dataset.itemId); else this._artAction(node.dataset.artAction, node.dataset.sourceId, node.dataset.itemId); });
    root.querySelectorAll("[data-quick-playlist]").forEach((node) => node.onclick = (event) => { event.stopPropagation(); this._quickPlaylist(node.dataset.sourceId, node.dataset.itemId); });
    root.querySelectorAll("[data-save-results]").forEach((node) => node.onclick = () => this._saveAsPlaylist(this._query || "Gallery", this._filteredItems));
    root.querySelectorAll("[data-save-row]").forEach((node) => node.onclick = () => this._saveAsPlaylist(node.dataset.saveRow, this._rowItemsByTitle?.get(node.dataset.saveRow) || []));
    root.querySelectorAll("[data-load-more]").forEach((node) => node.onclick = () => this._loadMoreGallery());
    root.querySelectorAll("[data-stop-adding]").forEach((node) => node.onclick = () => { this._addingToPlaylist = null; this._render(); });
    root.querySelectorAll("[data-upload]").forEach((node) => node.onclick = () => root.getElementById("upload")?.click());
    root.getElementById("upload")?.addEventListener("change", (event) => this._uploadFiles([...event.target.files]));
    root.querySelectorAll("[data-player-action]").forEach((node) => node.onclick = () => this._playerAction(node.dataset.playerAction));
    root.querySelectorAll("[data-queue-toggle]").forEach((node) => node.onclick = () => this._toggleQueue());
    root.querySelectorAll("[data-queue-size]").forEach((node) => node.onclick = () => this._stepQueueSize(node.dataset.queueSize));
    root.querySelector("[data-queue-handle]")?.addEventListener("pointerdown", (event) => this._dragQueueSheet(event));
    root.querySelector("[data-clear-queue]")?.addEventListener("click", () => this._queueAction({ action: "clear" }));
    root.querySelectorAll("[data-play-queue]").forEach((node) => node.onclick = () => this._queueAction({ action: "play", section: node.dataset.section, index: Number(node.dataset.index), slide_id: node.dataset.slideId }));
    root.querySelectorAll("[data-remove-queue]").forEach((node) => node.onclick = () => { const [index, ...id] = node.dataset.removeQueue.split(":"); this._queueAction({ action: "remove", index: Number(index), slide_id: id.join(":") }); });
    root.querySelectorAll("[data-move-queue]").forEach((node) => node.onclick = () => this._moveQueue(node.dataset.section, Number(node.dataset.index), node.dataset.moveQueue));
    root.querySelectorAll("[data-create-playlist]").forEach((node) => node.onclick = () => this._createPlaylist());
    root.querySelectorAll("[data-play-playlist]").forEach((node) => node.onclick = () => this._playPlaylist(node.dataset.playPlaylist));
    root.querySelectorAll("[data-add-from-browse]").forEach((node) => node.onclick = () => { this._addingToPlaylist = node.dataset.addFromBrowse; this._navigate("/"); this._notify(`Add art to ${this._playlist?.name || "playlist"}.`); });
    root.querySelectorAll("[data-playlist-menu]").forEach((node) => node.onclick = () => this._playlistMenu(node.dataset.playlistMenu));
    root.querySelectorAll("[data-move-slide]").forEach((node) => node.onclick = () => this._moveSlide(Number(node.dataset.slideIndex), node.dataset.moveSlide));
    root.querySelectorAll("[data-remove-slide]").forEach((node) => node.onclick = () => this._removeSlide(node.dataset.removeSlide));
    root.querySelectorAll("[data-slide-settings]").forEach((node) => node.onclick = () => this._slideSettings(node.dataset.slideSettings));
    root.querySelector("[data-close-modal]")?.addEventListener("click", () => this._closeModal());
    root.querySelector("[data-modal-backdrop]")?.addEventListener("click", (event) => { if (event.target === event.currentTarget) this._closeModal(); });
    root.querySelectorAll("[data-overlays]").forEach((node) => node.onclick = () => this._openOverlays());
    root.querySelectorAll("[data-change-playlist]").forEach((node) => node.onclick = () => this._changePlaylist());
    root.querySelector("[data-toggle-shuffle]")?.addEventListener("click", () => this._toggleShuffle());
    root.querySelectorAll("[data-interval]").forEach((node) => node.onclick = () => this._setInterval(Number(node.dataset.interval)));
    root.querySelectorAll("[data-options]").forEach((node) => node.onclick = () => this._haNavigate("/config/integrations/integration/fraimic"));
    root.querySelectorAll("[data-add-frame]").forEach((node) => node.onclick = () => this._haNavigate("/config/integrations/dashboard/add?domain=fraimic"));
    root.querySelectorAll("[data-reload], [data-retry]").forEach((node) => node.onclick = () => this._loadGallery(true));
    root.querySelector("[data-reload-frames]")?.addEventListener("click", () => this._loadAll());
    root.querySelector("[data-dismiss-failures]")?.addEventListener("click", () => { for (const [key, status] of this._sourceStatus) if (status.status === "error") this._sourceStatus.delete(key); this._render(); });
    root.querySelector("[data-docs]")?.addEventListener("click", () => window.open("https://github.com/kristofferR/ha-fraimic-eink", "_blank", "noopener"));
    root.querySelector("[data-device]")?.addEventListener("click", () => {
      const host = this._frame?.host;
      if (host) window.open(`http://${host}`, "_blank", "noopener");
    });
    root.querySelector("[data-toast-action]")?.addEventListener("click", () => { const action = this._toast?.callback; this._toast = null; action?.(); this._render(); });
    this._bindKeyboard();
    this._bindDnD();
    this._bindSourceReorder();
    this._bindDetailModal();
    this._bindOverlayEditor();
    root.host.onclick = (event) => { if (this._menu && !event.composedPath().some((node) => node?.classList?.contains("menu")) && !event.composedPath().some((node) => node?.dataset?.menu)) { this._menu = null; this._renderPreservingFocus(); } };
  }

  _bindKeyboard() {
    this.shadowRoot.querySelectorAll("[data-keyboard-item]").forEach((node) => node.onkeydown = (event) => {
      if (event.key === "Enter") node.querySelector("[data-detail]")?.click();
      if (event.key.toLowerCase() === "s") node.querySelector("[data-art-action='show_now']")?.click();
      if (event.key.toLowerCase() === "q") node.querySelector("[data-art-action='queue']")?.click();
    });
    this.shadowRoot.querySelector("[data-player]")?.addEventListener("keydown", (event) => { if (event.code === "Space") { event.preventDefault(); this._playerAction("toggle"); } });
  }

  _handleKeyDown(event) {
    if (event.key === "Escape") {
      if (this._modal) this._closeModal();
      else if (this._overlaysOpen) this._requestCloseOverlays();
      else if (this._queueOpen) this._toggleQueue();
    }
    if (this._modal && event.key === "Tab") this._trapModalFocus(event);
  }

  _bindDnD() {
    const shell = this.shadowRoot.querySelector(".shell");
    shell?.addEventListener("dragenter", (event) => { if ([...event.dataTransfer?.types || []].includes("Files")) { this._dropActive = true; this._render(); } });
    shell?.addEventListener("dragover", (event) => { if ([...event.dataTransfer?.types || []].includes("Files")) event.preventDefault(); });
    shell?.addEventListener("drop", (event) => { if (event.dataTransfer?.files?.length) { event.preventDefault(); this._dropActive = false; this._uploadFiles([...event.dataTransfer.files]); } });
    this.shadowRoot.querySelectorAll("[data-item]").forEach((tile) => {
      tile.ondragstart = (event) => {
        const [source, ...id] = tile.dataset.item.split(":");
        this._draggedArt = { source, itemId: id.join(":"), title: tile.querySelector(".cap b")?.textContent || "Picture" };
        event.dataTransfer.effectAllowed = "copy";
        event.dataTransfer.setData("text/plain", JSON.stringify(this._draggedArt));
      };
      tile.ondragend = () => { this._draggedArt = null; };
    });
    this.shadowRoot.querySelectorAll("[data-art-drop]").forEach((target) => {
      target.addEventListener("dragover", (event) => { if (this._draggedArt) event.preventDefault(); });
      target.addEventListener("drop", (event) => {
        if (!this._draggedArt) return;
        event.preventDefault();
        const row = event.target.closest("[data-queue-index]");
        this._dropArt(target.dataset.artDrop, row ? Number(row.dataset.queueIndex) : undefined);
      });
    });
    this.shadowRoot.querySelectorAll("[data-playlist-drop]").forEach((target) => {
      target.addEventListener("dragover", (event) => { if (this._draggedArt) event.preventDefault(); });
      target.addEventListener("drop", (event) => { if (this._draggedArt) { event.preventDefault(); this._dropArt("playlist-card", undefined, target.dataset.playlistDrop); } });
    });
    const player = this.shadowRoot.querySelector("[data-player]");
    let expandTimer = null;
    player?.addEventListener("dragenter", () => { if (this._draggedArt && !this._queueOpen) expandTimer = setTimeout(() => { this._queueOpen = true; this._render(); }, 600); });
    player?.addEventListener("dragleave", () => clearTimeout(expandTimer));
    this._bindReorder("[data-queue-section]", (source, target) => {
      if (source.dataset.queueSection !== target.dataset.queueSection) return;
      this._reorderQueue(source.dataset.queueSection, Number(source.dataset.queueIndex), Number(target.dataset.queueIndex));
    });
    this._bindReorder("[data-slide-id]", (source, target) => this._reorderSlides(Number(source.dataset.slideIndex), Number(target.dataset.slideIndex)));
  }

  _bindSourceReorder() {
    let dragged = null;
    const trees = [...this.shadowRoot.querySelectorAll("[data-source-tree]")];
    for (const tree of trees) {
      tree.ondragstart = (event) => {
        dragged = tree;
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", tree.dataset.sourceTree);
      };
      tree.ondragover = (event) => {
        if (!dragged || dragged === tree) return;
        event.preventDefault();
        tree.classList.add("drag-over");
      };
      tree.ondragleave = () => tree.classList.remove("drag-over");
      tree.ondrop = (event) => {
        event.preventDefault();
        tree.classList.remove("drag-over");
        if (dragged) this._reorderSource(dragged.dataset.sourceTree, tree.dataset.sourceTree);
        dragged = null;
      };
      tree.ondragend = () => {
        dragged = null;
        this.shadowRoot.querySelectorAll(".source-tree.drag-over").forEach((node) => node.classList.remove("drag-over"));
      };
    }
    this.shadowRoot.querySelectorAll("[data-source-move-handle]").forEach((handle) => {
      handle.onkeydown = (event) => {
        if (!event.altKey || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
        const index = this._sourceOrder.indexOf(handle.dataset.sourceMoveHandle);
        const target = this._sourceOrder[index + (event.key === "ArrowUp" ? -1 : 1)];
        if (!target) return;
        event.preventDefault();
        this._reorderSource(handle.dataset.sourceMoveHandle, target);
      };
    });
  }

  _dropArt(section, index, playlistId = null) {
    const art = this._draggedArt;
    this._draggedArt = null;
    if (!art) return;
    if (section === "queue") this._artAction("queue", art.source, art.itemId, null, { queueIndex: index });
    else {
      const beforeSlideId = Number.isInteger(index)
        ? this._player?.playlist?.items?.[index]?.id
        : null;
      this._artAction("add_playlist", art.source, art.itemId, playlistId || this._player?.playlist_id, { beforeSlideId });
    }
  }

  _bindReorder(selector, onDrop) {
    let dragged = null;
    this.shadowRoot.querySelectorAll(selector).forEach((row) => {
      row.ondragstart = (event) => { dragged = row; event.dataTransfer.effectAllowed = "move"; };
      row.ondragover = (event) => { if (dragged && dragged !== row) { event.preventDefault(); row.classList.add("drag-over"); } };
      row.ondragleave = () => row.classList.remove("drag-over");
      row.ondrop = (event) => { event.preventDefault(); row.classList.remove("drag-over"); if (dragged) onDrop(dragged, row); dragged = null; };
      row.ondragend = () => { dragged = null; this.shadowRoot.querySelectorAll(".drag-over").forEach((node) => node.classList.remove("drag-over")); };
    });
  }

  _bindOverlayEditor() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-select-overlay]").forEach((node) => node.onclick = () => { this._selectedOverlayId = node.dataset.selectOverlay; this._render(); });
    root.querySelectorAll("[data-toggle-overlay]").forEach((node) => node.onclick = (event) => { event.stopPropagation(); this._updateOverlay(node.dataset.toggleOverlay, (overlay) => { overlay.enabled = !overlay.enabled; }); });
    root.querySelectorAll("[data-layer-move]").forEach((node) => node.onclick = () => { const [direction, id] = node.dataset.layerMove.split(":"); const index = this._overlayDraft.findIndex((overlay) => overlay.id === id); const target = direction === "up" ? index - 1 : index + 1; if (target >= 0 && target < this._overlayDraft.length) { [this._overlayDraft[index], this._overlayDraft[target]] = [this._overlayDraft[target], this._overlayDraft[index]]; this._render(); } });
    root.querySelectorAll("[data-overlay-box]").forEach((node) => node.onpointerdown = (event) => { if (event.target.dataset.overlayResize) return; this._dragOverlay(event, node.dataset.overlayBox, false); });
    root.querySelectorAll("[data-overlay-resize]").forEach((node) => node.onpointerdown = (event) => { event.stopPropagation(); this._dragOverlay(event, node.dataset.overlayResize, true); });
    root.querySelectorAll("[data-preview]").forEach((node) => node.onclick = () => { this._selectedPreview = node.dataset.preview; this._render(); });
    root.querySelectorAll("[data-anchor]").forEach((node) => node.onclick = () => this._setAnchor(node.dataset.anchor));
    root.querySelectorAll("[data-overlay-size]").forEach((node) => node.onclick = () => this._setOverlaySize(node.dataset.overlaySize));
    root.querySelectorAll("[data-overlay-plate]").forEach((node) => node.onclick = () => this._updateSelected((overlay) => { overlay.plate = node.dataset.overlayPlate; }));
    root.querySelectorAll("[data-text-size]").forEach((node) => node.onclick = () => this._updateSelected((overlay) => { overlay.text_size = node.dataset.textSize; }));
    root.querySelectorAll("[data-visibility]").forEach((node) => node.onclick = () => this._updateSelected((overlay) => { overlay.visibility ||= {}; overlay.visibility.mode = node.dataset.visibility; }));
    root.querySelectorAll("[data-overlay-option]").forEach((node) => node.onchange = () => this._updateSelected((overlay) => { overlay.options ||= {}; overlay.options[node.dataset.overlayOption] = node.type === "checkbox" ? node.checked : node.type === "number" ? Number(node.value) : node.value; }, false));
    root.querySelectorAll("[data-overlay-option-list]").forEach((node) => node.onchange = () => this._updateSelected((overlay) => { overlay.options ||= {}; overlay.options[node.dataset.overlayOptionList] = node.value.split(",").map((value) => value.trim()).filter(Boolean); }, false));
    root.querySelectorAll("[data-overlay-thresholds]").forEach((node) => node.onchange = () => { try { const value = JSON.parse(node.value); this._updateSelected((overlay) => { overlay.options ||= {}; overlay.options.thresholds = value; }, false); } catch (_error) { this._notify("Thresholds must be valid JSON.", { error: true }); } });
    root.querySelectorAll("[data-caption-field]").forEach((node) => node.onchange = () => this._updateSelected((overlay) => { overlay.options ||= {}; const fields = new Set(overlay.options.fields || []); node.checked ? fields.add(node.dataset.captionField) : fields.delete(node.dataset.captionField); overlay.options.fields = [...fields]; }, false));
    root.querySelectorAll("[data-overlay-field]").forEach((node) => node.onchange = () => this._updateSelected((overlay) => { overlay[node.dataset.overlayField] = node.value; }));
    root.querySelectorAll("[data-visibility-field]").forEach((node) => node.onchange = () => this._updateSelected((overlay) => { overlay.visibility ||= {}; overlay.visibility[node.dataset.visibilityField] = node.value; }));
    root.querySelectorAll("[data-visibility-check]").forEach((node) => node.onchange = () => this._updateSelected((overlay) => { overlay.visibility ||= {}; overlay.visibility[node.dataset.visibilityCheck] = node.checked; }, false));
    root.querySelectorAll("[data-weekday]").forEach((node) => node.onclick = () => this._updateSelected((overlay) => { overlay.visibility ||= {}; const days = new Set(overlay.visibility.days || []); days.has(node.dataset.weekday) ? days.delete(node.dataset.weekday) : days.add(node.dataset.weekday); overlay.visibility.days = [...days]; }));
    root.querySelector("[data-remove-overlay]")?.addEventListener("click", () => { this._overlayDraft = this._overlayDraft.filter((overlay) => overlay.id !== this._selectedOverlayId); this._selectedOverlayId = this._overlayDraft[0]?.id || null; this._render(); });
    root.querySelector("[data-add-overlay]")?.addEventListener("click", () => { this._selectedOverlayId = null; this._render(); });
    root.querySelectorAll("[data-preset]").forEach((node) => node.onclick = () => this._applyPreset(node.dataset.preset));
    root.querySelector("[data-start-empty]")?.addEventListener("click", () => { this._overlayDraft = []; this._selectedOverlayId = null; this._render(); });
    root.querySelector("[data-save-overlays]")?.addEventListener("click", () => this._saveOverlays());
    root.querySelector("[data-discard-overlays]")?.addEventListener("click", () => this._discardOverlays());
    root.querySelector("[data-copy-overlays]")?.addEventListener("click", () => this._copyOverlays());
    this._bindReorder("[data-layer-index]", (source, target) => { const from = Number(source.dataset.layerIndex), to = Number(target.dataset.layerIndex); const [overlay] = this._overlayDraft.splice(from, 1); this._overlayDraft.splice(to, 0, overlay); this._render(); });
  }

  async _selectFrame(id) {
    if (id === this._selectedFrameId) return;
    this._selectedFrameId = id;
    localStorage.setItem("fraimic-frame", id);
    this._queueOpen = false;
    await Promise.all([this._loadPlayer(false), this._loadSources(), this._loadPlaylists()]);
    await this._loadRoute();
  }

  _setSource(source, browseId = "", title = "") {
    this._selectedSource = source;
    this._selectedBrowseId = source === "all" ? "" : browseId;
    this._galleryTitle = source === "all" ? "" : title;
    this._menu = null;
    if (this._route !== "browse") this._navigate("/");
    else this._loadGallery();
  }

  _search(value) {
    this._query = value;
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => this._loadGallery(), SEARCH_DELAY);
  }

  _clearFilters() {
    this._selectedSource = "all"; this._selectedBrowseId = ""; this._galleryTitle = ""; this._colours.clear(); this._artist = ""; this._era = ""; this._fits = false; this._rendersWell = false; this._menu = null; this._loadGallery();
  }

  _setFacet(kind, value) {
    if (kind === "colour") this._colours.has(value) ? this._colours.delete(value) : this._colours.add(value);
    else this[`_${kind}`] = this[`_${kind}`] === value ? "" : value;
    this._render();
  }

  async _artAction(action, source, itemId, playlistId = null, options = {}, targetEntryId = null) {
    if (action === "queue" && this._findItem(source, itemId)?.queued) return;
    try {
      const entryId = targetEntryId || this._selectedFrameId;
      const fit = options.fit || "cover";
      const crop = fit === "cover" ? options.crop : null;
      const data = await this._api("gallery/action", this._json({ action, entry_id: entryId, source, item_id: itemId, playlist_id: playlistId, fit, tone: options.tone || "balanced", crop, queue_index: options.queueIndex, playlist_before_id: options.beforeSlideId }));
      const item = this._findItem(source, itemId);
      if (item && data.item) Object.assign(item, data.item);
      const targetFrame = this._frames.find((frame) => frame.id === entryId) || this._frame;
      if (!options.quiet) {
        if (action === "show_now") { localStorage.setItem(`fraimic-shown-${entryId}`, "1"); this._notify(`Sending to ${targetFrame.name}. The panel takes about 30 seconds.`); }
        if (action === "queue") this._notify(`Added to the queue, ${(this._player?.waiting_count || 0) + 1} waiting.`, { action: "Open queue", callback: () => { this._queueOpen = true; } });
        if (action === "add_playlist") this._notify(`Added to ${this._playlists.find((playlist) => playlist.id === playlistId)?.name}.`, { action: "Open", callback: () => this._navigate(`/playlists/${encodeURIComponent(playlistId)}`) });
        if (action === "save") this._notify("Saved to your library.");
        if (action === "favorite") this._notify("Added to favorites.");
        if (action === "unfavorite") this._notify("Removed from favorites.");
        await Promise.all([this._loadPlayer(false), this._loadPlaylists()]);
        this._render();
      }
      return data;
    } catch (error) {
      if (options.quiet) throw error;
      this._notify(this._friendlyError(error), { error: true });
    }
  }

  _findItem(source, itemId) { return this._allGalleryItems.find((item) => item.source === source && item.id === itemId); }

  _quickPlaylist(source, itemId) {
    const target = this._addingToPlaylist || this._player?.playlist_id || (this._playlists.length === 1 ? this._playlists[0].id : null);
    if (target) return this._artAction("add_playlist", source, itemId, target);
    this._choosePlaylist(source, itemId);
  }

  _choosePlaylist(source, itemId, options = {}) {
    this._openModal("Add to playlist", `<div class="queue-list">${this._playlists.map((playlist) => `<button class="queue-row" data-modal-playlist="${h(playlist.id)}"><span>${h(playlist.name)}</span><span class="spacer"></span><span class="counter">${playlist.slide_count}</span></button>`).join("")}</div>`);
    this.shadowRoot.querySelectorAll("[data-modal-playlist]").forEach((node) => node.onclick = () => { this._closeModal(); this._artAction("add_playlist", source, itemId, node.dataset.modalPlaylist, options); });
  }

  _showNow(source, itemId, options = {}) {
    if (this._frames.length <= 1) { this._closeModal(); return this._artAction("show_now", source, itemId, null, options); }
    const item = this._detail || this._findItem(source, itemId) || {};
    const frames = [...this._frames].sort((a, b) => this._fitDifference(item, a) - this._fitDifference(item, b));
    this._openModal("Show now", `<div class="queue-list">${frames.map((frame, index) => `<button class="queue-row" data-show-frame="${h(frame.id)}"><b>${h(frame.name)}</b><span class="spacer"></span><span class="counter">${index === 0 ? `${this._frameShape(frame)}, suits this` : `${this._frameShape(frame)}, will crop`}</span></button>`).join("")}${frames.length === 2 ? `<button class="queue-row" data-show-both>Both frames</button>` : ""}</div>`);
    this.shadowRoot.querySelectorAll("[data-show-frame]").forEach((node) => node.onclick = () => {
      const frame = this._frames.find((candidate) => candidate.id === node.dataset.showFrame);
      const targetOptions = { ...options, crop: frame?.id === this._selectedFrameId ? options.crop : this._defaultCrop(item, frame) };
      this._closeModal(); this._artAction("show_now", source, itemId, null, targetOptions, frame.id);
    });
    this.shadowRoot.querySelector("[data-show-both]")?.addEventListener("click", async () => {
      this._closeModal();
      for (const frame of frames) {
        const targetOptions = { ...options, crop: frame.id === this._selectedFrameId ? options.crop : this._defaultCrop(item, frame) };
        await this._artAction("show_now", source, itemId, null, targetOptions, frame.id);
      }
    });
  }

  async _openDetail(source, itemId, trigger) {
    const generation = ++this._detailGeneration;
    const item = this._findItem(source, itemId);
    this._modalTrigger = trigger;
    this._openModal(item?.title || "Picture", this._loadingTemplate());
    try {
      const params = new URLSearchParams({ entry_id: this._selectedFrameId, source, item_id: itemId });
      const detail = await this._api(`gallery/detail?${params}`);
      if (generation !== this._detailGeneration || !this._modal) return;
      this._detail = { ...detail, source, itemId };
      const key = this._cropKey(source, itemId, this._selectedFrameId);
      const crop = this._cropDrafts.get(key) || detail.saved_crop || this._defaultCrop(detail, this._frame);
      this._cropDrafts.set(key, crop);
      this._detailOptions = { fit: "cover", tone: "balanced", crop };
      this._renderDetailModal();
    } catch (error) { this._closeModal(); this._notify(this._friendlyError(error), { error: true }); }
  }

  _renderDetailModal() {
    const detail = this._detail;
    if (!detail) return;
    const options = this._detailOptions;
    const crop = options.crop;
    const cropWindow = options.fit === "cover" ? `<div class="crop-window" data-crop-window data-label="Visible on ${h(this._frame.name)}" style="${this._cropStyle(crop)}"><span class="crop-resize" data-crop-resize></span></div>` : "";
    const relatedFrame = this._frames.filter((frame) => frame.id !== this._selectedFrameId).sort((a, b) => this._fitDifference(detail, a) - this._fitDifference(detail, b))[0];
    const sourceHref = this._safeHref(detail.source_page_url);
    const artAspect = `${Math.max(1, Number(detail.width) || 4)} / ${Math.max(1, Number(detail.height) || 3)}`;
    const fitNotes = { cover: "Fills the whole frame", contain: "Shows the complete artwork", stretch: "Fills without cropping" };
    const toneNotes = { vivid: "More colour and contrast", balanced: "Natural colour and contrast", soft: "Gentler, paper-like result" };
    const artistLink = detail.artist ? `<button class="detail-text-link" data-related-query="${h(detail.artist)}">${h(detail.artist)}</button>` : "Unknown";
    const sourceLink = `<button class="detail-text-link" data-related-source="${h(detail.source)}">${h(detail.source_name || detail.source)}</button>`;
    const body = `<div class="detail-grid">
      <div class="detail-workspace">
        <div class="detail-section-head"><h3>Position artwork</h3><span class="spacer"></span><span class="counter">${h(this._frame.name)} · ${h(this._frame.width)} × ${h(this._frame.height)}</span></div>
        <div class="crop-stage" style="--art-aspect:${artAspect}"><img ${this._imageAttrs(detail.image_url, `${detail.title}${detail.artist ? `, ${detail.artist}` : ""}`)}>${cropWindow}</div>
        ${options.fit === "cover" ? `<div class="crop-tools"><button class="btn small" data-crop-command="reset"><ha-icon icon="mdi:restore"></ha-icon> Reset</button><button class="btn small" data-crop-command="centre"><ha-icon icon="mdi:image-filter-center-focus"></ha-icon> Centre</button><button class="btn small" data-crop-command="in"><ha-icon icon="mdi:magnify-plus-outline"></ha-icon> Zoom in</button><button class="btn small" data-crop-command="out"><ha-icon icon="mdi:magnify-minus-outline"></ha-icon> Zoom out</button></div><p class="crop-hint"><ha-icon icon="mdi:cursor-move"></ha-icon> Drag the crop to choose what stays inside the frame.</p>` : `<p class="crop-hint">${h(fitNotes[options.fit])}.</p>`}
      </div>
      <aside class="detail-inspector" aria-label="Display settings">
        <div class="detail-section-head"><h3>Display settings</h3><span class="spacer"></span><span class="counter">Spectra 6</span></div>
        <div class="detail-setting"><div class="detail-setting-copy"><h3>Fit</h3><p>${h(fitNotes[options.fit])}</p></div><select class="detail-select" data-detail-fit aria-label="Artwork fit"><option value="cover" ${options.fit === "cover" ? "selected" : ""}>Cover</option><option value="contain" ${options.fit === "contain" ? "selected" : ""}>Contain</option><option value="stretch" ${options.fit === "stretch" ? "selected" : ""}>Stretch</option></select></div>
        <div class="detail-setting"><div class="detail-setting-copy"><h3>Tone</h3><p>${h(toneNotes[options.tone])}</p></div><select class="detail-select" data-detail-tone aria-label="Artwork tone"><option value="vivid" ${options.tone === "vivid" ? "selected" : ""}>Vivid</option><option value="balanced" ${options.tone === "balanced" ? "selected" : ""}>Balanced</option><option value="soft" ${options.tone === "soft" ? "selected" : ""}>Soft</option></select></div>
        <section class="artwork-details"><h3>Artwork details</h3><dl class="detail-meta-list">
          <div class="detail-meta-row"><dt>Artist</dt><dd>${artistLink}</dd></div>
          <div class="detail-meta-row"><dt>Source</dt><dd>${sourceLink}</dd></div>
          <div class="detail-meta-row"><dt>Original</dt><dd>${h(detail.width)} × ${h(detail.height)}</dd></div>
          ${detail.year ? `<div class="detail-meta-row"><dt>Year</dt><dd>${h(detail.year)}</dd></div>` : ""}
          ${detail.license ? `<div class="detail-meta-row"><dt>License</dt><dd>${h(detail.license)}</dd></div>` : ""}
        </dl>${detail.description ? `<p class="detail-description">${h(detail.description)}</p>` : ""}
        <div class="detail-links">${relatedFrame && this._fitDifference(detail, relatedFrame) < this._fitDifference(detail, this._frame) ? `<button class="btn quiet small" data-related-frame="${h(relatedFrame.id)}">Better on ${h(relatedFrame.name)}</button>` : ""}${sourceHref ? `<a class="btn quiet small" href="${h(sourceHref)}" target="_blank" rel="noopener"><ha-icon icon="mdi:open-in-new"></ha-icon> Open original artwork</a>` : ""}${detail.source === "saved" ? `<button class="btn quiet small danger" data-detail-action="delete">Remove from library</button>` : ""}</div></section>
      </aside>
    </div>`;
    const actions = `<span class="detail-ready">Ready for ${h(this._frame.name)} · ${h(options.fit[0].toUpperCase() + options.fit.slice(1))} · ${h(options.tone[0].toUpperCase() + options.tone.slice(1))}</span><span class="spacer"></span><button class="btn primary" data-detail-action="show_now"><ha-icon icon="mdi:send"></ha-icon> Show now</button><button class="btn" data-detail-action="play_next">Play next</button><button class="btn" data-detail-action="queue">Add to queue</button><button class="btn" data-detail-action="playlist"><ha-icon icon="mdi:playlist-plus"></ha-icon> Add to playlist</button>`;
    const subtitle = `${artistLink}<span>·</span>${sourceLink}`;
    const headerActions = `<button class="icon-btn favorite-btn" data-detail-favorite aria-label="${detail.favorite ? "Remove from favorites" : "Add to favorites"}" aria-pressed="${Boolean(detail.favorite)}" ${this._favoriteBusy ? "disabled" : ""}><ha-icon icon="mdi:star${detail.favorite ? "" : "-outline"}"></ha-icon></button>`;
    this._openModal(detail.title, body, actions, { className: "detail-dialog", subtitle, headerActions });
  }

  _bindDetailModal() {
    const detail = this._detail;
    const options = this._detailOptions;
    if (!detail || !options || !this._modal?.className?.includes("detail-dialog")) return;
    this.shadowRoot.querySelectorAll("[data-detail-action]").forEach((node) => node.onclick = () => {
      const action = node.dataset.detailAction;
      if (action === "playlist") this._choosePlaylist(detail.source, detail.itemId, options);
      else if (action === "show_now") this._showNow(detail.source, detail.itemId, options);
      else if (action === "delete") this._deleteSavedPicture(detail);
      else { this._closeModal(); this._artAction(action, detail.source, detail.itemId, null, options); }
    });
    this.shadowRoot.querySelector("[data-detail-favorite]")?.addEventListener("click", () => this._toggleDetailFavorite());
    this.shadowRoot.querySelector("[data-detail-fit]")?.addEventListener("change", (event) => { options.fit = event.target.value; this._renderDetailModal(); });
    this.shadowRoot.querySelector("[data-detail-tone]")?.addEventListener("change", (event) => { options.tone = event.target.value; this._renderDetailModal(); });
    this.shadowRoot.querySelectorAll("[data-crop-command]").forEach((node) => node.onclick = () => this._adjustCrop(node.dataset.cropCommand));
    this.shadowRoot.querySelector("[data-crop-window]")?.addEventListener("pointerdown", (event) => { if (!event.target.dataset.cropResize) this._dragCrop(event, false); });
    this.shadowRoot.querySelector("[data-crop-resize]")?.addEventListener("pointerdown", (event) => { event.stopPropagation(); this._dragCrop(event, true); });
    this.shadowRoot.querySelectorAll("[data-related-query]").forEach((node) => node.onclick = () => { this._query = node.dataset.relatedQuery; this._closeModal(); this._loadGallery(); });
    this.shadowRoot.querySelectorAll("[data-related-source]").forEach((node) => node.onclick = () => { this._closeModal(); this._setSource(node.dataset.relatedSource); });
    this.shadowRoot.querySelectorAll("[data-related-frame]").forEach((node) => node.onclick = async () => { this._closeModal(); await this._selectFrame(node.dataset.relatedFrame); this._openDetail(detail.source, detail.itemId, null); });
  }

  async _toggleDetailFavorite() {
    const detail = this._detail;
    if (!detail || this._favoriteBusy) return;
    this._favoriteBusy = true;
    this._renderDetailModal();
    try {
      const action = detail.favorite ? "unfavorite" : "favorite";
      const data = await this._artAction(action, detail.source, detail.itemId, null, { ...this._detailOptions, quiet: true });
      if (data?.deleted) {
        this._closeModal();
        await Promise.all([this._loadSources(), this._loadGallery(true), this._loadPlaylists()]);
        this._notify("Removed from favorites.");
        return;
      }
      if (data?.item) Object.assign(detail, data.item);
      detail.favorite = action === "favorite";
      this._galleryLoadedAt = 0;
      await this._loadSources();
      if (this._selectedSource === "saved" && this._selectedBrowseId === "favorites") await this._loadGallery(true);
    } catch (error) {
      this._notify(this._friendlyError(error), { error: true });
    } finally {
      this._favoriteBusy = false;
      if (this._detail) this._renderDetailModal();
    }
  }

  async _deleteSavedPicture(detail) {
    if (!confirm(`Remove ${detail.title} from your library?`)) return;
    try {
      await this._api(`library/image/${encodeURIComponent(detail.itemId)}`, { method: "DELETE" });
      this._closeModal();
      this._galleryLoadedAt = 0;
      await Promise.all([this._loadGallery(), this._loadPlaylists(), this._loadPlayer(false)]);
      this._notify("Removed from your library.");
    } catch (error) {
      this._notify(this._friendlyError(error), { error: true });
    }
  }

  _cropKey(source, itemId, frameId) { return `${frameId}:${source}:${itemId}`; }

  _frameRatio(frame) {
    if (!frame?.width || !frame?.height) return 4 / 3;
    return [90, 270].includes(frame.rotation) ? frame.height / frame.width : frame.width / frame.height;
  }

  _frameShape(frame) { const ratio = this._frameRatio(frame); return ratio > 1.08 ? "landscape" : ratio < .92 ? "portrait" : "square"; }

  _fitDifference(item, frame) { return Math.abs(((item.width || 4) / (item.height || 3)) / this._frameRatio(frame) - 1); }

  _defaultCrop(detail, frame) {
    const sourceRatio = (detail.width || 4) / (detail.height || 3);
    const normalizedRatio = this._frameRatio(frame) / sourceRatio;
    if (normalizedRatio <= 1) return [(1 - normalizedRatio) / 2, 0, (1 + normalizedRatio) / 2, 1];
    const height = 1 / normalizedRatio;
    return [0, (1 - height) / 2, 1, (1 + height) / 2];
  }

  _cropStyle(crop) { return `left:${crop[0] * 100}%;top:${crop[1] * 100}%;width:${(crop[2] - crop[0]) * 100}%;height:${(crop[3] - crop[1]) * 100}%`; }

  _setDetailCrop(crop, render = true) {
    this._detailOptions.crop = crop.map((value) => Math.max(0, Math.min(1, value)));
    this._cropDrafts.set(this._cropKey(this._detail.source, this._detail.itemId, this._selectedFrameId), this._detailOptions.crop);
    if (render) this._renderDetailModal();
  }

  _adjustCrop(command) {
    if (command === "reset") return this._setDetailCrop(this._defaultCrop(this._detail, this._frame));
    const [x0,y0,x1,y1] = this._detailOptions.crop;
    if (command === "centre") return this._setDetailCrop([(1 - (x1 - x0)) / 2, (1 - (y1 - y0)) / 2, (1 + (x1 - x0)) / 2, (1 + (y1 - y0)) / 2]);
    const currentWidth = x1 - x0, currentHeight = y1 - y0;
    const scale = command === "in" ? .88 : Math.min(1.12, 1 / currentWidth, 1 / currentHeight);
    const width = currentWidth * scale, height = currentHeight * scale;
    this._setDetailCrop([.5 - width / 2, .5 - height / 2, .5 + width / 2, .5 + height / 2]);
  }

  _dragCrop(event, resize) {
    const target = event.currentTarget;
    const stage = target.closest(".crop-stage");
    const windowNode = stage.querySelector("[data-crop-window]");
    const original = [...this._detailOptions.crop];
    const startX = event.clientX, startY = event.clientY;
    target.setPointerCapture(event.pointerId);
    const move = (next) => {
      const dx = (next.clientX - startX) / stage.clientWidth, dy = (next.clientY - startY) / stage.clientHeight;
      let crop;
      if (resize) {
        const normalizedRatio = this._frameRatio(this._frame) / ((this._detail.width || 4) / (this._detail.height || 3));
        let width = Math.max(.12, Math.min(1 - original[0], original[2] - original[0] + dx));
        let height = width / normalizedRatio;
        if (height > 1 - original[1]) { height = 1 - original[1]; width = height * normalizedRatio; }
        crop = [original[0], original[1], original[0] + width, original[1] + height];
      } else {
        const width = original[2] - original[0], height = original[3] - original[1];
        const x = Math.max(0, Math.min(1 - width, original[0] + dx));
        const y = Math.max(0, Math.min(1 - height, original[1] + dy));
        crop = [x, y, x + width, y + height];
      }
      this._setDetailCrop(crop, false);
      windowNode.style.cssText = this._cropStyle(crop);
    };
    const up = () => { target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", up); target.removeEventListener("pointercancel", up); this._renderDetailModal(); };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", up);
    target.addEventListener("pointercancel", up);
  }

  async _saveAsPlaylist(name, items) {
    const value = prompt("Playlist name", name);
    if (!value) return;
    try {
      const playlist = await this._api("playlists", this._json({ name: value }));
      const selected = items.slice(0, 50);
      let added = 0;
      let failure = null;
      for (const item of selected) {
        try {
          await this._artAction("add_playlist", item.source, item.id, playlist.id, { quiet: true });
          added += 1;
        } catch (error) { failure = error; }
      }
      await this._loadPlaylists();
      const partial = added !== selected.length;
      this._notify(partial ? `Added ${added} of ${selected.length} to ${playlist.name}. ${this._friendlyError(failure)}` : `Added to ${playlist.name}.`, { error: partial, action: "Open", callback: () => this._navigate(`/playlists/${encodeURIComponent(playlist.id)}`) });
    } catch (error) { this._notify(this._friendlyError(error), { error: true }); }
  }

  async _uploadFiles(files) {
    if (!files.length) return;
    this._uploads = files.map((file) => ({ file, status: "Uploading" }));
    this._showUploads();
    for (const upload of this._uploads) {
      const form = new FormData(); form.append("file", upload.file, upload.file.name);
      try {
        const response = await this._hass.fetchWithAuth(`${API}/library/upload`, { method: "POST", body: form });
        const body = await response.json();
        if (!response.ok) throw new Error(body.message || response.statusText);
        upload.status = `Saved · ${body.width} × ${body.height}`;
      } catch (error) { upload.status = this._friendlyError(error); upload.error = true; }
      this._showUploads();
    }
    this._galleryLoadedAt = 0;
    await this._loadGallery();
  }

  _showUploads() {
    this._openModal(`Uploading ${this._uploads.length} pictures`, `<div>${this._uploads.map((upload) => `<div class="upload-row"><ha-icon icon="mdi:${upload.error ? "alert-circle-outline" : upload.status.startsWith("Saved") ? "check" : "image-outline"}"></ha-icon><div class="row-copy"><b>${h(upload.file.name)}</b><span class="${upload.error ? "danger" : ""}">${h(upload.status)}</span></div></div>`).join("")}</div>`, this._uploads.every((upload) => upload.status !== "Uploading") ? `<span class="spacer"></span><button class="btn primary" data-close-modal>Done</button>` : "");
    this.shadowRoot.querySelectorAll("[data-close-modal]").forEach((node) => node.onclick = () => this._closeModal());
  }

  async _playerAction(action) {
    try { this._player = await this._api("player/control", this._json({ entry_id: this._selectedFrameId, action })); this._menu = null; this._render(); }
    catch (error) { this._notify(this._friendlyError(error), { error: true }); }
  }

  async _queueAction(body) {
    try {
      this._player = await this._api("player/queue", this._json({ entry_id: this._selectedFrameId, ...body }));
      const message = body.action === "clear" ? "Queue cleared." : body.action === "remove" ? "Removed from queue." : body.action === "reorder" ? "Queue reordered." : null;
      if (message) this._notify(message); else this._render();
    }
    catch (error) { this._notify(this._friendlyError(error), { error: true }); await this._loadPlayer(); }
  }

  _toggleQueue() {
    this._queueOpen = !this._queueOpen;
    if (!this._queueOpen && this._menu === "interval") this._menu = null;
    this._render();
    if (this._queueOpen) this.shadowRoot.querySelector(".queue-sheet")?.focus();
    else this.shadowRoot.querySelector("[data-player] [data-queue-toggle]")?.focus();
  }

  _moveQueue(section, index, direction) {
    const items = section === "queue" ? [...(this._player.hand_queue || [])] : [...(this._player.playlist?.items || [])];
    const target = direction === "top" ? 0 : direction === "bottom" ? items.length - 1 : direction === "up" ? index - 1 : index + 1;
    if (target < 0 || target >= items.length) return;
    [items[index], items[target]] = [items[target], items[index]];
    this._queueAction({ action: "reorder", section, ordered_ids: items.map((item) => item.id) });
  }

  _reorderQueue(section, from, to) {
    if (from === to) return;
    const items = section === "queue" ? [...(this._player.hand_queue || [])] : [...(this._player.playlist?.items || [])];
    const [item] = items.splice(from, 1); items.splice(to, 0, item);
    this._queueAction({ action: "reorder", section, ordered_ids: items.map((candidate) => candidate.id) });
  }

  _stepQueueSize(direction) {
    let index = QUEUE_SNAPS.reduce((best, value, current) => Math.abs(value - this._queueHeight) < Math.abs(QUEUE_SNAPS[best] - this._queueHeight) ? current : best, 0);
    index += direction === "larger" ? 1 : -1;
    this._queueHeight = QUEUE_SNAPS[Math.max(0, Math.min(QUEUE_SNAPS.length - 1, index))];
    this._render();
  }

  _dragQueueSheet(event) {
    const target = event.currentTarget;
    const sheet = target.closest(".queue-sheet");
    const startY = event.clientY, startHeight = this._queueHeight;
    this._queueDragging = true; sheet.classList.add("dragging"); target.setPointerCapture(event.pointerId);
    const move = (next) => { this._queueHeight = Math.max(180, Math.min(window.innerHeight - 120, startHeight + startY - next.clientY)); sheet.style.setProperty("--queue-height", `${this._queueHeight}px`); };
    const up = () => { target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", up); target.removeEventListener("pointercancel", up); this._queueDragging = false; sheet.classList.remove("dragging"); this._queueHeight = QUEUE_SNAPS.reduce((best, value) => Math.abs(value - this._queueHeight) < Math.abs(best - this._queueHeight) ? value : best, QUEUE_SNAPS[0]); this._render(); };
    target.addEventListener("pointermove", move); target.addEventListener("pointerup", up); target.addEventListener("pointercancel", up);
  }

  async _createPlaylist() {
    const name = prompt("Playlist name", "New playlist"); if (!name) return;
    try { const playlist = await this._api("playlists", this._json({ name })); await this._loadPlaylists(); this._navigate(`/playlists/${encodeURIComponent(playlist.id)}`); }
    catch (error) { this._notify(this._friendlyError(error), { error: true }); }
  }

  async _playPlaylist(id) {
    try { await this._api(`playlists/${encodeURIComponent(id)}/control`, this._json({ action: "play", entry_id: this._selectedFrameId })); await Promise.all([this._loadPlaylists(), this._loadPlayer(false)]); this._render(); }
    catch (error) { this._notify(this._friendlyError(error), { error: true }); }
  }

  _playlistMenu(id) {
    const playlist = this._playlists.find((item) => item.id === id) || this._playlist;
    this._openModal(playlist?.name || "Playlist", `<div class="queue-list"><button class="queue-row" data-playlist-edit="rename">Rename</button><button class="queue-row" data-playlist-edit="duplicate">Duplicate</button><button class="queue-row danger" data-playlist-edit="delete">Delete</button></div>`);
    this.shadowRoot.querySelectorAll("[data-playlist-edit]").forEach((node) => node.onclick = () => this._editPlaylist(id, node.dataset.playlistEdit));
  }

  async _editPlaylist(id, action) {
    this._closeModal();
    try {
      if (action === "delete") { if (!confirm("Delete this playlist?")) return; await this._api(`playlists/${encodeURIComponent(id)}`, { method: "DELETE" }); this._navigate("/playlists"); return; }
      const name = action === "rename" ? prompt("Playlist name", this._playlist?.name || "") : null;
      if (action === "rename" && name === null) return;
      const playlist = await this._api(`playlists/${encodeURIComponent(id)}`, this._json(action === "rename" ? { action, name } : { action }));
      await this._loadPlaylists(); this._navigate(`/playlists/${encodeURIComponent(playlist.id)}`);
    } catch (error) { this._notify(this._friendlyError(error), { error: true }); }
  }

  _moveSlide(index, direction) { this._reorderSlides(index, direction === "top" ? 0 : direction === "bottom" ? this._playlist.slides.length - 1 : direction === "up" ? index - 1 : index + 1); }

  async _reorderSlides(from, to) {
    if (!this._playlist || from === to || to < 0 || to >= this._playlist.slides.length) return;
    const slides = [...this._playlist.slides]; const [slide] = slides.splice(from, 1); slides.splice(to, 0, slide); this._playlist.slides = slides; this._render();
    try { const data = await this._api(`playlists/${encodeURIComponent(this._playlist.id)}/slides`, this._json({ action: "reorder", ordered_ids: slides.map((item) => item.id) })); this._playlist = data.playlist; this._render(); }
    catch (error) { this._notify(this._friendlyError(error), { error: true }); await this._loadPlaylist(this._playlist.id); this._render(); }
  }

  async _removeSlide(id) {
    try { const data = await this._api(`playlists/${encodeURIComponent(this._playlist.id)}/slides`, this._json({ action: "remove", slide_id: id })); this._playlist = data.playlist; this._notify(`Removed from ${this._playlist.name}.`, { action: "Undo", callback: () => this._undoRemove(data.undo_token) }); this._render(); }
    catch (error) { this._notify(this._friendlyError(error), { error: true }); }
  }

  async _undoRemove(token) { const data = await this._api(`playlists/${encodeURIComponent(this._playlist.id)}/slides`, this._json({ action: "undo", undo_token: token })); this._playlist = data.playlist; this._render(); }

  _slideSettings(id) {
    const slide = this._playlist.slides.find((item) => item.id === id);
    this._openModal("Slide settings", `<div class="field"><label>Fit</label><select id="slide-fit"><option value="cover" ${slide.fit === "cover" ? "selected" : ""}>Cover</option><option value="contain" ${slide.fit === "contain" ? "selected" : ""}>Contain</option></select></div><div class="field"><label>Tone</label><select id="slide-tone">${["soft","balanced","vivid"].map((tone) => `<option value="${tone}" ${slide.tone === tone ? "selected" : ""}>${tone}</option>`).join("")}</select></div><div class="field"><label>Overlays</label><select id="slide-overlays"><option value="inherit" ${slide.overlays === "inherit" ? "selected" : ""}>Inherit from ${h(this._frame?.name || "frame")}</option><option value="none" ${slide.overlays === "none" ? "selected" : ""}>None</option></select></div>`, `<span class="spacer"></span><button class="btn primary" data-save-slide>Save</button>`);
    this.shadowRoot.querySelector("[data-save-slide]").onclick = async () => { try { const data = await this._api(`playlists/${encodeURIComponent(this._playlist.id)}/slides`, this._json({ action: "settings", slide_id: id, fit: this.shadowRoot.getElementById("slide-fit").value, tone: this.shadowRoot.getElementById("slide-tone").value, overlays: this.shadowRoot.getElementById("slide-overlays").value })); this._playlist = data.playlist; this._closeModal(); this._render(); } catch (error) { this._notify(this._friendlyError(error), { error: true }); } };
  }

  _changePlaylist() { this._openModal("Change playlist", `<div class="queue-list">${this._playlists.map((playlist) => `<button class="queue-row" data-change-to="${h(playlist.id)}">${h(playlist.name)}${playlist.id === this._player?.playlist_id ? `<span class="spacer"></span><span class="counter">current</span>` : ""}</button>`).join("")}</div>`); this.shadowRoot.querySelectorAll("[data-change-to]").forEach((node) => node.onclick = () => { this._closeModal(); this._playPlaylist(node.dataset.changeTo); }); }
  async _toggleShuffle() { if (!this._player?.playlist_id) return; try { await this._api(`playlists/${encodeURIComponent(this._player.playlist_id)}/control`, this._json({ action: "shuffle", shuffle: !this._player.playlist.shuffle })); await this._loadPlayer(); } catch (error) { this._notify(this._friendlyError(error), { error: true }); } }
  async _setInterval(interval) { if (!this._player?.playlist_id) return; try { await this._api(`playlists/${encodeURIComponent(this._player.playlist_id)}/control`, this._json({ action: "interval", interval })); this._menu = null; await this._loadPlayer(); } catch (error) { this._notify(this._friendlyError(error), { error: true }); } }

  async _openOverlays() {
    this._menu = null; this._overlaysOpen = true; this._overlayData = null; this._render();
    try { this._overlayData = await this._api(`overlays?entry_id=${encodeURIComponent(this._selectedFrameId)}`); this._overlayDraft = structuredClone(this._overlayData.overlays || []); this._overlaySaved = JSON.stringify(this._overlayDraft); this._selectedOverlayId = this._overlayDraft[0]?.id || null; this._selectedPreview = this._overlayData.preview_thumbnails?.[0]?.id || null; this._render(); }
    catch (error) { this._overlaysOpen = false; this._notify(this._friendlyError(error), { error: true }); }
  }

  _updateOverlay(id, mutate, render = true) { const overlay = this._overlayDraft.find((item) => item.id === id); if (!overlay) return; mutate(overlay); if (render) this._render(); }
  _updateSelected(mutate, render = true) { this._updateOverlay(this._selectedOverlayId, mutate, render); }

  _setAnchor(anchor) {
    const dims = { s: [3,1], m: [5,2], l: [5,3] };
    this._updateSelected((overlay) => { overlay.anchor = anchor; [overlay.w, overlay.h] = dims[overlay.size || "m"]; const col = anchor.includes("left") ? 0 : anchor.includes("right") ? 12 - overlay.w : Math.floor((12 - overlay.w) / 2); const row = anchor.includes("top") ? 0 : anchor.includes("bottom") ? 8 - overlay.h : Math.floor((8 - overlay.h) / 2); overlay.x = col; overlay.y = row; });
  }

  _setOverlaySize(size) { const dims = { s: [3,1], m: [5,2], l: [5,3] }; this._updateSelected((overlay) => { overlay.size = size; [overlay.w, overlay.h] = dims[size]; overlay.x = Math.min(overlay.x, 12 - overlay.w); overlay.y = Math.min(overlay.y, 8 - overlay.h); }); }

  _dragOverlay(event, id, resize) {
    const target = event.currentTarget;
    const canvas = target.closest(".canvas"); const overlay = this._overlayDraft.find((item) => item.id === id); if (!overlay) return; this._selectedOverlayId = id;
    canvas.classList.add("dragging");
    const startX = event.clientX, startY = event.clientY, original = { ...overlay }; target.setPointerCapture(event.pointerId);
    const move = (next) => { const dx = Math.round((next.clientX - startX) / canvas.clientWidth * 12); const dy = Math.round((next.clientY - startY) / canvas.clientHeight * 8); if (resize) { overlay.w = Math.max(1, Math.min(12 - overlay.x, original.w + dx)); overlay.h = Math.max(1, Math.min(8 - overlay.y, original.h + dy)); } else { overlay.x = Math.max(0, Math.min(12 - overlay.w, original.x + dx)); overlay.y = Math.max(0, Math.min(8 - overlay.h, original.y + dy)); } const box = canvas.querySelector(`[data-overlay-box="${CSS.escape(id)}"]`); if (box) { box.style.left = `${overlay.x / 12 * 100}%`; box.style.top = `${overlay.y / 8 * 100}%`; box.style.width = `${overlay.w / 12 * 100}%`; box.style.height = `${overlay.h / 8 * 100}%`; } };
    const up = () => { target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", up); target.removeEventListener("pointercancel", up); canvas.classList.remove("dragging"); this._render(); };
    target.addEventListener("pointermove", move); target.addEventListener("pointerup", up); target.addEventListener("pointercancel", up);
  }

  _newOverlay(type) {
    const id = crypto.randomUUID().replaceAll("-", ""); const entities = this._overlayData.entities || {};
    const sensor = entities.sensor?.[0] || "sensor.temperature";
    const options = type === "clock" ? { format: "%H:%M" } : type === "date" ? { format: "%A, %-d %B" } : type === "todo" ? { entity: entities.todo?.[0] || "todo.todo", max_items: 6, show_title: true } : type === "weather" ? { entity: entities.weather?.[0] || "weather.home", view: "current" } : type === "agenda" ? { entities: [entities.calendar?.[0] || "calendar.home"], days: 3, max_events: 6 } : type === "stat" ? { entity: sensor, precision: 1, trend: false } : type === "gauge" ? { entity: sensor, min: 0, max: 100, thresholds: [] } : type === "text" ? { template: "Text", align: "left", size: "m" } : type === "caption" ? { fields: ["title", "artist", "source"] } : type === "entities" ? { entities: [sensor], max_rows: 6 } : type === "chart" ? { entities: [sensor], hours: 24, style: "line" } : {};
    const geometry = { clock:["top_left","s"], date:["top_left","s"], todo:["bottom_right","l"], agenda:["right","l"], weather:["bottom_left","m"], stat:["top_right","s"], entities:["right","m"], chart:["bottom","l"], gauge:["bottom_right","m"], text:["bottom","m"], caption:["bottom_left","m"] }[type];
    const overlay = { id, type, enabled: true, options, anchor: geometry[0], size: geometry[1], x: 0, y: 0, w: 1, h: 1, plate: "panel", plate_color: "white", text_size: "m", visibility: { mode: "always", from: "00:00", to: "23:59", days: [], entity: null, state: "on", hide_when_empty: true } };
    this._positionOverlay(overlay);
    return overlay;
  }

  _positionOverlay(overlay) {
    const dims = { s: [3,1], m: [5,2], l: [5,3] };
    [overlay.w, overlay.h] = dims[overlay.size || "m"];
    overlay.x = overlay.anchor.includes("left") ? 0 : overlay.anchor.includes("right") ? 12 - overlay.w : Math.floor((12 - overlay.w) / 2);
    overlay.y = overlay.anchor.includes("top") ? 0 : overlay.anchor.includes("bottom") ? 8 - overlay.h : Math.floor((8 - overlay.h) / 2);
  }

  _applyPreset(name) {
    if (OVERLAY_TYPES.includes(name)) { const overlay = this._newOverlay(name); this._overlayDraft.push(overlay); this._selectedOverlayId = overlay.id; this._render(); return; }
    const presets = {
      info: [["clock","bottom_left"],["weather","bottom"],["date","bottom_right"]],
      side: [["agenda","right"],["stat","top_right"]],
      morning: [["clock","top_left"],["weather","top_right"],["agenda","bottom"]],
    };
    for (const [type, anchor] of presets[name] || []) { const overlay = this._newOverlay(type); overlay.anchor = anchor; if (name === "morning") overlay.visibility = { ...overlay.visibility, mode: "times", from: "06:00", to: "09:00", days: ["mon","tue","wed","thu","fri"] }; this._positionOverlay(overlay); if (name === "morning" && type === "agenda") { overlay.w = 10; overlay.x = 1; } this._overlayDraft.push(overlay); }
    this._selectedOverlayId = this._overlayDraft.at(-1)?.id || null; this._render();
  }

  async _saveOverlays() { try { const entryId = this._selectedFrameId; this._overlayData = await this._api("overlays", this._json({ action: "save", entry_id: entryId, overlays: this._overlayDraft })); this._overlayDraft = structuredClone(this._overlayData.overlays || []); const overlays = structuredClone(this._overlayDraft); const frameName = this._frames.find((frame) => frame.id === entryId)?.name || this._frame.name; this._overlaySaved = JSON.stringify(this._overlayDraft); this._overlaysOpen = false; await this._loadPlayer(false); this._notify("Overlays saved. They will appear on the next picture change.", { action: "Apply now", callback: () => this._applyOverlaysNow(entryId, overlays, frameName) }); this._render(); } catch (error) { this._notify(this._friendlyError(error), { error: true }); } }
  async _applyOverlaysNow(entryId, overlays, frameName) { try { await this._api("overlays", this._json({ action: "save", entry_id: entryId, overlays, apply_now: true })); this._notify(`Sending to ${frameName}. The panel takes about 30 seconds.`); } catch (error) { this._notify(this._friendlyError(error), { error: true }); } }
  _overlaysDirty() { return JSON.stringify(this._overlayDraft) !== this._overlaySaved; }
  _closeOverlayEditor() { this._overlaysOpen = false; this._overlayData = null; this._overlayDraft = []; this._overlaySaved = "[]"; }
  _discardOverlays() { this._closeOverlayEditor(); this._render(); }
  _requestCloseOverlays() { if (this._overlaysDirty() && !confirm("Discard unsaved overlay changes?")) return; this._discardOverlays(); }
  async _copyOverlays() { const target = this._frames.find((frame) => frame.id !== this._selectedFrameId); if (!target) return; if (!confirm(`Replace overlays on ${target.name}?`)) return; try { await this._api("overlays", this._json({ action: "copy", entry_id: this._selectedFrameId, target_entry_id: target.id })); this._notify(`Copied overlays to ${target.name}.`); } catch (error) { this._notify(this._friendlyError(error), { error: true }); } }

  _openModal(title, body, actions = "", options = {}) { this._modal = { title, body, actions, ...options }; this._render(); queueMicrotask(() => this.shadowRoot.querySelector(".dialog button, .dialog input, .dialog select")?.focus()); }
  _closeModal() { this._detailGeneration += 1; this._modal = null; this._detail = null; this._favoriteBusy = false; this._render(); this._modalTrigger?.focus?.(); this._modalTrigger = null; }

  _trapModalFocus(event) {
    const focusable = [...this.shadowRoot.querySelectorAll(".dialog button:not([disabled]), .dialog input:not([disabled]), .dialog select:not([disabled]), .dialog textarea:not([disabled]), .dialog a[href]")];
    if (!focusable.length) return;
    const first = focusable[0], last = focusable.at(-1), active = this.shadowRoot.activeElement;
    if (event.shiftKey && active === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
  }

  _notify(text, { error = false, action = null, callback = null } = {}) {
    clearTimeout(this._toastTimer); this._toast = { text, error, action, callback }; this._render();
    if (!error) this._toastTimer = setTimeout(() => { this._toast = null; this._render(); }, action === "Undo" ? 8000 : 4000);
  }

  _friendlyError(error) {
    const message = error?.message || String(error);
    if (/too large|buffer/i.test(message)) return "That picture is too large for the frame buffer.";
    if (/upload|answer|connect|unreachable/i.test(message)) return `${this._frame?.name || "The frame"} did not answer. Check the frame before trying again.`;
    return message;
  }

  _formatInterval(seconds) {
    if (!seconds) return ""; if (seconds < 3600) return `${Math.round(seconds / 60)} min`; if (seconds === 86400) return "once a day"; const hours = seconds / 3600; return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  }
  _lastSeenMinutes(timestamp) { return Math.max(0, Math.round((Date.now() / 1000 - Number(timestamp || Date.now() / 1000)) / 60)); }
  _timeLeft(seconds) { if (seconds == null) return ""; if (seconds < 60) return "less than a minute left"; if (seconds < 3600) return `${Math.ceil(seconds / 60)} min left`; const hours = Math.floor(seconds / 3600), minutes = Math.ceil((seconds % 3600) / 60); return `${hours} h${minutes ? ` ${minutes} min` : ""} left`; }

  _safeHref(value) {
    if (!value) return null;
    try {
      const url = new URL(value, window.location.origin);
      return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    } catch (_error) { return null; }
  }

  _imageAttrs(url, alt) {
    if (!url) return `alt="${h(alt)}"`;
    if (url.startsWith("/api/")) {
      const signed = this._cachedSignedPath(url);
      return signed ? `src="${h(signed)}" alt="${h(alt)}"` : `data-path="${h(url)}" alt="${h(alt)}"`;
    }
    return `src="${h(url)}" alt="${h(alt)}"`;
  }

  _cachedSignedPath(path) {
    const cached = this._signedPaths.get(path);
    if (!cached) return null;
    if (cached.expiresAt <= Date.now()) { this._signedPaths.delete(path); return null; }
    return cached.path;
  }

  async _signImages() {
    const images = [...this.shadowRoot.querySelectorAll("img")];
    for (const img of images) {
      img.addEventListener("error", () => img.classList.add("image-failed"), { once: true });
      if (img.complete && img.currentSrc && !img.naturalWidth) img.classList.add("image-failed");
    }
    this._imageObserver?.disconnect();
    const nodes = images.filter((img) => img.matches("[data-path]:not([data-signing])"));
    if (!("IntersectionObserver" in window)) {
      await Promise.all(nodes.map((img) => this._signImage(img)));
      return;
    }
    this._imageObserver ||= new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        this._imageObserver.unobserve(entry.target);
        this._signImage(entry.target);
      }
    }, { rootMargin: "600px 0px" });
    for (const img of nodes) {
      const cached = this._cachedSignedPath(img.dataset.path);
      if (cached) img.src = cached;
      else this._imageObserver.observe(img);
    }
  }

  async _signImage(img) {
    const path = img.dataset.path;
    if (!path || img.dataset.signing) return;
    img.dataset.signing = "true";
    const cached = this._cachedSignedPath(path);
    if (cached) { if (img.isConnected) img.src = cached; return; }
    let pending = this._signedPathPromises.get(path);
    if (!pending) {
      pending = this._hass.callWS({ type: "auth/sign_path", path, expires: 3600 })
        .then((result) => {
          this._signedPaths.set(path, { path: result.path, expiresAt: Date.now() + 55 * 60 * 1000 });
          if (this._signedPaths.size > SIGNED_PATH_LIMIT) this._signedPaths.delete(this._signedPaths.keys().next().value);
          return result.path;
        })
        .finally(() => this._signedPathPromises.delete(path));
      this._signedPathPromises.set(path, pending);
    }
    try {
      const signed = await pending;
      if (img.isConnected && img.dataset.path === path) img.src = signed;
    } catch (_error) {
      delete img.dataset.signing;
    }
  }
}

customElements.define("fraimic-panel-v2", FraimicPanel);
