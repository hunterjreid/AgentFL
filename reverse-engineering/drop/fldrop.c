/* In-process pointer for FL Studio: file drops, clicks and drags.
 *
 * Loaded into FL by a WH_GETMESSAGE hook, so it runs on FL's UI thread, the
 * only thread FL's handlers expect to be called on. Two registered messages
 * drive it:
 *
 *   AgentFL.Drop   plays DragEnter/DragOver/Drop against a window's own
 *                  IDropTarget, exactly what Explorer does when a file is
 *                  released over FL. Adds channels, loads plugins and effects,
 *                  places audio clips.
 *   AgentFL.Mouse  sends mouse messages to the window under the agent's
 *                  pointer. Places pattern clips, presses canvas buttons.
 *
 * FL does not trust the coordinates it is handed. It asks the system where
 * the cursor is and whether a button is down. For the length of one action,
 * every module in FL has those questions pointed here and answered from the
 * agent's pointer. The physical cursor is never moved, and nothing outside
 * FL's process sees any change.
 *
 * Requests arrive as files in %TEMP% (agentfl_drop.request,
 * agentfl_mouse.request); results are written beside them.
 */
#define COBJMACROS
#include <windows.h>
#include <ole2.h>
#include <shlobj.h>
#include <tlhelp32.h>
#include <stdio.h>

static UINT g_drop_msg, g_mouse_msg;
static POINT g_fake;
static int g_lbtn, g_rbtn, g_ctrl;
static HMODULE g_self;
static MSG *g_curmsg;   /* the trigger message; its pt is the cursor FL's framework sees */

/* ---- the fake pointer ---------------------------------------------------- */

static BOOL WINAPI fake_GetCursorPos(LPPOINT p) { if (p) *p = g_fake; return TRUE; }
static BOOL WINAPI fake_GetPhysicalCursorPos(LPPOINT p) { if (p) *p = g_fake; return TRUE; }
static DWORD WINAPI fake_GetMessagePos(void) { return MAKELONG((SHORT)g_fake.x, (SHORT)g_fake.y); }
static BOOL WINAPI fake_GetCursorInfo(PCURSORINFO ci)
{
    if (!ci) return FALSE;
    ci->flags = CURSOR_SHOWING;
    ci->hCursor = GetCursor();
    ci->ptScreenPos = g_fake;
    return TRUE;
}
static SHORT WINAPI fake_GetAsyncKeyState(int vk)
{
    if (vk == VK_LBUTTON) return g_lbtn ? (SHORT)0x8000 : 0;
    if (vk == VK_RBUTTON) return g_rbtn ? (SHORT)0x8000 : 0;
    if (vk == VK_CONTROL || vk == VK_LCONTROL) return g_ctrl ? (SHORT)0x8000 : 0;
    return GetAsyncKeyState(vk);
}
static SHORT WINAPI fake_GetKeyState(int vk)
{
    if (vk == VK_LBUTTON) return g_lbtn ? (SHORT)0x8000 : 0;
    if (vk == VK_RBUTTON) return g_rbtn ? (SHORT)0x8000 : 0;
    if (vk == VK_CONTROL || vk == VK_LCONTROL) return g_ctrl ? (SHORT)0x8000 : 0;
    return GetKeyState(vk);
}

/* FL finds the window under the cursor with WindowFromPoint, which answers
   with whatever is visually on top. When another app covers FL there, FL
   finds nothing and its handler throws. At the agent's pointer the answer
   is FL's own window, whatever sits in front of it. */
static HWND g_root;
static HWND deepest_at(HWND root, POINT sp);
/* The real implementation, saved when user32's own slot is swapped, so the
   fallback never loops back through the fake. */
static HWND (WINAPI *g_real_wfp)(POINT);

static HWND WINAPI fake_WindowFromPoint(POINT p)
{
    /* Any point inside FL, not just the exact agent point: FL converts
       between logical and physical coordinates before asking, so the point
       it asks about is rarely bit-identical to the one it was given. */
    RECT r;
    if (g_root && GetWindowRect(g_root, &r) && PtInRect(&r, p)) return deepest_at(g_root, p);
    return g_real_wfp ? g_real_wfp(p) : WindowFromPoint(p);
}
static HWND WINAPI fake_WindowFromPhysicalPoint(POINT p) { return fake_WindowFromPoint(p); }

/* FL treats input as belonging to it only while it is the active app. The
   agent acts while the human is focused elsewhere, so for one action FL is
   told it is in front. */
