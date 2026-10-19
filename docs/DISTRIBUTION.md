# Binary distribution and dependency rights

The application source repository is public at Shardul Narvekar's request.
Its original application material retains the proprietary terms in LICENSE.txt.
Public releases contain source only. The portable Windows package is supplied
separately for the owner's personal use. Earlier bundled release assets are
kept in a non-public draft release, not exposed through public downloads.

The application licensing/attribution documents are in place. Compliance work
for public distribution of bundled third-party runtimes is **not complete**.
Do not describe the portable ZIP as cleared for public redistribution or sale.
No third-party copyright is reassigned.

## Current package

- The original application is subject to `LICENSE.txt`.
- Python's license and the LGPL/GPL license texts are included in `licenses/`.
- `THIRD-PARTY-NOTICES.txt` identifies the runtimes and upstream sources.
- Qt/PySide/FFmpeg remain separate DLLs in `_internal`, with no application
  integrity check blocking compatible modified versions.
- The app's complete source and pinned direct build requirements are included.
- The PyInstaller bootloader permits applications to use their own license
  under its exception. See the included PyInstaller notice.
- Version 1.1.2 excludes unused Qt PDF, virtual-keyboard, QML, and Quick modules
  and their entry-point plugins from the portable package.

To use a compatible modified Qt/PySide/FFmpeg build, keep a backup of the app,
replace the applicable DLLs/package files under `_internal` with an ABI-compatible
build, and launch normally. Alternatively, create a Python 3.11 x64 environment,
install your compatible modified runtime packages, and rebuild the application
using the commands in README.md. No application signing keys are required.

## Before giving a binary to other people

1. Inventory the exact libraries in that build, including their transitive
   dependencies. Confirm that any new Qt module is available under terms
   compatible with the intended proprietary application.
2. Retain the complete corresponding source of the exact LGPL-covered library
   builds, including downstream patches, configuration, and necessary build
   scripts. Deliver it or use a license-compliant source-delivery/offer mechanism.
   Upstream links in a notice are useful provenance; they alone do not establish
   full compliance. The current archive does not contain those library source
   trees, and it does not make an unbacked written source offer.
3. Include all required copyright notices and license texts with every package,
   including transitive components. Allow library modification/replacement and
   reverse engineering for debugging those modifications as required by LGPL.
4. Check distribution-channel terms, codec patent requirements, and your end-user
   terms with qualified counsel before a commercial/public release.

This does not mean your own application must automatically become open source.
The obligations depend on the license and how the libraries are used/distributed.
Qt describes dynamic-linking conditions for proprietary applications in its
[official LGPL guidance](https://www.qt.io/development/open-source-lgpl-obligations).
Consult the full [LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.en.html),
[LGPLv2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.en.html), and
[FFmpeg legal guidance](https://ffmpeg.org/legal.html).
