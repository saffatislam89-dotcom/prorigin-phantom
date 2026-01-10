
"""
input_control.py

Cross-platform minimal input synthesis utilities.

Public API:
    - move_mouse(x: int, y: int) -> bool
    - click_mouse(button: str = "left") -> bool
    - type_text(text: str) -> bool

Design & safety:
- Uses only the Python standard library.
- Does not use shell=True.
- Does not execute anything at import time.
- Validates inputs and returns False on any error (no exceptions propagated).
- Integrates with os_capabilities.supports_feature("keyboard_mouse"): if unsupported, functions return False.
- Best-effort, non-blocking actions. No persistent hooks/listeners.
- Python 3.10+ compatible.

Notes:
- Windows: implements using ctypes + Win32 SendInput / SetCursorPos with Unicode keyboard events.
- Linux: attempts X11 + XTest via ctypes (libX11 + libXtst).
- macOS: attempts CoreGraphics (Quartz) via ctypes; this is best-effort and guarded.
- If any platform-specific libraries or calls are not available, functions return False.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from typing import Optional, Tuple

# ---------------------------
# Utility helpers (no actions)
# ---------------------------


def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _check_feature_supported() -> bool:
    """
    Import os_capabilities.supports_feature("keyboard_mouse") at call-time.
    Return False on any problem.
    """
    try:
        from os_capabilities import supports_feature  # type: ignore

        return bool(supports_feature("keyboard_mouse"))
    except Exception:
        return False


def _valid_int_coord(v) -> bool:
    try:
        # Accept ints but reject floats and other types
        if isinstance(v, bool):
            return False
        return isinstance(v, int)
    except Exception:
        return False


def _valid_button(button: str) -> bool:
    return button in ("left", "right", "middle")


# ---------------------------
# Windows implementation
# ---------------------------


def _win_move_mouse(x: int, y: int) -> bool:
    try:
        import ctypes.wintypes as wintypes

        user32 = ctypes.windll.user32  # type: ignore
        # BOOL SetCursorPos(int X, int Y);
        res = user32.SetCursorPos(wintypes.INT(x), wintypes.INT(y))
        return bool(res)
    except Exception:
        return False


def _win_click_mouse(button: str) -> bool:
    try:
        import ctypes.wintypes as wintypes

        user32 = ctypes.windll.user32  # type: ignore

        # Use SendInput for mouse events
        PUL = ctypes.POINTER(ctypes.c_ulong)

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]

        # Constants
        INPUT_MOUSE = 0
        MOUSEEVENTF_MOVE = 0x0001
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        MOUSEEVENTF_RIGHTDOWN = 0x0008
        MOUSEEVENTF_RIGHTUP = 0x0010
        MOUSEEVENTF_MIDDLEDOWN = 0x0020
        MOUSEEVENTF_MIDDLEUP = 0x0040
        # We will use absolute coordinates only for move; clicks can be relative to current pos.

        if button == "left":
            down = MOUSEEVENTF_LEFTDOWN
            up = MOUSEEVENTF_LEFTUP
        elif button == "right":
            down = MOUSEEVENTF_RIGHTDOWN
            up = MOUSEEVENTF_RIGHTUP
        else:
            down = MOUSEEVENTF_MIDDLEDOWN
            up = MOUSEEVENTF_MIDDLEUP

        inp1 = INPUT()
        inp1.type = INPUT_MOUSE
        inp1.union.mi = MOUSEINPUT(0, 0, 0, down, 0, None)

        inp2 = INPUT()
        inp2.type = INPUT_MOUSE
        inp2.union.mi = MOUSEINPUT(0, 0, 0, up, 0, None)

        SendInput = user32.SendInput
        SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
        SendInput.restype = ctypes.c_uint

        arr = (INPUT * 2)(inp1, inp2)
        n = SendInput(2, arr, ctypes.sizeof(INPUT))
        return n == 2
    except Exception:
        return False


def _win_type_text(text: str) -> bool:
    """
    Use SendInput with KEYEVENTF_UNICODE to send Unicode characters.
    """
    try:
        import ctypes.wintypes as wintypes

        user32 = ctypes.windll.user32  # type: ignore

        # Structures
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]

        INPUT_KEYBOARD = 1
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002

        SendInput = user32.SendInput
        SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
        SendInput.restype = ctypes.c_uint

        # Build inputs list
        inputs = []
        for ch in text:
            codepoint = ord(ch)
            # key down
            ki_down = KEYBDINPUT(0, codepoint, KEYEVENTF_UNICODE, 0, None)
            inp_down = INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=ki_down))
            inputs.append(inp_down)
            # key up
            ki_up = KEYBDINPUT(0, codepoint, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)
            inp_up = INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=ki_up))
            inputs.append(inp_up)

        if not inputs:
            return True  # nothing to do

        arr_type = INPUT * len(inputs)
        arr = arr_type(*inputs)
        sent = SendInput(len(arr), arr, ctypes.sizeof(INPUT))
        return sent == len(arr)
    except Exception:
        return False


# ---------------------------
# Linux (X11 + XTest) implementation
# ---------------------------


def _linux_load_xlibs() -> Optional[Tuple[ctypes.CDLL, ctypes.CDLL]]:
    """
    Attempt to load libX11 and libXtst. Return tuple(libX11, libXtst) or None on failure.
    """
    try:
        libx11_name = ctypes.util.find_library("X11")
        libxtst_name = ctypes.util.find_library("Xtst")
        if not libx11_name or not libxtst_name:
            return None
        libx11 = ctypes.CDLL(libx11_name)
        libxtst = ctypes.CDLL(libxtst_name)
        return libx11, libxtst
    except Exception:
        return None


def _linux_move_mouse(x: int, y: int) -> bool:
    try:
        libs = _linux_load_xlibs()
        if not libs:
            return False
        libx11, libxtst = libs
        # Display * XOpenDisplay(char*)
        libx11.XOpenDisplay.restype = ctypes.c_void_p
        libx11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        display = libx11.XOpenDisplay(None)
        if not display:
            return False
        # int XDefaultScreen(Display*)
        libx11.XDefaultScreen.restype = ctypes.c_int
        libx11.XDefaultScreen.argtypes = [ctypes.c_void_p]
        screen = libx11.XDefaultScreen(display)
        # Bool XTestFakeMotionEvent(Display*, int, int, int, unsigned long)
        libxtst.XTestFakeMotionEvent.restype = ctypes.c_int
        libxtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        res = libxtst.XTestFakeMotionEvent(display, screen, ctypes.c_int(x), ctypes.c_int(y), ctypes.c_ulong(0))
        libx11.XFlush(display)
        libx11.XCloseDisplay(display)
        return bool(res)
    except Exception:
        return False


def _linux_click_mouse(button: str) -> bool:
    try:
        libs = _linux_load_xlibs()
        if not libs:
            return False
        libx11, libxtst = libs
        libx11.XOpenDisplay.restype = ctypes.c_void_p
        libx11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        display = libx11.XOpenDisplay(None)
        if not display:
            return False
        # button mapping: left=1, middle=2, right=3
        mapping = {"left": 1, "middle": 2, "right": 3}
        btn = mapping.get(button, 1)
        # int XTestFakeButtonEvent(Display*, unsigned int button, Bool is_press, unsigned long delay)
        libxtst.XTestFakeButtonEvent.restype = ctypes.c_int
        libxtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        down = libxtst.XTestFakeButtonEvent(display, ctypes.c_uint(btn), ctypes.c_int(1), ctypes.c_ulong(0))
        up = libxtst.XTestFakeButtonEvent(display, ctypes.c_uint(btn), ctypes.c_int(0), ctypes.c_ulong(0))
        libx11.XFlush(display)
        libx11.XCloseDisplay(display)
        return bool(down and up)
    except Exception:
        return False


def _linux_type_text(text: str) -> bool:
    try:
        libs = _linux_load_xlibs()
        if not libs:
            return False
        libx11, libxtst = libs
        libx11.XOpenDisplay.restype = ctypes.c_void_p
        libx11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        display = libx11.XOpenDisplay(None)
        if not display:
            return False

        # Functions
        libx11.XKeysymToKeycode.restype = ctypes.c_uint
        libx11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]

        libx11.XStringToKeysym.restype = ctypes.c_ulong
        libx11.XStringToKeysym.argtypes = [ctypes.c_char_p]

        libxtst.XTestFakeKeyEvent.restype = ctypes.c_int
        libxtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]

        for ch in text:
            # Convert character to keysym string e.g., "a" or "A"
            s = ch.encode("utf-8", errors="ignore")
            if not s:
                continue
            # XStringToKeysym expects a bytes string of ASCII keysym, for Unicode this may fail.
            # As a heuristic, for single ASCII characters this works; for others, we skip.
            try:
                keysym = libx11.XStringToKeysym(s)
            except Exception:
                keysym = 0
            if keysym == 0:
                # Non-ASCII attempt: skip
                continue
            keycode = libx11.XKeysymToKeycode(display, keysym)
            if not keycode:
                continue
            # Press
            libxtst.XTestFakeKeyEvent(display, ctypes.c_uint(keycode), ctypes.c_int(1), ctypes.c_ulong(0))
            libxtst.XTestFakeKeyEvent(display, ctypes.c_uint(keycode), ctypes.c_int(0), ctypes.c_ulong(0))
        libx11.XFlush(display)
        libx11.XCloseDisplay(display)
        return True
    except Exception:
        return False


# ---------------------------
# macOS (CoreGraphics) implementation
# ---------------------------


def _mac_load_coregraphics() -> Optional[ctypes.CDLL]:
    try:
        # Try to load CoreGraphics framework
        path = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        return ctypes.CDLL(path)
    except Exception:
        # Try via util
        try:
            name = ctypes.util.find_library("CoreGraphics")
            if name:
                return ctypes.CDLL(name)
        except Exception:
            pass
    return None


def _mac_move_mouse(x: int, y: int) -> bool:
    try:
        core = _mac_load_coregraphics()
        if not core:
            return False

        # typedef struct { double x; double y; } CGPoint;
        class CGPoint(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

        # CGEventRef CGEventCreateMouseEvent(CGEventSourceRef, CGEventType, CGPoint, CGMouseButton);
        core.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        core.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, CGPoint, ctypes.c_int]

        # CGEventPost(CGEventTapLocation, CGEventRef)
        core.CGEventPost.restype = None
        core.CGEventPost.argtypes = [ctypes.c_int, ctypes.c_void_p]

        # Create and post mouse moved event
        kCGEventMouseMoved = 5  # typical constant
        kCGHIDEventTap = 0

        pt = CGPoint(float(x), float(y))
        ev = core.CGEventCreateMouseEvent(None, kCGEventMouseMoved, pt, 0)
        if not ev:
            return False
        core.CGEventPost(kCGHIDEventTap, ev)
        return True
    except Exception:
        return False


def _mac_click_mouse(button: str) -> bool:
    try:
        core = _mac_load_coregraphics()
        if not core:
            return False

        class CGPoint(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

        core.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        core.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, CGPoint, ctypes.c_int]
        core.CGEventPost.restype = None
        core.CGEventPost.argtypes = [ctypes.c_int, ctypes.c_void_p]

        kCGEventLeftMouseDown = 1
        kCGEventLeftMouseUp = 2
        kCGEventRightMouseDown = 3
        kCGEventRightMouseUp = 4
        kCGHIDEventTap = 0

        # Obtain current cursor position via CGEventCreate(NULL)?? Simpler: use (0,0) as click location fallback.
        # Better to use CGEventCreate(None) and CGEventGetLocation but keep minimal:
        # We'll post events at current location by creating events with (0,0) and hoping system uses current pos.
        # Safer: attempt to get location
        try:
            core.CGEventSourceCreate.restype = ctypes.c_void_p
            core.CGEventSourceCreate.argtypes = [ctypes.c_int]
            src = core.CGEventSourceCreate(0)
            # CGEventRef CGEventCreate(None) can give current location
            core.CGEventCreate.restype = ctypes.c_void_p
            ev0 = core.CGEventCreate(None)
            # CGEventGetLocation
            core.CGEventGetLocation.restype = CGPoint
            core.CGEventGetLocation.argtypes = [ctypes.c_void_p]
            loc = core.CGEventGetLocation(ev0)
            x = loc.x
            y = loc.y
        except Exception:
            x = 0.0
            y = 0.0

        pt = CGPoint(float(x), float(y))

        if button == "left":
            down_type = kCGEventLeftMouseDown
            up_type = kCGEventLeftMouseUp
            btn = 0
        elif button == "right":
            down_type = kCGEventRightMouseDown
            up_type = kCGEventRightMouseUp
            btn = 1
        else:
            # macOS doesn't have a distinct middle button constants in older APIs; treat as left.
            down_type = kCGEventLeftMouseDown
            up_type = kCGEventLeftMouseUp
            btn = 0

        ev_down = core.CGEventCreateMouseEvent(None, down_type, pt, btn)
        if not ev_down:
            return False
        core.CGEventPost(kCGHIDEventTap, ev_down)

        ev_up = core.CGEventCreateMouseEvent(None, up_type, pt, btn)
        if not ev_up:
            return False
        core.CGEventPost(kCGHIDEventTap, ev_up)
        return True
    except Exception:
        return False


def _mac_type_text(text: str) -> bool:
    try:
        core = _mac_load_coregraphics()
        if not core:
            return False

        # CGEventRef CGEventCreateKeyboardEvent(CGEventSourceRef, CGKeyCode virtualKey, bool keyDown)
        core.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        core.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_ushort, ctypes.c_bool]

        # void CGEventKeyboardSetUnicodeString(CGEventRef event, UniCharCount length, const UniChar *string)
        core.CGEventKeyboardSetUnicodeString.restype = None
        core.CGEventKeyboardSetUnicodeString.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]

        core.CGEventPost.restype = None
        core.CGEventPost.argtypes = [ctypes.c_int, ctypes.c_void_p]

        kCGEventKeyDown = 10
        kCGEventKeyUp = 11
        kCGHIDEventTap = 0

        for ch in text:
            # Create a keyboard event with virtual key 0 and assign unicode string
            ev_down = core.CGEventCreateKeyboardEvent(None, 0, True)
            if not ev_down:
                continue
            # Prepare UTF-16 (UniChar) array
            uni = (ctypes.c_uint16 * 1)(ord(ch))
            core.CGEventKeyboardSetUnicodeString(ev_down, 1, ctypes.cast(uni, ctypes.c_void_p))
            core.CGEventPost(kCGHIDEventTap, ev_down)

            ev_up = core.CGEventCreateKeyboardEvent(None, 0, False)
            if ev_up:
                uni2 = (ctypes.c_uint16 * 1)(ord(ch))
                core.CGEventKeyboardSetUnicodeString(ev_up, 1, ctypes.cast(uni2, ctypes.c_void_p))
                core.CGEventPost(kCGHIDEventTap, ev_up)
        return True
    except Exception:
        return False


# ---------------------------
# Public API
# ---------------------------


def move_mouse(x: int, y: int) -> bool:
    """
    Move the mouse pointer to absolute screen coordinates (x, y).

    Returns True if the request was initiated successfully, False otherwise.
    """
    try:
        if not _valid_int_coord(x) or not _valid_int_coord(y):
            return False
        if not _check_feature_supported():
            return False

        if _is_windows():
            return _win_move_mouse(x, y)
        if _is_linux():
            return _linux_move_mouse(x, y)
        if _is_macos():
            return _mac_move_mouse(x, y)
        return False
    except Exception:
        return False


def click_mouse(button: str = "left") -> bool:
    """
    Perform a mouse click using the specified button.
    button: "left", "right", or "middle"

    Returns True if the request was initiated successfully, False otherwise.
    """
    try:
        if not isinstance(button, str):
            return False
        button_norm = button.strip().lower()
        if not _valid_button(button_norm):
            return False
        if not _check_feature_supported():
            return False

        if _is_windows():
            return _win_click_mouse(button_norm)
        if _is_linux():
            return _linux_click_mouse(button_norm)
        if _is_macos():
            return _mac_click_mouse(button_norm)
        return False
    except Exception:
        return False


def type_text(text: str) -> bool:
    """
    Type the given text string as keyboard input (best-effort).

    Returns True if the request was initiated successfully, False otherwise.
    """
    try:
        if not isinstance(text, str):
            return False
        # Empty string is a no-op success
        if text == "":
            return True
        if not _check_feature_supported():
            return False

        if _is_windows():
            return _win_type_text(text)
        if _is_linux():
            return _linux_type_text(text)
        if _is_macos():
            return _mac_type_text(text)
        return False
    except Exception:
        return False