static HWND WINAPI fake_GetForegroundWindow(void) { return g_root ? g_root : GetForegroundWindow(); }
static HWND WINAPI fake_GetActiveWindow(void) { return g_root ? g_root : GetActiveWindow(); }

static const struct { const char *name; void *fake; } FAKES[] = {
    {"GetForegroundWindow", fake_GetForegroundWindow},
    {"GetActiveWindow", fake_GetActiveWindow},
    {"WindowFromPoint", fake_WindowFromPoint},
    {"WindowFromPhysicalPoint", fake_WindowFromPhysicalPoint},
    {"GetCursorPos", fake_GetCursorPos},
    {"GetPhysicalCursorPos", fake_GetPhysicalCursorPos},
    {"GetCursorInfo", fake_GetCursorInfo},
    {"GetMessagePos", fake_GetMessagePos},
    {"GetAsyncKeyState", fake_GetAsyncKeyState},
    {"GetKeyState", fake_GetKeyState},
};
#define NFAKES (sizeof FAKES / sizeof FAKES[0])

static struct { void **slot; void *orig; } g_patched[1024];
static int g_npatched;

static void set_slot(void **slot, void *value)
{
    DWORD old;
    VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old);
    *slot = value;
    VirtualProtect(slot, sizeof(void *), old, &old);
}

static int patch_table(BYTE *base, IMAGE_THUNK_DATA *names, IMAGE_THUNK_DATA *addrs,
                       FILE *log, const wchar_t *modname, const char *kind)
{
    int hits = 0;
    for (; names->u1.AddressOfData; names++, addrs++) {
        if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal)) continue;
        const char *fn = (char *)((IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData))->Name;
        for (int i = 0; i < (int)NFAKES; i++) {
            if (strcmp(fn, FAKES[i].name)) continue;
            if (g_npatched >= 1024) return hits;
            void **slot = (void **)&addrs->u1.Function;
            g_patched[g_npatched].slot = slot;
            g_patched[g_npatched].orig = *slot;
            g_npatched++;
            set_slot(slot, FAKES[i].fake);
            if (log) fprintf(log, "  %ls!%s (%s)\n", modname, fn, kind);
            hits++;
        }
    }
    return hits;
}

/* Both the normal and the delay-load import tables. FL's engine delay-loads
   GetPhysicalCursorPos, which the normal table never shows. An unresolved
   delay slot points at a loader stub; overwriting it bypasses the stub and
   restoring puts the stub back, so both states are safe. */
static int patch_module(HMODULE m, FILE *log, const wchar_t *modname)
{
    BYTE *base = (BYTE *)m;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    int hits = 0;
    IMAGE_DATA_DIRECTORY d = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (d.VirtualAddress)
        for (IMAGE_IMPORT_DESCRIPTOR *imp = (IMAGE_IMPORT_DESCRIPTOR *)(base + d.VirtualAddress); imp->Name; imp++) {
            if (_stricmp((char *)(base + imp->Name), "user32.dll") || !imp->OriginalFirstThunk) continue;
            hits += patch_table(base, (IMAGE_THUNK_DATA *)(base + imp->OriginalFirstThunk),
                                (IMAGE_THUNK_DATA *)(base + imp->FirstThunk), log, modname, "import");
        }
    IMAGE_DATA_DIRECTORY dd = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT];
    if (dd.VirtualAddress)
        for (IMAGE_DELAYLOAD_DESCRIPTOR *dl = (IMAGE_DELAYLOAD_DESCRIPTOR *)(base + dd.VirtualAddress); dl->DllNameRVA; dl++) {
            if (_stricmp((char *)(base + dl->DllNameRVA), "user32.dll") || !dl->ImportNameTableRVA) continue;
            hits += patch_table(base, (IMAGE_THUNK_DATA *)(base + dl->ImportNameTableRVA),
                                (IMAGE_THUNK_DATA *)(base + dl->ImportAddressTableRVA), log, modname, "delay");
        }
    return hits;
}

/* Import tables miss anything resolved at runtime through GetProcAddress.
   In user32 each cursor query is a stub that jumps through a pointer slot
   (`[mov edx, n;] jmp [rip+disp]`). Swapping that slot catches every caller
   in the process however it found the function, and it is one pointer write
   with no code rewritten, so it restores cleanly. */
static BOOL WINAPI slot_CursorPos(LPPOINT p, DWORD mode) { if (p) *p = g_fake; return TRUE; }

