/*
 * Fraimic Lovelace card: shows the frame's last-uploaded preview with status
 * chips and a shortcut to the Fraimic panel. Auto-registered by the
 * integration (no manual resource needed).
 *
 * Config:
 *   type: custom:fraimic-card
 *   entity: image.frame_preview          # required — the preview image entity
 *   title: Living room frame             # optional
 *   battery_entity: sensor.frame_battery # optional
 *   online_entity: binary_sensor.frame_online  # optional
 */

class FraimicCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity || !config.entity.startsWith("image.")) {
      throw new Error('fraimic-card needs "entity" set to the frame\'s preview image entity');
    }
    this._config = config;
    if (!this._root) {
      this._root = this.attachShadow({ mode: "open" });
      this._root.innerHTML = `
        <style>
          ha-card { overflow: hidden; }
          .imgwrap {
            background:
              repeating-conic-gradient(var(--secondary-background-color) 0% 25%, var(--card-background-color) 0% 50%)
              50% / 24px 24px;
            min-height: 120px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
          }
          img { width: 100%; display: block; }
          .placeholder { color: var(--secondary-text-color); padding: 40px 16px; font-size: 14px; }
          .footer {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 16px;
            flex-wrap: wrap;
          }
          .name { font-size: 15px; font-weight: 500; flex: 1; }
          .chip {
            font-size: 12px;
            padding: 2px 10px;
            border-radius: 12px;
            background: var(--secondary-background-color);
            color: var(--secondary-text-color);
          }
          .chip.offline { color: var(--error-color); }
          button {
            background: none;
            border: none;
            color: var(--primary-color);
            font: inherit;
            font-size: 13px;
            font-weight: 500;
            text-transform: uppercase;
            cursor: pointer;
            padding: 4px 8px;
          }
        </style>
        <ha-card>
          <div class="imgwrap" id="imgwrap"></div>
          <div class="footer">
            <div class="name" id="name"></div>
            <span class="chip" id="battery" hidden></span>
            <span class="chip" id="online" hidden></span>
            <button id="open">Fraimic</button>
          </div>
        </ha-card>
      `;
      this._root.getElementById("open").addEventListener("click", () => {
        history.pushState(null, "", "/fraimic");
        window.dispatchEvent(new CustomEvent("location-changed"));
      });
      this._root.getElementById("imgwrap").addEventListener("click", () => {
        const event = new CustomEvent("hass-more-info", {
          bubbles: true,
          composed: true,
          detail: { entityId: this._config.entity },
        });
        this.dispatchEvent(event);
      });
    }
  }

  set hass(hass) {
    if (!this._config) return;
    const state = hass.states[this._config.entity];
    const wrap = this._root.getElementById("imgwrap");
    const picture = state && state.attributes.entity_picture;
    const stamp = state ? state.state : "";
    if (picture && this._lastStamp !== stamp) {
      this._lastStamp = stamp;
      wrap.innerHTML = "";
      const img = document.createElement("img");
      img.src = picture;
      wrap.appendChild(img);
    } else if (!picture && !this._placeholderSet) {
      this._placeholderSet = true;
      wrap.innerHTML = '<div class="placeholder">Nothing uploaded yet</div>';
    }

    this._root.getElementById("name").textContent =
      this._config.title ||
      (state && state.attributes.friendly_name) ||
      this._config.entity;

    const battery = this._root.getElementById("battery");
    const batteryState = this._config.battery_entity && hass.states[this._config.battery_entity];
    battery.hidden = !batteryState;
    if (batteryState) battery.textContent = `🔋 ${batteryState.state}%`;

    const online = this._root.getElementById("online");
    const onlineState = this._config.online_entity && hass.states[this._config.online_entity];
    online.hidden = !onlineState;
    if (onlineState) {
      const isOn = onlineState.state === "on";
      online.textContent = isOn ? "Online" : "Offline";
      online.classList.toggle("offline", !isOn);
    }
  }

  getCardSize() {
    return 4;
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("image.") && id.includes("preview")
    );
    return { entity: entity || "image.frame_preview" };
  }
}

customElements.define("fraimic-card", FraimicCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "fraimic-card",
  name: "Fraimic Frame Card",
  description: "Preview of what a Fraimic e-ink frame is showing, with status and panel shortcut.",
  preview: true,
});
