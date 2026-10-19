# Validation record — 1.1.1

Checked on Windows on 19 October 2026.

- Thirteen regression tests passed, covering drag-and-drop, signed QuickTime
  composition offsets, ISO unsigned offsets, optional-summary omission,
  byte-preserving export, and compact sample groups. The group tests check every
  nonempty slice of an 18-sample pattern at all four supported index widths.
- The reported 2.91 GB iPhone recording opened with all nine tracks. Beginning,
  middle, and ending clips exported with verified copied bytes and nine tracks.
  FFmpeg decoded video and stereo audio with `-xerror`; the first 25 decoded
  video frames of each clip matched its source cut point. Re-trimming passed.
  Source size and modification time remained unchanged.
- Seven additional export/decode/pixel comparisons passed: H.264 with B-frames,
  HEVC, silent video, ProRes/PCM, a prior nine-track iPhone clip, and two iPhone
  recordings with implicit trailing sample groups.
- The frozen 1.1.1 Windows executable passed its native-preview drag-and-drop,
  playback, seek, and two-clip batch-export smoke test on the affected recording.
  It decoded 32 preview frames and retained all nine tracks in both exports.
- An index-only scan opened 236 local MOV recordings, including 42 with `cslg`.
  Cut plans at the beginning, middle, and end succeeded for 235 recordings.
  One 2.25-second recording has a metadata track ending after only 0.067 seconds;
  later cuts still stop because that track contains no media in the range.
  This scan did not decode or export every recording.
- The earlier 1.0 build passed 15 media/safety checks and 21 GUI checks.
  Version 1.1.0 added six drag-and-drop regression tests.

The drag tests inject Qt drag events, including into the native preview surface;
they are not a recording of a physical mouse drag from Explorer. Final package
integrity is checked by the packaging script and a SHA-256 file accompanies it.

Physical iPhone playback, Apple spatial-audio decoding, and future iOS
compatibility remain unverified. Private recordings, filenames, and test exports
are not included in the source repository or release archive.
