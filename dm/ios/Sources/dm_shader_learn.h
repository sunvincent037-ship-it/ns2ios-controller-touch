#pragma once
#include <stddef.h>

// ---- What the host learns about a shader's output types ------------------------------------------------------------
// A game may write a colour target that its pass binds as an unsigned (or signed) integer format from a shader whose
// output is declared float: the console's hardware converts the value as it writes it, Metal refuses the pipeline
// ("output of type float4 is not compatible with a MTLPixelFormatR8Uint color attachment") and the draw disappears.
//
// Nothing can decide this ahead of time: the output type is a property of the shader, the format a property of the pass,
// and only the pass knows it. The translator offers two ways out -- an automatic integer entry point (dmsh_build.py
// fs_uint) for the shaders it recognises, and a hand-written row per shader in shader_facts_manual.tsv -- and both need
// the answer before the game is ever run.
//
// So the host learns it instead, from the refusal itself: it rewrites that one declaration in the shader's source to
// uint (or int), converts every value written to it, compiles the source again and builds the pipeline. The row goes to
// Documents/dm_shader_learn.tsv, and the next launch's one-off compile (dm_shader_prep) reads it, so a shader that was
// ever refused is compiled with the right output types the first time and never stalls again.
//
// This only works where the package holds shader source (the Windows route: nometal_run.py copies the source instead of
// running Apple's compiler, and dm_shader_prep compiles it on the device). A package with real metallib has no source to
// rewrite: dm_shader_learn_rewrite returns NULL and nothing changes.

// The source with the chosen colour outputs declared unsigned/signed, and every value written to them converted.
// mask: bits 0-7 = colour slots that must be unsigned, bits 8-15 = slots that must be signed.
// Returns a malloc'd, NUL-terminated buffer (*out_len excluding the NUL), or NULL when this source declares none of those
// slots as float, or uses one of them somewhere other than as the target of a plain assignment (a rewrite not guessed
// at). The caller frees it with free().
char *dm_shader_learn_rewrite(const char *src, size_t len, unsigned mask, size_t *out_len);

// The mask learned for this shader (0 = nothing). Reads the stored rows; never compiles anything.
unsigned dm_shader_learn_mask(const char *key);

// Add (or widen) the mask kept for this shader. Called once a pipeline built with it exists.
void dm_shader_learn_note(const char *key, unsigned mask, const char *why);

// DM_SHADER_LEARN=0 turns the whole mechanism off: the red line then behaves exactly as it did before.
int dm_shader_learn_enabled(void);

// The file the rows live in, for the log; NULL when there is no Documents directory to write to.
const char *dm_shader_learn_path(void);
