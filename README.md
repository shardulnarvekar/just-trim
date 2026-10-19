# Just Trim

A simple Windows application for cutting iPhone MOV recordings into separate
clips while copying the original compressed media samples.

**Project owner and maintainer: Shardul Narvekar** · **Version 1.1.1**

## Use it

1. Extract the entire `JustTrim-Windows.zip` archive.
2. Open `JustTrim-Windows/Just Trim.exe`. Keep `_internal` next to the executable.
3. Drag one `.mov` file from File Explorer onto the window, including the preview,
   the drop area, or the clip list. **Open MOV** works too.
4. Set the start and end, then click **Add clip**. Repeat for more clips.
5. Click **Export MOV clips** and select an output folder.

Every checked row exports as a separate MOV. Existing files are never overwritten.
The application reads the original file without changing or deleting it.
It requires Windows 10/11 x64; the packaged app needs no Python installation,
account, internet connection, or separately purchased playback codec.

## What it preserves

The exporter copies compressed samples directly rather than re-encoding. It keeps
supported audio and metadata tracks, sample descriptions, orientation, and HDR
information. Every export is reread and its copied sample bytes are verified
before it is published as a completed MOV.

The tested 10 GB iPhone recording has nine tracks, including HEVC/Dolby Vision,
stereo sound, Apple spatial audio, and metadata. All nine are retained. Preview
uses Qt's FFmpeg backend; export uses the app's direct QuickTime sample copier.

Version 1.1.1 also accepts recordings with an optional `cslg` timing summary.
Exports omit that summary while preserving the actual per-frame timing and
sample-group associations, including signed QuickTime composition offsets.

## Lossless cut boundaries and compatibility

Cuts expand to surrounding video keyframes. The **Actual export** line shows
the resulting times. This is not a frame-exact editor. MOV timing headers and
the media index are rebuilt for the shorter clip; the file as a whole changes.

Physical iPhone playback, Apple spatial-audio decoding, and Apple Photos editing
features have not been verified. Test a clip on your iPhone before deleting
irreplaceable originals. Windows preview colors may differ from an HDR display.

Supported inputs are self-contained MOVs with one video track and conventional
sample tables. Unsupported structures are rejected instead of silently dropping
tracks. Fragmented/encrypted MOVs, external references, multiple video tracks,
and complex slow-motion/edit timelines are outside this version's scope.
An export also stops if a track has no media in the selected range, to avoid
silently discarding that track.

## Controls

| Action | Control |
| --- | --- |
| Open a recording | Drop one MOV anywhere, or Ctrl+O |
| Play / pause | Space |
| Mark start / end | I / O |
| Add a clip | A |
| Seek about one frame | Left / Right |
| Seek one second | Ctrl+Left / Ctrl+Right |
| Seek a lossless boundary | Keyframe buttons |
| Adjust a range | Drag blue IN/OUT handles or type times |

Drops accept existing local MOV files only. Multiple files, directories, web
links, and drops during an export are rejected. A drop always uses copy semantics;
it never requests that Explorer move or delete the source. Opening another file
with clips selected retains the existing confirmation before clearing the list.

## Develop and build

Use Python 3.11 x64 on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist --workpath build "src\Just Trim.spec"
.\.venv\Scripts\python.exe scripts\package.py
```

The app is built into `dist/Just Trim`; the complete ZIP is created in `release/`.
The spec prevents an unrelated ICU DLL on PATH from contaminating the build.

For an opt-in executable test with a recording longer than 33 seconds:

```powershell
& '.\dist\Just Trim\Just Trim.exe' --self-test 'C:\Videos\sample.mov' 'smoke.json' 'smoke-clips'
```

This test opens the source through a drop on the native preview surface, plays,
seeks, exports two clips, verifies the copied samples, and checks retained tracks.
The source file is opened read-only. Use a new output directory for each run.

## Source layout

| File | Purpose |
| --- | --- |
| `src/main.py` | Controls, preview, timeline, and background tasks |
| `src/drop_support.py` | File drops across widgets and the native preview |
| `src/movcut.py` | Conservative MOV parser, sample copier, and verification |
| `src/selfcheck.py` | Opt-in packaged application smoke test |
| `tests/test_drop.py` | Drag-and-drop regression tests |
| `tests/test_mov_timing.py` | Timing and sample-group regression fixtures |
| `scripts/package.py` | Package runtime, source, documentation, and licenses |

## Ownership and licensing

Copyright (c) 2026 **Shardul Narvekar**. The original app material in this version
is proprietary; it is not offered under an open-source license. See
[LICENSE.txt](LICENSE.txt). This project was specified and directed by Shardul
Narvekar and developed with AI assistance. This notice does not claim that every
line was manually written or that the dependencies belong to the project owner.

Third-party components retain their own licenses. See
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt), [licenses/](licenses/), and
[ownership guidance](docs/OWNERSHIP.md). Earlier MIT grants, if any copies were
shared under them, are not revoked by this version's licensing change.

Keep this repository private for personal development. Before distributing the
bundled binary to other people, complete the corresponding-source and notices
requirements described in [DISTRIBUTION.md](docs/DISTRIBUTION.md).

Recordings, private test exports, credentials, virtual environments, and build
caches are excluded from Git. Release archives belong in GitHub Releases.