static void **jmp_slot(BYTE *fn)
{
    for (int i = 0; i < 8; i++) {
        if (fn[i] == 0xFF && fn[i + 1] == 0x25) {
            INT32 disp = *(INT32 *)(fn + i + 2);
            return (void **)(fn + i + 6 + disp);
        }
    }
    return NULL;
}

static void patch_user32_slots(FILE *log)
{
    HMODULE u = GetModuleHandleW(L"user32.dll");
    const struct { const char *name; void *fake; } S[] = {
        {"GetCursorPos", slot_CursorPos},
        {"GetPhysicalCursorPos", slot_CursorPos},
        {"GetCursorInfo", fake_GetCursorInfo},
        {"GetMessagePos", fake_GetMessagePos},
        {"WindowFromPoint", fake_WindowFromPoint},
        {"WindowFromPhysicalPoint", fake_WindowFromPoint},
    };
    for (int i = 0; i < 6; i++) {
        BYTE *fn = (BYTE *)GetProcAddress(u, S[i].name);
        void **slot = fn ? jmp_slot(fn) : NULL;
        if (!slot || g_npatched >= 1024) continue;
        int seen = 0;
        for (int j = 0; j < g_npatched; j++) if (g_patched[j].slot == slot) seen = 1;
        if (seen) continue;   /* GetCursorPos and GetPhysicalCursorPos share one */
        g_patched[g_npatched].slot = slot;
        g_patched[g_npatched].orig = *slot;
        g_npatched++;
        set_slot(slot, S[i].fake);
        if (log) fprintf(log, "  user32 slot %s\n", S[i].name);
    }
}

/* Every module in FL, because FL, its VCL runtime and its plugins each ask
   for the cursor through their own imports. System DLLs are skipped: they
   are the implementation being faked. */
static int fake_pointer_on(POINT at, FILE *log)
{
    g_fake = at;
    if (g_npatched) return g_npatched;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
    if (snap == INVALID_HANDLE_VALUE) return 0;
    MODULEENTRY32W me = { sizeof me };
    for (BOOL ok = Module32FirstW(snap, &me); ok; ok = Module32NextW(snap, &me)) {
        if (me.hModule == g_self) continue;
        if (wcsstr(_wcslwr(me.szExePath), L"\\windows\\")) continue;
        patch_module(me.hModule, log, me.szModule);
    }
    CloseHandle(snap);
    patch_user32_slots(log);
    return g_npatched;
}

static void fake_pointer_off(void)
{
    for (int i = 0; i < g_npatched; i++) set_slot(g_patched[i].slot, g_patched[i].orig);
    g_npatched = 0;
    g_lbtn = g_rbtn = g_ctrl = 0;
}

static void CALLBACK fake_pointer_timer(HWND h, UINT m, UINT_PTR id, DWORD t)
{
    KillTimer(NULL, id);
    fake_pointer_off();
}

/* ---- files -------------------------------------------------------------- */

static void temp_path(wchar_t *out, const wchar_t *name)
{
    wchar_t dir[MAX_PATH];
    GetTempPathW(MAX_PATH, dir);
    size_t n = wcslen(dir);
    if (n && dir[n - 1] == L'\\') dir[n - 1] = 0;
    swprintf(out, MAX_PATH, L"%s\\%s", dir, name);
}

