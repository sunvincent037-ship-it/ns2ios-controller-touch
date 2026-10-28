# iOS controller and touch implementation plan

**Goal:** Give Xbox and DualSense separate players and restore on-demand touch controls.

**Architecture:** Reuse the existing host player input and slot APIs; keep UIKit
layout cycling in a small portable policy header.

**Tech stack:** Objective-C, GameController, UIKit, C, Python unittest, Xcode.

- [x] Reproduce the old iOS wiring with `python -m unittest dm.tools.tests.test_ios_gamepad -v` (four expected failures).
- [x] Add `ios_pad_layout.h` and run the 21 slot/layout checks in `t_ios_pad.c` with Zig cc on Windows.
- [x] Update `DmGamepad.m`: independent player publishing, slot lifecycle, main-queue handlers, always accessible layout switch, release on background.
- [x] Integrate the portable test into `dm/host/tests/Makefile` and update the shell overlay and its DmGamepad patch.
- [x] Document the cause and correction in the services reference and Wonder note; refresh the symptom index.
- [x] Run wiring tests, portable tests, documentation checks and patch application checks. Xcode 26.3 builds the shell; native HID tests pass 119 checks. Device validation remains pending; whole documentation checks have existing fork-snapshot failures.
- [x] Build the shell in the user's authorized GitHub fork and repack the game locally. The new IPA passes all ZIP CRCs and preserves 55,599 game/resource entries. The original IPA is intact.
