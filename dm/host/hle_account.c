// nn::account: the real device manages users via the acc:u0 service; the host supplies stable local users.
// Online accounts (network service account / Nintendo Account authorization / tokens) are out of scope and uniformly return RES_FAIL; the async context's completion event fires immediately.
// Environment: DM_LOCAL_USERS=1..8 (default one), DM_NICK=primary nickname (default Player).
#include "hle.h"
#include "local_users.h"
#include <stdatomic.h>

typedef dm_local_uid Uid;                             // nn::account::Uid, 16 bytes
typedef struct { uint64_t v[3]; } UserHandle;          // nn::account::UserHandle, 24 bytes
_Static_assert(sizeof(Uid) == 16, "Uid");
typedef struct AccountSession { struct AccountSession *next; uint64_t token; int user; } AccountSession;
static AccountSession *g_sessions;
static uint64_t g_next_token;
static unsigned g_open[DM_LOCAL_USER_MAX];
static int g_last_user;   // the primary is the launcher's preselected identity until a user is opened
static atomic_flag g_account_lock = ATOMIC_FLAG_INIT;
static void account_lock(void) { while (atomic_flag_test_and_set_explicit(&g_account_lock, memory_order_acquire)) {} }
static void account_unlock(void) { atomic_flag_clear_explicit(&g_account_lock, memory_order_release); }

static Result account_open(UserHandle *h, const Uid *uid) {
    int user = dm_local_user_index(uid);
    if (!h || user < 0) return RES_FAIL;
    AccountSession *s = malloc(sizeof *s);
    if (!s) return RES_FAIL;
    account_lock();
    if (g_next_token == UINT64_MAX) { account_unlock(); free(s); return RES_FAIL; }
    s->token = ++g_next_token; s->user = user; s->next = g_sessions; g_sessions = s;
    g_open[user]++; g_last_user = user;
    h->v[0] = uid->v[0]; h->v[1] = uid->v[1]; h->v[2] = s->token;
    account_unlock();
    return RES_OK;
}

// Caller holds the account lock. The token distinguishes separate handles for the same UID and rejects stale closes.
static AccountSession **account_session(const UserHandle *h) {
    AccountSession **p = &g_sessions;
    int user = h ? dm_local_user_index(h->v) : -1;
    while (*p && ((*p)->token != h->v[2] || (*p)->user != user)) p = &(*p)->next;
    return p;
}

static Result account_list(int *n, Uid *out, int max, int open_only) {
    if (!n || max < 0 || (max && !out)) return RES_FAIL;
    *n = 0; account_lock();
    for (int i = 0; i < dm_local_user_count() && *n < max; i++)
        if (!open_only || g_open[i]) out[(*n)++] = dm_local_user_uid(i);
    account_unlock(); return RES_OK;
}

HLE_FORCE("_ZN2nn7account10InitializeEv", "acc:u0; stable local users configured before launch", void, h_acc_Init, void) {}

HLE_FORCE("_ZN2nn7account13ListOpenUsersEPiPNS0_3UidEi", "list the local users with live account handles", Result, h_acc_ListOpen, int *n, Uid *out, int max) { return account_list(n, out, max, 1); }
HLE_FORCE("_ZN2nn7account12ListAllUsersEPiPNS0_3UidEi", "list configured local users", Result, h_acc_ListAll, int *n, Uid *out, int max) { return account_list(n, out, max, 0); }

