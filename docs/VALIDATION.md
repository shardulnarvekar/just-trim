# Validation record — 1.1.0

Checked on Windows on 18 October 2026.

- Six drag-and-drop regression tests passed. The tests cover the main window,
  child controls, the clip-list viewport, text fields, the top-level native
  window, and the native video surface. They also check Unicode paths, drag
  feedback, rejection while busy, invalid inputs, and copy-only semantics.
- The frozen Windows executable accepted a MOV drop on its native video surface.
- That drop opened the supplied 10 GB iPhone recording with all nine tracks.
- Preview decoded frames and sought past ten seconds.
- Two MOV clips exported successfully with their copied bytes verified and all
  nine tracks retained.
- The earlier 1.0 build passed 15 media/safety checks and 21 GUI checks. These
  included H.264, HEVC, ProRes/PCM, silent-video fixtures, cancellation, source
  protection, independent decoding, and decoded HDR frame comparisons. The
  sample-copying engine is unchanged in 1.1.0.

The drag tests inject Qt drag events, including into the native preview surface;
they are not a recording of a physical mouse drag from Explorer. Final package
integrity is checked by the packaging script and a SHA-256 file accompanies it.

Physical iPhone playback, Apple spatial-audio decoding, and future iOS
compatibility remain unverified. Private recordings and test clips are not
included in the source repository or release archive.
