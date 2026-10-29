// 壳专用（不含游戏内容的公开版安装包，tools/shell_build.sh）：首次启动把全部着色器一次编完，带进度。内测 / 自己用 Xcode 构建的包不编这个文件的内容。
// 为什么要有：使用者的电脑上没有苹果的着色器编译器时，着色器是以源码放进安装包的（tools/d2rm_pack.py、gfx/tools/nometal_run.py），
// 设备上用到哪个现编哪个。真机实测：平均约 80 毫秒一个、单个最长约 450 毫秒；边玩边编的话第一次进一个新场景会顿约 0.8 秒
// （编好的库同一处是 0.12 秒）。所以改成进主菜单之前一次编完——系统会把编好的结果缓存，之后游戏里再建同一个库不花时间。
// 做完的记号放在 Library/Caches（和系统的着色器缓存在同一处，系统清缓存时一起没，下次启动自动重做一遍）。
// 中途切到后台 / 被杀：已编的在系统缓存里，回来从头数一遍，已编的每个只要不到 1 毫秒，等于接着做。
// Shell only (the public install package with no game content, tools/shell_build.sh): on first launch compile all shaders in one go, with progress. Beta packages / packages you build yourself with Xcode do not compile this file's contents.
// Why it exists: when the user's computer has no Apple shader compiler, the shaders are put into the install package as source (tools/d2rm_pack.py, gfx/tools/nometal_run.py),
// and each is compiled on the device when it is first used. Measured on a real device: about 80 ms each on average, about 450 ms for the longest single one; compiling while playing, the first entry into a new scene stutters for about 0.8 seconds
// (0.12 seconds at the same spot with compiled libraries). So it is changed to compiling everything once before entering the main menu -- the system caches the compiled results, and building the same library again in the game afterwards takes no time.
// The completion marker is placed in Library/Caches (the same place as the system's shader cache, so it goes away together when the system clears caches, and the next launch automatically redoes it once).
// Sent to the background / killed midway: what was compiled is in the system cache; on return it counts from the start, each already compiled one taking less than 1 ms, which amounts to resuming.
#ifdef DM_SHELL
#import <Metal/Metal.h>
#import <UIKit/UIKit.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dm_shader_learn.h"
#include "dm_shader_prep_policy.h"
#include "../../gfx/msl_source_options.h"

