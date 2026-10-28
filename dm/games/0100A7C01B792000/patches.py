# Minecraft Dungeons II 1.1.1.0: measured constructor, object and vtable addresses.
# The matching build-gated host mapping in hle_uemalloc.c installs UE5_6's vtable
# before startup. Without that replacement this cut must not be used.
CUTS = {
    '9e9d887d59f7f7db176b35e3379258b9': [
        (0x143b0, '6c700294', '1f2003d5',
         'nninitStartup: FMallocBinned3 constructor at main+0xb0560 reserves 38 GiB; '
         'the host installs its allocator in the object at main+0x9979228'),
    ],
}
