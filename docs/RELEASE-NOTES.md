# Just Trim 1.1.2 — source release

By Shardul Narvekar. Proprietary application; public source for inspection.

- Drag a MOV from Explorer onto any part of the app, including the preview.
- Accept the optional `cslg` timing summary and omit it from exported clips,
  preserving the actual sample timing and compressed media bytes.
- Handle sparse metadata tracks without blocking later cuts. Track definitions
  remain present with zero samples when they have no content in the clip.
- Exclude unused Qt PDF/virtual-keyboard plugins and QML/Quick runtime libraries.

This public release contains **source only**. The owner's portable Windows ZIP
is supplied separately. Public bundled binary redistribution is withheld until
the exact third-party corresponding sources and required notices are prepared.
See [distribution requirements](https://github.com/shardulnarvekar/just-trim/blob/main/docs/DISTRIBUTION.md)
and [validation](https://github.com/shardulnarvekar/just-trim/blob/main/docs/VALIDATION.md).

Copyright (c) 2026 Shardul Narvekar. All rights reserved for protectable original
application material, subject to LICENSE.txt and GitHub's viewing/forking rights.
Third-party dependencies retain their own licenses.
