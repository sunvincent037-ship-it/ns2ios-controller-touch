// UIKit-free layout policy. Only the visible layouts are saved in NSUserDefaults.
#pragma once
enum { IOS_PAD_2D, IOS_PAD_3D, IOS_PAD_TAP, IOS_PAD_HIDDEN };

static inline int ios_pad_layout_valid(int layout, int handheld) {
    if (layout == IOS_PAD_3D) return IOS_PAD_3D;
    if (layout == IOS_PAD_TAP && handheld) return IOS_PAD_TAP;
    return IOS_PAD_2D;
}

static inline int ios_pad_layout_next(int layout, int handheld, int physical) {
    if (layout == IOS_PAD_HIDDEN) return IOS_PAD_2D;
    if (layout == IOS_PAD_2D) return IOS_PAD_3D;
    if (layout == IOS_PAD_3D && handheld) return IOS_PAD_TAP;
    return physical ? IOS_PAD_HIDDEN : IOS_PAD_2D;
}
