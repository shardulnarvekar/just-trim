# Validation record — 1.1.2

Checked on Windows on 19 October 2026.

- Eighteen regression tests passed, covering drag-and-drop, signed QuickTime
  composition offsets, ISO unsigned offsets, optional-summary omission,
  byte-preserving export, and compact sample groups. The group tests check every
  nonempty slice of an 18-sample pattern at all four supported index widths.
  Five additional checks cover sparse metadata before/after its active interval,
  an overlapping interval, empty-track re-trimming, and preserved audio guards.
- The reported 2.91 GB iPhone recording opened with all nine tracks. Beginning,
  middle, and ending clips exported with verified copied bytes and nine tracks.
  FFmpeg decoded video and stereo audio with `-xerror`; the first 25 decoded
  video frames of each clip matched its source cut point. Re-trimming passed.
  Source size and modification time remained unchanged.
- Seven additional export/decode/pixel comparisons passed again on 1.1.2: H.264 with B-frames,
  HEVC, silent video, ProRes/PCM, a prior nine-track iPhone clip, and two iPhone
  recordings with implicit trailing sample groups.
- The frozen 1.1.2 Windows executable passed its native-preview drag-and-drop,
  playback, seek, and two-clip batch-export smoke test on the affected recording.
  It decoded five preview frames and retained all nine tracks in both exports.
  This was the rebuilt package with unused optional Qt plugins removed.
- An index-only scan opened 236 local MOV recordings, including 42 with `cslg`.
  Cut plans at the beginning, middle, and end succeeded for all 236 recordings.
  This scan did not decode or export every recording.
- The formerly failing 2.25-second recording has a metadata track ending after
  0.067 seconds. Beginning/middle/end exports now pass byte verification and
  independent video/stereo-audio decoding with all nine track definitions kept.
  Later cuts have a zero-sample, zero-duration metadata track, because that
  interval contains no metadata samples. Their first 25/25/17 video frames match
  the source; all three re-trims also pass. Source size/mtime stayed unchanged.
- The earlier 1.0 build passed 15 media/safety checks and 21 GUI checks.
  Version 1.1.0 added six drag-and-drop regression tests.

The drag tests inject Qt drag events, including into the native preview surface;
they are not a recording of a physical mouse drag from Explorer. Final package
integrity is checked by the packaging script and a SHA-256 file accompanies it.

Physical iPhone playback, Apple spatial-audio decoding, and future iOS
compatibility remain unverified. Private recordings, filenames, and test exports
are not included in the source repository or release archive.
