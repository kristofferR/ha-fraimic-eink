# Fraimic 3.0

## Voice creations in your library

- `fraimic.import_creations` copies the pictures you made by voice in the Fraimic app into the library's new **Creations** album. They work with favorites, crops, the queue and playlists like any other picture.
- Each creation keeps its transcript, style and creation date, shown in **Picture details**.
- The originals are stored in Home Assistant, so they keep working after Fraimic's download links expire or the frame stops using the Fraimic cloud. Run the import before moving a frame off the Fraimic cloud.
- Running it again adds only creations that aren't in the library yet. Nothing is shown on a frame or changed in your Fraimic account.

## A steadier frame

- Home Assistant now leaves the frame alone while it finishes drawing an upload. Restart, Sleep, Refresh and the next picture wait for the drawing to finish instead of interrupting it, and only the newest of several queued pictures is sent.
- Polls, refreshes and diagnostics skip the frame while an upload is in progress, since the frame can only answer one request at a time.
- If another Fraimic answers at a frame's address, Home Assistant no longer mixes its data into the wrong device. Setup also saves the frame's IP address instead of `fraimic.local`, which every frame claims.
- Uploads must be exactly the right size for the panel, and a damaged cached picture is redrawn instead of being sent.

## Clearer status and warnings

- Frame times are read in the frame's own time zone. A new **Frame UTC offset** sensor shows it, and a repair explains a mismatch with Home Assistant and when the 03:00 maintenance redraw really happens.
- A repair warns when the frame can't reach the internet time and DNS services it needs, even on a LAN-only network. The README has a new section on isolated networks and IoT VLANs.
- A repair warns when the frame keeps reporting a charging cable while its battery drains, which also stops it from sleeping.
- Several sensors are renamed to match what the frame reports: **Last/Next maintenance refresh**, **Voice recording enabled** and **Auto-update preference**.

## Fixes

- Diagnostics now remove the device key, account details, MAC addresses and private IP addresses, including inside frame log lines, and add Wi-Fi details for troubleshooting.
- The maintenance redraw is no longer mistaken for new content on the frame.
- `fraimic.update_album` checks that the frame's cloud proxy really saved the change, and re-reads the album when the reply is unclear.

## Updating

Update through HACS, restart Home Assistant, then reload the browser or companion-app page.

**Full changelog:** [v2.5.0…v3.0.0](https://github.com/kristofferR/ha-fraimic-eink/compare/v2.5.0...v3.0.0)
