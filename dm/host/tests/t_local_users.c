// Included after the actual account hooks and MountSaveData implementation by test_local_users.py.
static Uid user(int index) {
    Uid uid = {{0x78626c0000000001ull + (uint64_t)index, 0x53574e4154495645ull}};
    return uid;
}
static int equal(Uid a, Uid b) { return a.v[0] == b.v[0] && a.v[1] == b.v[1]; }
static void open_count(int expected) {
    Uid out[8]; int n = -1;
    assert(h_acc_ListOpen(&n, out, 8) == RES_OK && n == expected);
}

int main(int argc, char **argv) {
    assert(argc > 1);
    const char *test = argv[1];
    Uid primary = user(0), secondary = user(1), unknown = user(8), out = {{0}};
    UserHandle first = {{0}}, second = {{0}};
    unsigned char settings[0x88] = {0};
    if (!strcmp(test, "enumerate")) {
        int expected = atoi(argv[2]), n = 0; Uid users[8] = {{{0}}};
        assert(h_acc_UserCount(&n) == RES_OK && n == expected);
        assert(h_acc_ListAll(&n, users, 8) == RES_OK && n == expected);
        for (int i = 0; i < n; i++) assert(equal(users[i], user(i)));
        assert(h_acc_ListQual(&n, users, 8) == RES_OK && n == expected);
        assert(h_acc_ListAll(&n, users, 1) == RES_OK && n == 1 && equal(users[0], primary));
        assert(h_acc_ListAll(&n, NULL, 0) == RES_OK && n == 0);
        uint8_t exists = 0;
        assert(h_acc_Exists(&exists, &primary) == RES_OK && exists);
        if (expected < 8) { Uid absent = user(expected); assert(h_acc_Exists(&exists, &absent) == RES_OK && !exists); }
        char nick[33]; assert(h_acc_GetNick(nick, &primary) == RES_OK && !strcmp(nick, "Player"));
    } else if (!strcmp(test, "lifecycle")) {
        open_count(0);
        assert(h_acc_TryOpenPre(&first) == 1);
        assert(h_acc_GetUserId(&out, &first) == RES_OK && equal(out, primary)); open_count(1);
        assert(h_acc_OpenUser(&second, &secondary) == RES_OK); open_count(2);
        assert(h_acc_LastOpened(&out) == RES_OK && equal(out, secondary));
        h_acc_CloseUser(&first); open_count(1);
        assert(h_acc_GetUserId(&out, &first) != RES_OK);
        h_acc_CloseUser(&first); open_count(1);
        assert(h_acc_LastOpened(&out) == RES_OK && equal(out, secondary));
        h_acc_CloseUser(&second); open_count(0);
        assert(h_acc_OpenPre(&first) == RES_OK); open_count(1);
        assert(h_acc_LastOpened(&out) == RES_OK && equal(out, primary));
        assert(h_acc_OpenUser(&second, &primary) == RES_OK); open_count(1);
        h_acc_CloseUser(&first); open_count(1);
        h_acc_CloseUser(&second); open_count(0);
    } else if (!strcmp(test, "selection")) {
        assert(h_acc_ShowSel(&out, settings) == RES_OK && equal(out, primary)); open_count(0);
        assert(h_acc_TryOpenPre(&first));
        settings[0x83] = 1;
        assert(h_acc_ShowSel(&out, settings) == RES_OK && equal(out, secondary)); open_count(1);
        memcpy(settings + 7 * sizeof(Uid), &secondary, sizeof secondary);
        assert(h_acc_ShowSel(&out, settings) != RES_OK);
        memset(settings, 0, sizeof settings); settings[0x83] = 1;
        assert(h_acc_OpenUser(&second, &secondary) == RES_OK);
        assert(h_acc_ShowSel(&out, settings) != RES_OK);
        h_acc_CloseUser(&second);
        assert(h_acc_ShowSel(&out, settings) == RES_OK && equal(out, secondary));
        memset(settings, 0, sizeof settings);
        memcpy(settings, &primary, sizeof primary);
        assert(h_acc_ShowSel(&out, settings) == RES_OK && equal(out, secondary));
        memcpy(settings + sizeof(Uid), &secondary, sizeof secondary);
        assert(h_acc_ShowSel(&out, settings) != RES_OK);
    } else if (!strcmp(test, "online")) {
        settings[0x81] = 1;
        assert(h_acc_ShowSel(&out, settings) != RES_OK);
        assert(h_acc_OpenPre(&first) == RES_OK);
        uint8_t available = 1;
        assert(h_acc_NsaAvail(&available, &first) == RES_OK && !available);
        assert(h_acc_EnsureNsa(&first) != RES_OK);
    } else if (!strcmp(test, "invalid")) {
        Uid zero = {{0}}; uint8_t exists = 1; char nick[33];
        assert(h_acc_Exists(&exists, &unknown) == RES_OK && !exists);
        assert(h_acc_OpenUser(&first, &unknown) != RES_OK);
        assert(h_acc_OpenUser(&first, &zero) != RES_OK);
        assert(h_acc_GetNick(nick, &unknown) != RES_OK);
        assert(h_acc_GetUserId(&out, &first) != RES_OK); open_count(0);
        int n = -1;
        assert(h_acc_ListAll(&n, NULL, 1) != RES_OK);
        assert(h_acc_ListOpen(&n, &out, -1) != RES_OK);
    } else if (!strcmp(test, "saves")) {
        assert(h_fs_MountSave("save", &primary) == RES_OK && !strcmp(mounted, "/saves/game"));
        assert(h_fs_MountSave("save2", &secondary) == RES_OK && !strcmp(mounted, "/saves/game_user2"));
        assert(h_fs_MountSave("device-fallback", NULL) == RES_OK && !strcmp(mounted, "/saves/game"));
    } else if (!strcmp(test, "unknown_save")) {
        assert(h_fs_MountSave("save", &unknown) != RES_OK && !mount_calls);
    } else if (!strcmp(test, "overflow_save")) {
        assert(h_fs_MountSave("save", &primary) != RES_OK && !mount_calls);
    } else if (!strcmp(test, "secondary_overflow")) {
        assert(h_fs_MountSave("save2", &secondary) != RES_OK && !mount_calls);
    } else if (!strcmp(test, "nickname")) {
        char nick[33];
        assert(h_acc_GetNick(nick, &primary) == RES_OK && !strcmp(nick, "Alex"));
        assert(h_acc_GetNick(nick, &secondary) == RES_OK && !strcmp(nick, "Alex 2"));
    } else if (!strcmp(test, "nickname_utf8")) {
        // Decode ASCII transport to the exact UTF-8 bytes: Windows' wide-to-narrow environment conversion uses its code page.
        const char *hex = getenv("DM_NICK"); char utf8[33]; size_t length = strlen(hex) / 2;
        assert(length <= 32);
        for (size_t i = 0; i < length; i++) { unsigned byte; assert(sscanf(hex + 2 * i, "%2x", &byte) == 1); utf8[i] = (char)byte; }
        utf8[length] = 0;
        test_nickname = utf8;
        char nick[33], expected[33]; const char *base = getenv("DM_NICK");
        size_t prefix = (size_t)atoi(argv[2]);
        assert(strlen(base) <= 32 && prefix <= 30);
        assert(h_acc_GetNick(nick, &primary) == RES_OK && !strcmp(nick, base));
        memcpy(expected, base, prefix); memcpy(expected + prefix, " 2", 3);
        assert(h_acc_GetNick(nick, &secondary) == RES_OK && !strcmp(nick, expected));
    } else { assert(!"unknown test"); }
    return 0;
}
