# Changelog

## 1.1.2 — 2026-10-19

- Preserve sparse metadata track definitions with zero samples when the chosen
  clip contains no media from that track. Do not stretch out-of-range metadata
  into the clip; keep video/audio absence checks in place.
- Add regression coverage for empty metadata tracks, re-trimming, and delayed
  metadata. Keep copied video/audio bytes and per-frame timing unchanged.
- Remove unused Qt PDF/virtual-keyboard plugins and QML/Quick dependencies
  from the portable build.
- Publish the application source under the existing proprietary terms, with an
  explicit GitHub viewing/forking carve-out. Keep bundled binary assets private
  until their separate corresponding-source obligations are completed.

## 1.1.1 — 2026-10-19

- Accept the optional QuickTime `cslg` timing summary when opening recordings and
  omit it from exported clips. Keep the actual per-frame timing tables.
- Interpret signed QuickTime version-zero composition offsets correctly.
- Preserve Apple sample-group associations when a cut crosses a repeated
  pattern, including implicit trailing groups.
- Add synthetic timing and sample-group regression fixtures.

## 1.1.0 — 2026-10-18

- Accept MOV drops across the preview, clip list, timeline, text fields, and window.
- Add a visible drop area with feedback while a valid MOV is dragged over it.
- Force copy semantics so Explorer is never asked to move the source.
- Reject non-files, unsupported formats, multiple files, and drops during export.
- Add regression checks and a native-preview drop to the executable smoke test.
- Identify Shardul Narvekar in Windows file properties and ownership notices.
- Add proprietary terms for this version, preserving third-party and prior rights.

## 1.0.0 — 2026-10-18

- Initial portable Windows application with multiple clip selection.
- Direct MOV sample copying, supported-track retention, and byte verification.
- Playback, keyboard controls, keyframe snapping, cancellation, and overwrite protection.