// Public UserSelectionSettings ABI: https://switchbrew.github.io/libnx/structPselUserSelectionSettings.html
typedef struct { Uid invalid[8]; uint8_t skip, network_required, show_skip, additional, unqualified; } UserSelectionSettings;
_Static_assert(offsetof(UserSelectionSettings, network_required) == 0x81, "UserSelectionSettings network flag");
_Static_assert(offsetof(UserSelectionSettings, additional) == 0x83, "UserSelectionSettings additional flag");
HLE_FORCE("_ZN2nn7account16ShowUserSelectorEPNS0_3UidERKNS0_21UserSelectionSettingsE", "select an eligible local user; additional selection excludes open users", Result, h_acc_ShowSel, Uid *out, const void *settings) {
    if (!out) return RES_FAIL;
    const UserSelectionSettings *s = settings;
    if (s && s->network_required) return RES_FAIL;   // no local user has a linked Nintendo Account
    account_lock();
    for (int i = 0; i < dm_local_user_count(); i++) {
        if (s && s->additional && g_open[i]) continue;
        Uid uid = dm_local_user_uid(i); int excluded = 0;
        for (int j = 0; s && j < 8; j++)
            if (s->invalid[j].v[0] == uid.v[0] && s->invalid[j].v[1] == uid.v[1]) excluded = 1;
        if (!excluded) { *out = uid; account_unlock(); return RES_OK; }
    }
    account_unlock(); return RES_FAIL;
}
// Take the users the system opened on the application's behalf (Mario 1.2.1 asks this first and falls back to TryOpenPreselectedUser on 0; the game only reads the count, not the return value):
// the host has no such users and returns 0, so the game opens the preselected user itself, as in v0
HLE_FORCE("_ZN2nn7account12PopOpenUsersEPiPNS0_10UserHandleEi", "users opened by the system: none (the game falls back to the preselected user)", void, h_acc_PopOpen, int *n, UserHandle *out, int max) { (void)out; (void)max; *n = 0; }
// Hand the open users to the next program of a multi-program application (Octopath Traveler 0 imports it with oe::ExecuteProgram): the host runs one program, so there is nothing to hand over
HLE_FORCE("_ZN2nn7account13PushOpenUsersEv", "hand the open users to the next program: the host runs only this one", void, h_acc_PushOpen, void) {}
HLE_FORCE("_ZN2nn7account22TryOpenPreselectedUserEPNS0_10UserHandleE", "open the primary user preselected at launch (returns bool)", unsigned, h_acc_TryOpenPre, UserHandle *h) {
    Uid uid = dm_local_user_uid(0); return account_open(h, &uid) == RES_OK;
}
// The aborting form (Super Mario Odyssey, SDK 7): without the hook the SDK's IPC call fails and aborts with no message. In SDK 6 the same symbol returns a Result, and Fire Emblem: Three Houses
// skips its save mount when it is non-zero (main+0x53b7e0); returning void left the handle pointer in w0, so the game never mounted "save" and its loading screen waited forever for save:/system.
// It returns 0 now, which SDK 7+ callers ignore
HLE_FORCE("_ZN2nn7account19OpenPreselectedUserEPNS0_10UserHandleE", "open the primary user preselected at launch (Result in SDK 6, later versions abort on failure)", Result, h_acc_OpenPre, UserHandle *h) {
    Uid uid = dm_local_user_uid(0); return account_open(h, &uid);
}
HLE_FORCE("_ZN2nn7account17GetLastOpenedUserEPNS0_3UidE", "most recently opened local user", Result, h_acc_LastOpened, Uid *out) {
    if (!out) return RES_FAIL;
    account_lock(); *out = dm_local_user_uid(g_last_user); account_unlock(); return RES_OK;
}
HLE_FORCE("_ZN2nn7account8OpenUserEPNS0_10UserHandleERKNS0_3UidE", "open an existing local user with a distinct session handle", Result, h_acc_OpenUser, UserHandle *h, const Uid *uid) { return account_open(h, uid); }
HLE_FORCE("_ZN2nn7account9GetUserIdEPNS0_3UidERKNS0_10UserHandleE", "get the Uid from a live account handle", Result, h_acc_GetUserId, Uid *out, const UserHandle *h) {
    if (!out || !h) return RES_FAIL;
    account_lock(); AccountSession *s = *account_session(h);
    if (s) *out = dm_local_user_uid(s->user);
    account_unlock(); return s ? RES_OK : RES_FAIL;
}
// nn::account::Nickname = struct { char name[33]; }, UTF-8
HLE_FORCE("_ZN2nn7account11GetNicknameEPNS0_8NicknameERKNS0_3UidE", "local nickname; DM_NICK with a player number for secondary users", Result, h_acc_GetNick, char *nick, const Uid *uid) {
    int user = dm_local_user_index(uid);
    if (!nick || user < 0) return RES_FAIL;
    const char *e = getenv("DM_NICK");
    memset(nick, 0, 33);
    if (user) {
        const char *base = e ? e : "Player";
        size_t n = strlen(base);
        if (n > 30) {
            n = 30;
            while (n && ((unsigned char)base[n] & 0xc0) == 0x80) n--;   // keep a complete UTF-8 prefix before the suffix
        }
        memcpy(nick, base, n); nick[n] = ' '; nick[n + 1] = (char)('1' + user);
    }
    else strncpy(nick, e ? e : "Player", 32);
    return RES_OK;
}

