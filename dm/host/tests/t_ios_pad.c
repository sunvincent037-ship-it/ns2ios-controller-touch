// iOS overlay policy and the shared controller slots; runs without UIKit or a device.
#include <stdio.h>
#include "../pad_slots.h"
#include "../../ios/Sources/ios_pad_layout.h"

#define CHECK(c) do { checks++; if (!(c)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)

int main(void) {
    int checks = 0;
    pad_slots slots = {0};
    char xbox, dualsense, reconnected;
    CHECK(pad_slot_take(&slots, &xbox, "Xbox Wireless Controller") == 0);
    CHECK(pad_slot_take(&slots, &dualsense, "DualSense Wireless Controller") == 1);
    CHECK(pad_slot_mask(&slots) == 3);
    CHECK(pad_slot_free(&slots, &dualsense) == 1);
    CHECK(pad_slot_of(&slots, &xbox) == 0);
    CHECK(pad_slot_mask(&slots) == 1);
    CHECK(pad_slot_take(&slots, &reconnected, "DualSense Wireless Controller") == 1);
    CHECK(pad_slot_mask(&slots) == 3);

    CHECK(ios_pad_layout_valid(0, 0) == IOS_PAD_2D);
    CHECK(ios_pad_layout_valid(1, 0) == IOS_PAD_3D);
    CHECK(ios_pad_layout_valid(2, 0) == IOS_PAD_2D);
    CHECK(ios_pad_layout_valid(2, 1) == IOS_PAD_TAP);
    CHECK(ios_pad_layout_valid(-1, 1) == IOS_PAD_2D);
    CHECK(ios_pad_layout_valid(99, 1) == IOS_PAD_2D);

    // Docked: the always-visible Pad switch restores the controls with pads connected.
    CHECK(ios_pad_layout_next(IOS_PAD_HIDDEN, 0, 1) == IOS_PAD_2D);
    CHECK(ios_pad_layout_next(IOS_PAD_2D, 0, 1) == IOS_PAD_3D);
    CHECK(ios_pad_layout_next(IOS_PAD_3D, 0, 1) == IOS_PAD_HIDDEN);
    // Without a physical controller the overlay cannot disappear in docked mode.
    CHECK(ios_pad_layout_next(IOS_PAD_3D, 0, 0) == IOS_PAD_2D);
    // Handheld: raw touch remains a separate layout, with or without a controller.
    CHECK(ios_pad_layout_next(IOS_PAD_3D, 1, 1) == IOS_PAD_TAP);
    CHECK(ios_pad_layout_next(IOS_PAD_TAP, 1, 1) == IOS_PAD_HIDDEN);
    CHECK(ios_pad_layout_next(IOS_PAD_TAP, 1, 0) == IOS_PAD_2D);
    printf("iOS controller slots and touch layouts: %d checks passed\n", checks);
    return 0;
}