static void pl(NSString *s) { fprintf(stderr, "[dm] %s\n", s.UTF8String); }
static int lg(void) { NSString *l = NSLocale.preferredLanguages.firstObject; return [l hasPrefix:@"zh"] ? 1 : [l hasPrefix:@"es"] ? 2 : 0; }   // 系统首选语言：1 中文 / 2 西语 / 0 其余英文 | System preferred language: 1 Chinese / 2 Spanish / 0 English otherwise
#define L3(zh, en, es) (lg() == 1 ? (zh) : lg() == 2 ? (es) : (en))
static NSString *msldir(void) { return [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"msl"]; }
static NSString *libdir(void) {   // <包>/msl/b-<链版本>：壳里只有一个版本目录 | <package>/msl/b-<chain version>: the shell has only one version directory
    NSString *msl = msldir();
    for (NSString *d in [NSFileManager.defaultManager contentsOfDirectoryAtPath:msl error:nil] ?: @[]) if ([d hasPrefix:@"b-"]) return [msl stringByAppendingPathComponent:d];
    return nil;
}
// 编好的库以 MTLB 开头；不是的就是源码 | a compiled library starts with MTLB; anything else is source
static BOOL is_source(NSString *path) {
    FILE *f = fopen(path.fileSystemRepresentation, "rb"); if (!f) return NO; char h[4] = {0}; size_t n = fread(h, 1, 4, f); fclose(f);
    return n == 4 && memcmp(h, "MTLB", 4) != 0;
}
// 以源码形式放进包的着色器：NVN 的是 b-<链版本> 下的 *.metallib（还是源码，不是 MTLB），GL 的是 msl/gl/src 下的 *.metal
// （打包的电脑上没有苹果的编译器时，gl_shaders.py 只写这两样：PC 上能装 glslang 和 spirv-cross，装不了 xcrun metal）
// The shaders a package holds as source: NVN's are the *.metallib that are not MTLB under b-<chain version>, GL's the
// *.metal under msl/gl/src (what gl_shaders.py writes when the packing computer has no Apple compiler).
static NSArray<NSString *> *shader_sources(void) {
    NSMutableArray<NSString *> *a = [NSMutableArray array];
    NSString *d = libdir();
    for (NSString *f in [[NSFileManager.defaultManager contentsOfDirectoryAtPath:d error:nil] sortedArrayUsingSelector:@selector(compare:)] ?: @[]) {
        NSString *p = [d stringByAppendingPathComponent:f];
        if ([f hasSuffix:@".metallib"] && is_source(p)) [a addObject:p];
    }
    NSString *gs = [msldir() stringByAppendingPathComponent:@"gl/src"];
    for (NSString *f in [[NSFileManager.defaultManager contentsOfDirectoryAtPath:gs error:nil] sortedArrayUsingSelector:@selector(compare:)] ?: @[])
        if ([f hasSuffix:@".metal"]) [a addObject:[gs stringByAppendingPathComponent:f]];
    NSString *vs = [msldir() stringByAppendingPathComponent:@"vk/src"];
    for (NSString *f in [[NSFileManager.defaultManager contentsOfDirectoryAtPath:vs error:nil] sortedArrayUsingSelector:@selector(compare:)] ?: @[])
        if ([f hasSuffix:@".metal"]) [a addObject:[vs stringByAppendingPathComponent:f]];
    return a;
}
static NSString *marker(NSArray<NSString *> *src, NSString *dir) {
    // The key has to name this package's shaders, not just the source tree: the chain version (b-<V>) follows the source tree
    // and is the same for every game, so a marker keyed by it alone says "done" for a different game's package, or for a
    // repack whose shaders changed -- and the app then loads source-form .metallib files as if they were compiled, which
    // Metal rejects as "Invalid library file" and the game runs on with no picture at all. The package's own stamp
    // (inputs.tsv: the game and the digest of the profile inputs) is what distinguishes one package from another; a package
    // without it falls back to a digest of the directory's contents.
    NSString *tag = dir.lastPathComponent ?: @"gl";
    tag = [tag stringByAppendingFormat:@"-%s", DM_MSL_SOURCE_OPTIONS_TAG];
    NSString *stamp = [NSString stringWithContentsOfFile:[(dir ?: [msldir() stringByAppendingPathComponent:@"gl"]) stringByAppendingPathComponent:@"inputs.tsv"] encoding:NSUTF8StringEncoding error:nil];
    for (NSString *ln in [stamp componentsSeparatedByString:@"\n"]) {
        NSArray *c = [ln componentsSeparatedByString:@"\t"];
        if (c.count == 2 && ([c[0] isEqual:@"inputs"] || [c[0] isEqual:@"game"])) tag = [tag stringByAppendingFormat:@"-%@", c[1]];
    }
    unsigned long long n = 0, bytes = 0;
    for (NSString *p in src) { n++; bytes += [NSFileManager.defaultManager attributesOfItemAtPath:p error:nil].fileSize; }
    if (n) tag = [tag stringByAppendingFormat:@"-%llux%llu", n, bytes];
    NSString *c = NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES).firstObject;
    return [c stringByAppendingPathComponent:[NSString stringWithFormat:@"dm_shader_prep_%@_%@.done", tag, NSProcessInfo.processInfo.operatingSystemVersionString.length ? @(NSProcessInfo.processInfo.operatingSystemVersion.majorVersion * 100 + NSProcessInfo.processInfo.operatingSystemVersion.minorVersion).stringValue : @"0"]];
}
// 要不要做：返回 1 = 已接手（显示进度页，做完调 done）；0 = 不用做（没有源码着色器，或上次已经做完）
// Whether it needs to run: returns 1 = taken over (shows the progress page, calls done when finished); 0 = nothing to do (no source shaders, or already finished last time)
int dm_shader_prep_begin(void (^done)(void)) {
    if (!dm_shader_prep_all(getenv("DM_SHADER_PREP"))) {
        pl(@"shader preparation: using demanded shaders and the renderer's PSO manifests");
        return 0;
    }
    NSString *dir = libdir();   // NVN 的版本目录；GL 包没有，源码在 msl/gl/src | the chain version's directory; a GL package has none, its sources are in msl/gl/src
    NSMutableArray<NSString *> *src = [shader_sources() mutableCopy];
    if (!src.count) return 0;
    NSString *mk = marker(src, dir); if ([NSFileManager.defaultManager fileExistsAtPath:mk]) return 0;
    UIWindow *win = nil;
    for (UIScene *s in UIApplication.sharedApplication.connectedScenes) if ([s isKindOfClass:UIWindowScene.class]) for (UIWindow *w in ((UIWindowScene *)s).windows) if (!win || w.isKeyWindow) win = w;
    UIView *host = win.rootViewController.view ?: win; if (!host) { pl(@"【红】着色器准备：没有窗口可放进度页，跳过（进游戏后会边玩边编，第一次进新场景会顿）"); return 0; }
    UIView *v = [[UIView alloc] initWithFrame:host.bounds]; v.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight; v.backgroundColor = UIColor.blackColor;
    UILabel *title = [UILabel new], *sub = [UILabel new], *note = [UILabel new]; UIProgressView *bar = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleDefault];
    for (UILabel *l in @[title, sub, note]) { l.textColor = [UIColor colorWithWhite:0.85 alpha:1]; l.textAlignment = NSTextAlignmentCenter; l.numberOfLines = 0; l.translatesAutoresizingMaskIntoConstraints = NO; [v addSubview:l]; }
    title.font = [UIFont systemFontOfSize:20 weight:UIFontWeightSemibold]; sub.font = [UIFont monospacedDigitSystemFontOfSize:15 weight:UIFontWeightRegular]; note.font = [UIFont systemFontOfSize:13]; note.textColor = [UIColor colorWithWhite:0.6 alpha:1];
    bar.translatesAutoresizingMaskIntoConstraints = NO; bar.progressTintColor = [UIColor colorWithRed:0.78 green:0.36 blue:0.16 alpha:1]; [v addSubview:bar];
    title.text = L3(@"首次启动：正在准备着色器", @"First launch: preparing shaders", @"Primer inicio: preparando los shaders");
    note.text = L3(@"正在预编译全部着色器。设备温度过高或切到后台时会暂停。\n返回应用并降温后继续。",
                   @"Precompiling all shaders. Preparation pauses while the device is hot or the app is inactive.\nIt resumes when you return and the device cools.",
                   @"Precompilando todos los shaders. Se pausa si el dispositivo se calienta o la app queda inactiva.\nContinúa al volver y cuando se enfría.");
    [NSLayoutConstraint activateConstraints:@[
        [title.centerXAnchor constraintEqualToAnchor:v.centerXAnchor], [title.bottomAnchor constraintEqualToAnchor:bar.topAnchor constant:-22],
        [bar.centerXAnchor constraintEqualToAnchor:v.centerXAnchor], [bar.centerYAnchor constraintEqualToAnchor:v.centerYAnchor], [bar.widthAnchor constraintEqualToAnchor:v.widthAnchor multiplier:0.5],
        [sub.centerXAnchor constraintEqualToAnchor:v.centerXAnchor], [sub.topAnchor constraintEqualToAnchor:bar.bottomAnchor constant:14],
        [note.centerXAnchor constraintEqualToAnchor:v.centerXAnchor], [note.topAnchor constraintEqualToAnchor:sub.bottomAnchor constant:22], [note.widthAnchor constraintLessThanOrEqualToAnchor:v.widthAnchor multiplier:0.8]]];
    [host addSubview:v];
    UIApplication.sharedApplication.idleTimerDisabled = YES;   // 这几分钟别自动锁屏 | do not auto-lock the screen during these few minutes
    const char *te = getenv("DM_SHADER_PREP_THREADS");
    int total = (int)src.count, threads = dm_shader_prep_workers((int)NSProcessInfo.processInfo.activeProcessorCount, te ? atoi(te) : 0);
    NSCondition *gate = [NSCondition new];
    __block int next = 0, thermal = (int)NSProcessInfo.processInfo.thermalState;
    __block int active = UIApplication.sharedApplication.applicationState == UIApplicationStateActive;
    __block int low_power = NSProcessInfo.processInfo.lowPowerModeEnabled;
    NSMutableArray *observers = [NSMutableArray array];
    for (NSNotificationName name in @[NSProcessInfoThermalStateDidChangeNotification,
            NSProcessInfoPowerStateDidChangeNotification, UIApplicationDidBecomeActiveNotification,
            UIApplicationWillResignActiveNotification, UIApplicationDidEnterBackgroundNotification]) {
        id observer = [NSNotificationCenter.defaultCenter addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
            [gate lock];
            thermal = (int)NSProcessInfo.processInfo.thermalState;
            low_power = NSProcessInfo.processInfo.lowPowerModeEnabled;
            if ([note.name isEqual:UIApplicationWillResignActiveNotification] || [note.name isEqual:UIApplicationDidEnterBackgroundNotification]) active = 0;
            else active = UIApplication.sharedApplication.applicationState == UIApplicationStateActive;
            [gate broadcast]; [gate unlock];
        }];
        [observers addObject:observer];
    }
    pl([NSString stringWithFormat:@"着色器准备：开始，共 %d 个，%d 线程", total, threads]);
    CFAbsoluteTime t0 = CFAbsoluteTimeGetCurrent(); __block _Atomic int fin = 0, bad = 0;
    void (^tick)(void) = ^{ int n = atomic_load(&fin); double el = CFAbsoluteTimeGetCurrent() - t0, left = n > 20 ? el / n * (total - n) : -1;
        bar.progress = (float)n / total;
        NSString *eta = left < 0 ? L3(@"正在估算剩余时间", @"estimating time left", @"calculando el tiempo restante") : left >= 90 ? [NSString stringWithFormat:L3(@"预计还要 %.0f 分钟", @"about %.0f min left", @"faltan unos %.0f min"), ceil(left / 60)] : [NSString stringWithFormat:L3(@"预计还要 %.0f 秒", @"about %.0f s left", @"faltan unos %.0f s"), ceil(left / 5) * 5];
        sub.text = [NSString stringWithFormat:@"%d / %d · %@", n, total, eta]; };
    tick();
    NSTimer *tm = [NSTimer scheduledTimerWithTimeInterval:0.5 repeats:YES block:^(NSTimer *t) { tick(); }];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice(); dispatch_group_t g = dispatch_group_create();
        for (int worker = 0; worker < threads; worker++) {
            dispatch_group_async(g, dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
              for (;;) { @autoreleasepool {
                [gate lock];
                while (next < total && worker >= dm_shader_prep_limit(threads, thermal, active, low_power)) [gate wait];
                if (next >= total) { [gate unlock]; break; }
                NSString *p = src[next++]; [gate unlock];
                NSString *txt = [NSString stringWithContentsOfFile:p encoding:NSUTF8StringEncoding error:nil]; NSError *e = nil;
                id<MTLLibrary> l = txt ? [dev newLibraryWithSource:txt options:dm_msl_source_options() error:&e] : nil;   // Keep the same options as the runtime so Metal's cache matches.
                if (!l && atomic_fetch_add(&bad, 1) < 5) pl([NSString stringWithFormat:@"【红】着色器准备：%@ 编不过：%@", p.lastPathComponent, e.localizedDescription ?: @"读不了"]);
                // 这个着色器以前被拒过管线：把它「输出声明成整数」的版本也编一遍（同一个调用、同样的文本，游戏里建库时缓存直接命中，不再卡）
                // This shader had a pipeline refused before, so the version with those outputs declared integer is compiled here
                // too: the game then builds that library out of the cache instead of stalling on it the first time it is drawn.
                unsigned lm = l ? dm_shader_learn_mask(p.lastPathComponent.stringByDeletingPathExtension.UTF8String) : 0;
                if (lm) {
                    const char *cs = txt.UTF8String; size_t on = 0;
                    char *w = dm_shader_learn_rewrite(cs, strlen(cs), lm, &on);
                    NSString *t2 = w ? [[NSString alloc] initWithBytes:w length:on encoding:NSUTF8StringEncoding] : nil;
                    free(w);
                    NSError *e2 = nil; id<MTLLibrary> l2 = t2 ? [dev newLibraryWithSource:t2 options:dm_msl_source_options() error:&e2] : nil;
                    if (!l2 && atomic_fetch_add(&bad, 1) < 5) pl([NSString stringWithFormat:@"【红】着色器准备：%@ 的整数输出版本编不过：%@", p.lastPathComponent, e2.localizedDescription ?: @"改写没做成"]);
                }
                int n = atomic_fetch_add(&fin, 1) + 1; if (n % 500 == 0) pl([NSString stringWithFormat:@"着色器准备：%d / %d，已用 %.0f 秒，温控档位 %ld", n, total, CFAbsoluteTimeGetCurrent() - t0, (long)NSProcessInfo.processInfo.thermalState]);
                [gate lock]; [gate broadcast]; [gate unlock];
              } }
            });
        }
        dispatch_group_wait(g, DISPATCH_TIME_FOREVER);
        double el = CFAbsoluteTimeGetCurrent() - t0; int nb = atomic_load(&bad);
        pl([NSString stringWithFormat:@"着色器准备：完成 %d 个，编不过 %d 个，用时 %.1f 秒，%d 线程，结束时温控档位 %ld", total, nb, el, threads, (long)NSProcessInfo.processInfo.thermalState]);
        if (!nb) [@"ok" writeToFile:mk atomically:YES encoding:NSUTF8StringEncoding error:nil];   // 有编不过的就不记完成：下次启动再来一遍（已编的很快） | if any failed to compile, do not record completion: run it again at the next launch (the already compiled ones are fast)
        dispatch_async(dispatch_get_main_queue(), ^{
            for (id observer in observers) [NSNotificationCenter.defaultCenter removeObserver:observer];
            [tm invalidate]; [v removeFromSuperview]; UIApplication.sharedApplication.idleTimerDisabled = NO; done();
        });
    });
    return 1;
}
#endif
