# Minecraft Dungeons II

**The user accepted the rendering-fix IPA. Single-player gameplay is observed on iPad. A 60 fps engine-limit correction is experimental, pending replacement-host performance acceptance.**

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

## Opening-logo abort on iPad

**Current offline workaround, measured on main build `9e9d887d59f7f7db176b35e3379258b9`.** The original IPA's `Documents/log.txt` on iPad17,1 / iPadOS 26.6.1 records video and audio decoding, followed by `nn::diag` abort at main+0x3c18. The stack passes through main+0x4238230 and the NativeXboxLive factory at main+0x423f5fc. The first location formats `XblInitialize failed: 0x%X` from `OnlineSubsystemNativeXboxLive/Private/Util/Xal.cpp:78`.

The statically verified failure chain is `XblInitialize` (main+0x712f020), `GlobalState::Create` (+0x7160740), `HCInitialize` (+0x7019020), its Nintendo HTTP provider (+0x7030cb0), and `nn::ssl::Context::Create` (+0x7030b1c). The host deliberately returns failure for that service; the provider converts it to `E_FAIL`. Xbox online transport is outside the offline host's scope. Merely changing the Unreal `-ini:` setting did not avoid the factory on this shipping build; a second device log has the same fatal stack.

The exact-build cut at main+0x423f5ec changes the factory's conditional branch to its existing disabled-subsystem path at +0x423f678. That path performs the game's cleanup and returns no Xbox subsystem. It does not change `XblInitialize`, the fatal handler, authentication results, the Nintendo/local subsystem, or local controller/account handling. This is a platform-limit workaround, not an implementation of Xbox online services. Whether the game accepts that absence through title and local gameplay remains open until the new IPA is installed and tested.

The same logs exposed CRLF in `msl/b-b63838f19a8a/inputs.tsv`: [Windows shader metadata fails the native stamp guards](../../../docs/reference/shaders.md#windows-shader-metadata-fails-the-native-stamp-guards). The packed metadata fix needs no shader retranslation.

An earlier launch also crashed in Apple's private filesystem shader cache under `nvn_deswz_gpu_init`; the next two launches passed that location. That separate intermittent failure is still open. The installed signature lacks the increased-memory-limit entitlement; the observed process limit was 5,117 MB, but neither captured fatal was a jetsam memory kill.

## Presentation fence on iPad

**Root cause verified; replacement-host acceptance pending.** On iPad17,1 / iPadOS 26.6.1 the process uses about 1.1 GiB with roughly 4 GiB of headroom. No captured failure at this point is a jetsam kill. A bounded launch with `-norhithread` still reaches the same fence.

Remote memory reads locate the GameThread wait at main+0x1501228, through +0x150194c and `FlushRenderingCommands` at +0x14fdc90. The event named `RenderingThread.cpp(1056)` depends on the untriggered event named `(1088)`. The flip consumer queue asks for frame 2; the graphics context has advanced to 3, but the completed-frame counter remains 0. The producer waits in +0x142b350. Its viewport producer calls the host's `vi::ListFrameHistory`, which logs that it always returns no history. See [VI frame history releases presentation fences](../../../docs/reference/frame-rate.md#vi-frame-history-releases-presentation-fences) for the general correction and ABI evidence.

The source also releases mapped source-shader files after copying their text, and makes full-library preparation optional with bounded thermal admission. These changes do not establish title-screen or gameplay acceptance. A temporary code-injection experiment was rejected by automatic approval review and was not executed; validation must use the normally compiled replacement host.

## Outstanding acceptance checks

The modified game-free shell compiled with Xcode in run 40747633054. The startup fix reuses that host and reassembles the rewritten Guest library. Validate the new unsigned IPA, then install it for a device test. Confirm first-launch Metal compilation, title screen, local gameplay, Xbox and DualSense controlling different players, reconnect, background/resume and separate save persistence. Online services are outside this port's scope. No playable gallery entry should be added until native gameplay passes.

## Rendering on iPad

The installed host from run 40825473513 reaches the title and hero menus on iPad17,1 / iPadOS 26.6.1. The observed process limit is now 12,285 MB; the menu uses approximately 1.2–1.4 GiB, remains at thermal state 0 and presents about 30 fps. The user reports that local co-op is available. These observations do not establish correct rendered output or full controller/save acceptance.

Black regions have straight triangle boundaries and move across the animated hero. Same-process `DM_NVN_UDC_AB` captures leave the artifacts present with both store-all and unwritten-attachment store elision. A diagnostic run replacing or dropping the directional-shadow fragment shader (`d71748ec1f014e2e_b`) leaves the black triangles present. In-frame snapshots show an intact depth-derived hero silhouette, then holes immediately in the first HDR material pass. Both pre-pass and material vertex sources already declare `[[position, invariant]]`, but the device's source-library loader passed nil compile options. See [Runtime source compilation must preserve offline options](../../../docs/reference/shaders.md#runtime-source-compilation-must-preserve-offline-options). The correction restores the existing offline compiler contract; new-host device acceptance remains pending.

Some automated launches still block after the movies: the latest eight queued frames are all marked dropped and the guest rendering fence waits. Starting from the visible launcher after a normal manual reopen reaches the menus. This launch-mode reliability issue remains open; it was not treated as evidence about the rendering comparison.

## Performance investigation on iPad

The rendering-fix IPA from run 40852975876 was accepted by the user. On 2026-10-29 a normally launched instance was observed in single-player gameplay on iPad17,1 / iPadOS 26.6.1, with the counter at 30 fps. The app requests present interval 2. At frame 6000 the 300-frame window had GPU p50 6.67 / p95 9.74 / max 13.11 ms, thermal state 0, footprint 1814 MiB. The user had selected MetalFX; its present pass cost p50 2.757 ms in a separate 600-present window. These are observations of the original working package, not the proposed 60 fps build.

Two independent causes are measured. First, the native UE5.6.1 limiters are not registered in the host. Static constructors at main+0x33eaa78 and +0x147dc20 register `t.MaxFPS` and `rhi.SyncInterval`; their TAutoConsoleVariable objects are main+0xae22500 and +0xac91a10, with value pointers at +0x10. The existing general frame-limit mechanism now handles this exact build and both game/render-thread copies. `fps_target 60` selects the experimental target; 30 and 0 remain supported overrides. It does not change render scale, effects or guest time-step code. `test_dungeons_performance.py` executes the production implementation and covers initialization, config resets, overrides, both copies, invalid values and the build gate.

Second, first-use source-shader compilation blocks submission. Frame 5846 took 2132.8 ms, including 2098.8 ms of new shader-library/pipeline work while the GPU took 13.1 ms. Other examples include frames 4728 and 4730 at 1087.0 and 1911.7 ms. Full preparation through the existing `DM_SHADER_PREP=all` path can move source-library compilation before gameplay; its two-worker thermal admission and shared relaxed/invariant options must remain intact. It costs a potentially long one-time preparation and does not promise to prebuild every unseen pipeline. Learned PSO manifests should remain local and be retained.

The iOS view fits 16:9 and the presenter preserves the game's aspect ratio. Filling the iPad by stretching or cropping would not meet the user's requirement. Native aspect expansion has not been established; the performance build keeps the aspect ratio, resolution and letterboxing.

New-package device acceptance must measure actual presentation cadence in the same gameplay route after preparation, plus motion, audio, co-op, saves and thermals. A successful build or 60 fps target is not proof of sustained 60 fps.
