#pragma once
#import <Metal/Metal.h>

// Match ios_metal.py's -fmetal-math-mode=relaxed -fpreserve-invariance.
// The default fast mode may remove the translator's NaN guards, and default
// invariance breaks depth agreement between pre-pass and material shaders.
// This tag is part of the optional full-preparation completion marker.
#define DM_MSL_SOURCE_OPTIONS_TAG "relaxed-invariant-v1"
static inline MTLCompileOptions *dm_msl_source_options(void) {
    MTLCompileOptions *options = [MTLCompileOptions new];
    options.mathMode = MTLMathModeRelaxed;
    options.preserveInvariance = YES;
    return options;
}