// ---------- Online accounts: cut ----------
HLE_FORCE("_ZN2nn7account36EnsureNetworkServiceAccountAvailableERKNS0_10UserHandleE", "network service account, out of scope; cut: always unavailable", Result, h_acc_EnsureNsa, const UserHandle *h) { (void)h; return RES_FAIL; }
HLE_FORCE("_ZN2nn7account26GetNetworkServiceAccountIdEPNS0_23NetworkServiceAccountIdERKNS0_10UserHandleE", "network service account, out of scope; cut", Result, h_acc_GetNsaId, void *id, const UserHandle *h) { (void)id; (void)h; return RES_FAIL; }
HLE_FORCE("_ZN2nn7account37LoadNetworkServiceAccountIdTokenCacheEPmPcmRKNS0_10UserHandleE", "network service account token, out of scope; cut", Result, h_acc_LoadTok, uint64_t *n, char *buf, uint64_t sz, const UserHandle *h) {
    (void)buf; (void)sz; (void)h; if (n) *n = 0; return RES_FAIL;
}
HLE_FORCE("_ZN2nn7account40ShowLicenseRequirementsForNetworkServiceERKNS0_10UserHandleE", "online membership notice applet, out of scope; cut", Result, h_acc_ShowLic, const UserHandle *h) { (void)h; return RES_FAIL; }
// The Nintendo Account's cached profile (birthday, country): no Nintendo Account is linked on the host, so loading fails and the game skips its getters (Big Brain Academy: Brain vs. Brain, main+0xab8bc)
HLE_FORCE("_ZN2nn7account29LoadCachedNintendoAccountInfoEPNS0_25CachedNintendoAccountInfoERKNS0_10UserHandleEPvm", "cached Nintendo Account info: none linked, fails", Result, h_acc_LoadNaInfo,
          void *info, const UserHandle *h, void *buf, uint64_t sz) { (void)info; (void)h; (void)buf; (void)sz; return RES_FAIL; }

// AsyncContext / NintendoAccountAuthorizationRequestContext: object contents are read and written only by the interfaces below; construction writes no memory, the completion event fires immediately, and the result is always failure
HLE_FORCE("_ZN2nn7account12AsyncContextC1Ev", "async context constructor; the host creates no IPC object", void, h_acc_AcCtor, void *self) { (void)self; }
HLE_FORCE("_ZN2nn7account44EnsureNetworkServiceAccountIdTokenCacheAsyncEPNS0_12AsyncContextERKNS0_10UserHandleE", "network service account token, out of scope; cut", Result, h_acc_EnsureTokAsync, void *ctx, const UserHandle *h) { (void)ctx; (void)h; return RES_FAIL; }
HLE_FORCE("_ZN2nn7account12AsyncContext14GetSystemEventEPNS_2os11SystemEventE", "async completion event; fires immediately", Result, h_acc_AcGetEv, void *self, void *ev) { (void)self; hle_signal_system_event(ev); return RES_OK; }
HLE_FORCE("_ZN2nn7account12AsyncContext9GetResultEv", "async result; networking is cut, always fails", Result, h_acc_AcGetRes, void *self) { (void)self; return RES_FAIL; }
HLE_FORCE("_ZN2nn7account42NintendoAccountAuthorizationRequestContextC1Ev", "Nintendo Account authorization, out of scope; the constructor writes no memory", void, h_acc_NaCtor, void *self) { (void)self; }
HLE_FORCE("_ZN2nn7account42NintendoAccountAuthorizationRequestContextD1Ev", "Nintendo Account authorization, out of scope", void, h_acc_NaDtor, void *self) { (void)self; }
HLE_FORCE("_ZN2nn7account41CreateNintendoAccountAuthorizationRequestEPNS0_42NintendoAccountAuthorizationRequestContextERKNS0_10UserHandleERKNS0_45NintendoAccountAuthorizationRequestParametersEPvm",
          "Nintendo Account authorization, out of scope; cut", Result, h_acc_NaCreate, void *ctx, const UserHandle *h, const void *prm, void *buf, uint64_t sz) {
    (void)ctx; (void)h; (void)prm; (void)buf; (void)sz; return RES_FAIL;
}
HLE_FORCE("_ZN2nn7account42NintendoAccountAuthorizationRequestContext14GetSystemEventEPNS_2os11SystemEventE", "authorization completion event; fires immediately", Result, h_acc_NaGetEv, void *self, void *ev) { (void)self; hle_signal_system_event(ev); return RES_OK; }
HLE_FORCE("_ZN2nn7account42NintendoAccountAuthorizationRequestContext34GetResultWithInteractionIfRequiredEv", "authorization result; always fails", Result, h_acc_NaGetRes, void *self) { (void)self; return RES_FAIL; }
HLE_FORCE("_ZN2nn7account42NintendoAccountAuthorizationRequestContext10GetIdTokenEPmPcm", "authorization token; always fails", Result, h_acc_NaGetTok, void *self, uint64_t *n, char *buf, uint64_t sz) {
    (void)self; (void)buf; (void)sz; if (n) *n = 0; return RES_FAIL;
}
HLE_FORCE("_ZN2nn7account42NintendoAccountAuthorizationRequestContext20GetAuthorizationCodeEPmPcm", "authorization code; always fails", Result, h_acc_NaGetCode, void *self, uint64_t *n, char *buf, uint64_t sz) {
    (void)self; (void)buf; (void)sz; if (n) *n = 0; return RES_FAIL;
}
HLE_FORCE("_ZN2nn7account42NintendoAccountAuthorizationRequestContext8GetStateEPmPcm", "authorization state string; always fails", Result, h_acc_NaGetState, void *self, uint64_t *n, char *buf, uint64_t sz) {
    (void)self; (void)buf; (void)sz; if (n) *n = 0; return RES_FAIL;
}

