# iOS independent controllers and touch controls

The iOS frontend currently publishes all physical controllers through one player-1
state and never reports additional connected players. The host already supports
independent players; the Mac frontend supplies the working slot assignment pattern.
Reuse `pad_slots.h`, retain controllers per slot, and publish buttons, sticks,
motion and rumble to the assigned player. Report the occupied mask, clear a
disconnected player's state and preserve other slots. Serialize callbacks on the
main queue, as UIKit and the slot table belong to that queue.

Retain the layout switch outside the hidden control layer. With physical pads,
cycle Pad (hidden), 2D, 3D, then Tap only in handheld mode, then Pad. Without
physical pads, cycle the existing 2D/3D/Tap layouts. The virtual pad feeds player
1; it does not allocate another player. Empty space still sends raw game touches
through the existing handheld touch path. Save visible layouts only; on losing
the last physical pad restore the preferred visible layout. Reset owned touches
on every mode change so buttons cannot remain held.

Verification covers Xbox/DualSense slot separation and reconnect, layout cycles,
frontend wiring, background releases, the existing HID player tests and raw touch
tests where the platform permits them. This Windows machine cannot compile UIKit
or run iOS. A new unsigned shell must be built with Xcode locally or in GitHub
Actions and then repacked with the existing local game files. No device signing
or installation is part of this change.