/* Run FL's own message queue for a while, on its own thread. */
static void pump(DWORD ms)
{
    DWORD end = GetTickCount() + ms; MSG m;
    while (GetTickCount() < end) {
        while (PeekMessageW(&m, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageW(&m); }
        Sleep(5);
    }
}

/* ---- drop --------------------------------------------------------------- */

static void do_drop(void)
{
    wchar_t req[MAX_PATH], res[MAX_PATH];
    temp_path(req, L"agentfl_drop.request");
    temp_path(res, L"agentfl_drop.result");
    FILE *o = _wfopen(res, L"w");
    FILE *f = _wfopen(req, L"r, ccs=UTF-8");
    if (!f) { if (o) { fprintf(o, "error no request file\n"); fclose(o); } return; }

    wchar_t line[1024];
    unsigned long long hv = 0; long x = 0, y = 0;
    fgetws(line, 1024, f); hv = _wcstoui64(line, NULL, 10);
    fgetws(line, 1024, f); swscanf(line, L"%ld %ld", &x, &y);

    PIDLIST_ABSOLUTE pidls[32]; int count = 0;
    while (count < 32 && fgetws(line, 1024, f)) {
        size_t l = wcslen(line);
        while (l && (line[l - 1] == L'\n' || line[l - 1] == L'\r')) line[--l] = 0;
        if (l && SUCCEEDED(SHParseDisplayName(line, NULL, &pidls[count], 0, NULL))) count++;
    }
    fclose(f);
    DeleteFileW(req);

    IDropTarget *dt = (IDropTarget *)GetPropW((HWND)(ULONG_PTR)hv, L"OleDropTargetInterface");
    IShellFolder *parent = NULL; PCUITEMID_CHILD first = NULL; IDataObject *data = NULL;
    if (!count) { if (o) fprintf(o, "error no parsable files\n"); goto out; }
    if (!dt) { if (o) fprintf(o, "error window has no drop target\n"); goto out; }

    /* One data object carries files from one folder. */
    HRESULT hr = SHBindToParent(pidls[0], &IID_IShellFolder, (void **)&parent, &first);
    if (FAILED(hr)) { if (o) fprintf(o, "error SHBindToParent 0x%08lx\n", hr); goto out; }
    PCUITEMID_CHILD kids[32];
    for (int i = 0; i < count; i++) kids[i] = ILFindLastID(pidls[i]);
    hr = IShellFolder_GetUIObjectOf(parent, NULL, count, kids, &IID_IDataObject, NULL, (void **)&data);
    IShellFolder_Release(parent);
    if (FAILED(hr)) { if (o) fprintf(o, "error GetUIObjectOf 0x%08lx\n", hr); goto out; }

    POINT at = { x, y };
    if (g_curmsg) g_curmsg->pt = at;
    g_root = GetAncestor((HWND)(ULONG_PTR)hv, GA_ROOT);
    wchar_t lp[MAX_PATH]; temp_path(lp, L"agentfl_patch.log");
    FILE *plog = _wfopen(lp, L"w");
    int patched = fake_pointer_on(at, plog);
    if (plog) fclose(plog);

    POINTL pt = { x, y };
    DWORD all = DROPEFFECT_COPY | DROPEFFECT_MOVE | DROPEFFECT_LINK;
    DWORD eff = all;
    HRESULT h1 = IDropTarget_DragEnter(dt, data, MK_LBUTTON, pt, &eff);
    DWORD e1 = eff;
    /* A real drag spends time between enter, over and drop, with FL's queue
       running. FL sets up its drop state on a message after DragEnter, so
       the steps are spaced the same way. */
    pump(120);
    HRESULT h2 = E_FAIL;
    for (int i = 0; i < 3; i++) {
        eff = all;
        h2 = IDropTarget_DragOver(dt, MK_LBUTTON, pt, &eff);
        pump(40);
    }
    DWORD e2 = SUCCEEDED(h2) ? eff : e1;
    if (e2 == DROPEFFECT_NONE) {
        HRESULT h3 = IDropTarget_DragLeave(dt);
        if (o) fprintf(o, "refused enter=0x%08lx/%lu over=0x%08lx/%lu leave=0x%08lx patched=%d\n", h1, e1, h2, e2, h3, patched);
    } else {
        eff = e2;
        HRESULT h3 = IDropTarget_Drop(dt, data, 0, pt, &eff);
        if (o) fprintf(o, "ok enter=0x%08lx/%lu over=0x%08lx/%lu drop=0x%08lx/%lu files=%d patched=%d\n",
                       h1, e1, h2, e2, h3, eff, count, patched);
    }
    IDataObject_Release(data);
    /* FL can finish a drop on a later message, so the real pointer comes
       back shortly after rather than the moment Drop returns. */
    SetTimer(NULL, 0, 300, fake_pointer_timer);
out:
    for (int i = 0; i < count; i++) CoTaskMemFree(pidls[i]);
    if (o) fclose(o);
}

/* ---- mouse -------------------------------------------------------------- */

static HWND deepest_at(HWND root, POINT sp)
{
    HWND h = root;
    for (;;) {
        POINT cp = sp; ScreenToClient(h, &cp);
        HWND c = RealChildWindowFromPoint(h, cp);
        if (!c || c == h) return h;
        h = c;
    }
}

/* Ops, one per line after the root hwnd, screen coordinates:
   move x y | ldown x y | lup x y | rdown x y | rup x y | wait ms
   wheel x y delta | cwheel x y delta   (cwheel holds Ctrl: FL's zoom) */
static void do_mouse(void)
{
    wchar_t req[MAX_PATH], res[MAX_PATH];
    temp_path(req, L"agentfl_mouse.request");
    temp_path(res, L"agentfl_mouse.result");
    FILE *o = _wfopen(res, L"w");
    FILE *f = _wfopen(req, L"r, ccs=UTF-8");
    if (!f) { if (o) { fprintf(o, "error no request\n"); fclose(o); } return; }
    wchar_t line[256];
    fgetws(line, 256, f);
    HWND root = (HWND)(ULONG_PTR)_wcstoui64(line, NULL, 10);
    g_root = root;

    int patched = -1;
    while (fgetws(line, 256, f)) {
        wchar_t op[16] = {0}; long x = 0, y = 0, z = 0;
        if (swscanf(line, L"%15s %ld %ld %ld", op, &x, &y, &z) < 1) continue;
        if (!wcscmp(op, L"wait")) {
            DWORD end = GetTickCount() + (DWORD)x; MSG m;
            while (GetTickCount() < end) {
                while (PeekMessageW(&m, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageW(&m); }
                Sleep(5);
            }
            continue;
        }
        POINT sp = { x, y };
        patched = fake_pointer_on(sp, NULL);
        HWND cap = GetCapture();
        HWND h = cap ? cap : deepest_at(root, sp);
        POINT cp = sp; ScreenToClient(h, &cp);
        LPARAM l = MAKELPARAM((SHORT)cp.x, (SHORT)cp.y);
        UINT msg = 0;
        if (!wcscmp(op, L"move"))  msg = WM_MOUSEMOVE;
        if (!wcscmp(op, L"ldown")) { g_lbtn = 1; msg = WM_LBUTTONDOWN; }
        if (!wcscmp(op, L"lup"))   { g_lbtn = 0; msg = WM_LBUTTONUP; }
        if (!wcscmp(op, L"rdown")) { g_rbtn = 1; msg = WM_RBUTTONDOWN; }
        if (!wcscmp(op, L"rup"))   { g_rbtn = 0; msg = WM_RBUTTONUP; }
        if (!wcscmp(op, L"wheel") || !wcscmp(op, L"cwheel")) {
            g_ctrl = !wcscmp(op, L"cwheel");
            WPARAM ww = MAKEWPARAM(g_ctrl ? MK_CONTROL : 0, (SHORT)z);
            SendMessageW(h, WM_MOUSEWHEEL, ww, MAKELPARAM((SHORT)x, (SHORT)y));  /* wheel lParam is screen coords */
            g_ctrl = 0;
            wchar_t cls[64]; GetClassNameW(h, cls, 64);
            if (o) fprintf(o, "%ls %ld %ld %ld -> %ls\n", op, x, y, z, cls);
            continue;
        }
        if (!msg) continue;
        WPARAM w = (g_lbtn ? MK_LBUTTON : 0) | (g_rbtn ? MK_RBUTTON : 0);
        SendMessageW(h, WM_SETCURSOR, (WPARAM)h, MAKELPARAM(HTCLIENT, msg));
        SendMessageW(h, msg, w, l);
        wchar_t cls[64]; GetClassNameW(h, cls, 64);
        if (o) fprintf(o, "%ls %ld %ld -> %ls (%ld,%ld)\n", op, x, y, cls, cp.x, cp.y);
    }
    fclose(f);
    DeleteFileW(req);
    fake_pointer_off();
    if (o) { fprintf(o, "done patched=%d\n", patched); fclose(o); }
}

/* ---- entry -------------------------------------------------------------- */

__declspec(dllexport) LRESULT CALLBACK GetMsgProc(int code, WPARAM wp, LPARAM lp)
{
    if (code == HC_ACTION && wp == PM_REMOVE) {
        MSG *m = (MSG *)lp;
        if (!g_drop_msg) g_drop_msg = RegisterWindowMessageW(L"AgentFL.Drop");
        if (!g_mouse_msg) g_mouse_msg = RegisterWindowMessageW(L"AgentFL.Mouse");
        if (m->message == g_drop_msg || m->message == g_mouse_msg) {
            /* Pinned: FL's imports point into this DLL while an action runs,
               and unhooking must never unload it underneath them. */
            GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                               (LPCWSTR)GetMsgProc, &g_self);
            UINT which = m->message;
            m->message = WM_NULL;   /* FL never sees it */
            g_curmsg = m;
            if (which == g_drop_msg) do_drop(); else do_mouse();
        }
    }
    return CallNextHookEx(NULL, code, wp, lp);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD r, LPVOID p) { return TRUE; }
