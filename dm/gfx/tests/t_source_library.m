// Exercise lib_from_file itself: a source library must release its file mapping
// on success, invalid UTF-8 and a Metal compiler error. macOS + Metal required.
#include <sys/mman.h>
#include <stddef.h>
static size_t mapped_bytes;
static void *tracked_mmap(void *p, size_t n, int prot, int flags, int fd, off_t off) {
    void *result = mmap(p, n, prot, flags, fd, off);
    if (result != MAP_FAILED) mapped_bytes += n;
    return result;
}
static int tracked_munmap(void *p, size_t n) {
    int result = munmap(p, n);
    if (!result) mapped_bytes -= n;
    return result;
}
#define mmap tracked_mmap
#define munmap tracked_munmap
#ifndef DM_SHELL
#define DM_SHELL 1
#endif
#include "../nvn/nvn_mtl.m"
#undef mmap
#undef munmap
uint64_t g_t0_ns;
int dm_guest_as_contains(uintptr_t address) { (void)address; return 0; }
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }

int main(void) { @autoreleasepool {
    g_dev = MTLCreateSystemDefaultDevice();
    if (!g_dev) { fprintf(stderr, "Metal device required\n"); return 1; }
    NSString *path = [NSTemporaryDirectory() stringByAppendingPathComponent:
        [NSString stringWithFormat:@"dm-source-%@.metallib", NSUUID.UUID.UUIDString]];
    const unsigned char bad_utf8[] = {0xff, 0xff, 0xff, 0xff};
    NSArray<NSData *> *cases = @[
        [@"#include <metal_stdlib>\nusing namespace metal; kernel void test_kernel(uint i [[thread_position_in_grid]]) {}\n" dataUsingEncoding:NSUTF8StringEncoding],
        [NSData dataWithBytes:bad_utf8 length:sizeof bad_utf8],
        [@"not valid Metal source" dataUsingEncoding:NSUTF8StringEncoding],
    ];
    int failures = 0;
    for (NSUInteger i = 0; i < cases.count; i++) { @autoreleasepool {
        [cases[i] writeToFile:path atomically:YES];
        NSError *error = nil;
        id<MTLLibrary> library = lib_from_file(path, &error);
        if ((i == 0) != (library != nil) || mapped_bytes != 0 || (i != 0 && !error)) {
            fprintf(stderr, "FAIL case %lu: library=%d mapped=%zu error=%s\n",
                    (unsigned long)i, library != nil, mapped_bytes, error.description.UTF8String);
            failures++;
        }
        if (i == 2 && [error.domain isEqual:@"dm"]) {
            fprintf(stderr, "FAIL: Metal compiler diagnostic was replaced\n"); failures++;
        }
    } }
    [NSFileManager.defaultManager removeItemAtPath:path error:nil];
    return failures ? 1 : 0;
} }