// ---------- Account interfaces used by newer SDKs: user enumeration / existence / profile image, the remaining AsyncContext members ----------
HLE_FORCE("_ZN2nn7account12GetUserCountEPi", "configured local user count", Result, h_acc_UserCount, int *n) { if (!n) return RES_FAIL; *n = dm_local_user_count(); return RES_OK; }
HLE_FORCE("_ZN2nn7account18ListQualifiedUsersEPiPNS0_3UidEi", "all local users qualify for offline play", Result, h_acc_ListQual, int *n, Uid *out, int max) { return account_list(n, out, max, 0); }
HLE_FORCE("_ZN2nn7account16GetUserExistenceEPbRKNS0_3UidE", "whether the configured local user exists", Result, h_acc_Exists, uint8_t *out, const Uid *uid) {
    if (!out) return RES_FAIL;
    *out = dm_local_user_index(uid) >= 0; return RES_OK;
}
HLE_FORCE("_ZN2nn7account15ShowUserCreatorEv", "user creation applet; the host already has its local user", Result, h_acc_ShowCreator, void) { return RES_OK; }
HLE_FORCE("_ZN2nn7account16LoadProfileImageEPmPvmRKNS0_3UidE", "user profile image; the host has none (fails)", Result, h_acc_LoadImage, uint64_t *n, void *buf, uint64_t sz, const Uid *uid) {
    (void)buf; (void)sz; (void)uid; if (n) *n = 0; return RES_FAIL;
}
// The save-data thumbnail is what the system's data management screen shows next to a save (The Great Ace Attorney Chronicles, SDK 10); the host has no such screen and keeps none
HLE_FORCE("_ZN2nn7account27StoreSaveDataThumbnailImageERKNS0_3UidEPKvm", "save-data thumbnail for the system's data management screen; the host keeps none", Result, h_acc_StoreThumb, const Uid *uid, const void *img, uint64_t n) {
    (void)uid; (void)img; (void)n; return RES_OK;
}
HLE_FORCE("_ZN2nn7account28DeleteSaveDataThumbnailImageERKNS0_3UidE", "save-data thumbnail; the host keeps none", Result, h_acc_DeleteThumb, const Uid *uid) { (void)uid; return RES_OK; }
HLE_FORCE("_ZN2nn7account32IsNetworkServiceAccountAvailableEPbRKNS0_10UserHandleE", "network service account, out of scope; always unavailable", Result, h_acc_NsaAvail, uint8_t *out, const UserHandle *h) { (void)h; *out = 0; return RES_OK; }
HLE_FORCE("_ZN2nn7account9CloseUserERKNS0_10UserHandleE", "close a live local account handle", void, h_acc_CloseUser, const UserHandle *h) {
    if (!h) return;
    account_lock(); AccountSession **p = account_session(h), *s = *p;
    if (s) { *p = s->next; g_open[s->user]--; }
    account_unlock(); free(s);
}
HLE_FORCE("_ZN2nn7account12AsyncContext6CancelEv", "async context cancel; no request", Result, h_acc_AcCancel, void *self) { (void)self; return RES_OK; }
HLE_FORCE("_ZN2nn7account12AsyncContext7HasDoneEPb", "async context: always done", Result, h_acc_AcHasDone, void *self, uint8_t *done) { (void)self; *done = 1; return RES_OK; }
HLE_FORCE("_ZN2nn7account12AsyncContextD1Ev", "async context destructor; no session to close", void, h_acc_AcDtor, void *self) { (void)self; }
HLE_FORCE("_ZN2nn7account12AsyncContextaSEOS1_", "async context move assignment; the object holds no host state", void *, h_acc_AcMove, void *self, void *other) { (void)other; return self; }
