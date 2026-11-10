# Fraimic 3.3

## Scheduled wakes for local frames

- On firmware 0.2.31 or newer, a frame on Local delivery can sleep between pictures and wake itself on a schedule. The queue's **Changes every** button becomes **Changes at**: pick up to four times a day, or an interval, and the weekdays. Each picture then changes at one of those wakes, and auto mode follows the same times. Queue rows show when each picture will appear.
- Times are picked on Home Assistant's clock. Frames keep their own time zone (usually US Eastern), so Home Assistant converts the times before writing them to the frame.
- At each wake Home Assistant sends the next picture and anything queued while the frame slept, then puts the frame back to sleep unless it is charging, even with keep-awake on.
- **Turn off wakes** goes back to the queue interval. A schedule set on the frame outside Home Assistant is left alone until you pick one here, and switching the frame to another delivery mode turns off a schedule set here.
- A repair appears after two missed wakes. Each wake needs the frame's internet time sync (UDP port 123) and its TCP check to `8.8.8.8` port 53, so a frame cut off from the internet must still be allowed both. See [Isolated networks and IoT VLANs](../README.md#isolated-networks-and-iot-vlans).

## AI art

- **Create** always opens to the prompt. Before an image service is set up it shows **Set up AI art**, which brings you back to Create with your text kept.
- The microphone button in Create dictates the prompt through an Assist pipeline and inserts the words at the cursor. It never creates a picture by itself. Browsers allow the microphone only over HTTPS and in the Home Assistant app.
- A menu next to **Create** picks the service and model for one picture, and your browser remembers it. The default service, used by the voice button and automations, stays as it is.
- **⋮ > AI art** sets up every service side by side, with a separate **Default service**. The Prompt section is now **Styles**, next to new **Rewrite** and **Speech** sections. Speech picks the dictation pipeline when more than one can do speech to text.

## Local backend (experimental)

- The frame's voice button has a new **Use Fraimic's AI** mode. The companion sends only the recording to Fraimic's own voice art and shows the picture it returns. The frame still never polls Fraimic, so it is never offered firmware. The picture also lands in your Fraimic gallery, where **Import creations** can copy it into the library. This needs the updated companion; see the [runbook](local-backend.md).

## Updating

Update through HACS or the Home Assistant Marketplace, restart Home Assistant, then reload the browser or companion-app page.

**Full changelog:** [v3.2.1…v3.3.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v3.2.1...v3.3.0)
