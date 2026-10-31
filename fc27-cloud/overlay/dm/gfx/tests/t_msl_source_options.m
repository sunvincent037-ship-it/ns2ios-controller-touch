// Query the actual Metal compile options without requiring a GPU or game data.
#import <Foundation/Foundation.h>
#include "../msl_source_options.h"
#include <stdio.h>
int main(void) { @autoreleasepool {
    MTLCompileOptions *o = dm_msl_source_options();
    if (!o || !o.preserveInvariance || o.mathMode != MTLMathModeRelaxed) {
        fprintf(stderr, "FAIL: source compilation must preserve invariant positions and NaN-aware relaxed math\n");
        return 1;
    }
    printf("Source compiler contract: relaxed math, invariant positions (%s)\n", DM_MSL_SOURCE_OPTIONS_TAG);
    return 0;
} }
