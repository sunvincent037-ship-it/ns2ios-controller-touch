# Minecraft Dungeons II

**Experimental, not yet boot-tested on Apple hardware. Local two-player gameplay is not verified.**

## Measured input

- Title ID: `0100A7C01B792000`; update v65536, display version 1.1.1.0.
- Main: `9e9d887d59f7f7db176b35e3379258b9`.
- Movie module: `3904a8dee6801472d56bd4921378df27`.
- SDK: `190030518b5d64e5d87b84bc54661af9`, version 20.5.15.
- Unreal Engine 5.6.1, NVN, Wwise and Havok.
- Base plus update extracts without bypassing integrity failures. The Hero Pack NSP extracts as index 1 with one 50-byte `PreOrderDLC.txt` marker; its substantive assets are in the main game.

## Offline rendering work

The 3.87 GiB merged RomFS has 61 files. `Dungeons/Content/Paks/Dungeons-Switch.utoc` is an unencrypted version 8 IoStore container: 48,631 chunks, two shader libraries and 2,125 shader-code groups. Its compression method is Oodle. A locally installed PC game's Oodle library decoded the two shader archives on Windows. No decoder binary is distributed with this profile.

All 16,751 decoded shader records parse as LSLG; deduplication gives 15,826 unique shaders. The Windows translation results report all 15,826 successful. There are 15,825 ordinary Metal-source libraries and one slice-only geometry metadata entry, which the host folds into the vertex shader's layer entry points. This verifies source generation, not Apple's compilation or rendered output. The translator also reports unimplemented instruction notes; their effect on this title's rendering is still open.

`tex_dyn_slots` enables the host's runtime texture-table fallback for shaders whose handles vary between c2 slots. Bindings and rendered output require native validation.

## Memory

The exported `nninitStartup` thunk reaches main+0x13f30. It defaults to a 62 GiB virtual-address reservation. The supported `-SwitchVirtualAddressSpaceSize=4064` argument caps that region. The profile starts with a 5 GiB guest block and 4.375 GiB alias region; its heap split and long-session address use remain provisional.

The allocator constructor at main+0xb0560 installs vtable main+0x85b68a8 in the static object main+0x9979228. Its reserve is 38 GiB. The call at main+0x143b0 is cut only for this main build, paired with the build-gated host allocator mapping. Its 32-slot layout matches the host's UE5_6 layout: TryMalloc and TryRealloc dispatch through offsets 0x30 and 0x40; zeroed allocation uses Malloc and memset; thread-safety and heap-validation slots return true. The SDK node-area function matcher recognizes this SDK and reduces its address-manager node region. Actual boot, residency and allocator behavior remain untested.

## Local two-player input

Reuse the independent physical-controller slots and touch overlay from the controller fix. The profile requests two local users because this game's account-selector call sites (main+0x424f2f8 and +0x424f424) set `additionalSelect` when another local user is needed. Returning the primary UID for that request duplicates player 1. The local-user implementation must choose a distinct eligible UID and keep its save backing separate. This adds no sign-in or account-management UI.

## Outstanding acceptance checks

Compile the modified game-free shell with Xcode, validate the unsigned IPA, then boot on Apple hardware. Confirm first-launch Metal compilation, title screen, local gameplay, Xbox and DualSense controlling different players, reconnect, background/resume and separate save persistence. Online services are outside this port's scope. No playable gallery entry should be added until native gameplay passes.
