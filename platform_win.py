"""
WinAPI хелперы для Windows 10/11: DWM, темная тема, window chrome.
"""

import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth",     ctypes.c_int),
            ("cxRightWidth",    ctypes.c_int),
            ("cyTopHeight",     ctypes.c_int),
            ("cyBottomHeight",  ctypes.c_int),
        ]

    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi

    # Window Messages
    WM_NCCALCSIZE = 0x0083
    WM_NCHITTEST   = 0x0084
    WM_GETMINMAXINFO = 0x0024

    # Hit Test Codes
    HTNOWHERE = 0
    HTCLIENT  = 1
    HTCAPTION = 2
    HTMINBUTTON = 8
    HTMAXBUTTON = 9
    HTCLOSE   = 20
    HTLEFT    = 10
    HTRIGHT   = 11
    HTTOP     = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM  = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17

    # DWM Attributes
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWA_CAPTION_COLOR = 35
    DWMWA_TEXT_COLOR = 36
    DWMWA_SYSTEMBACKDROP_TYPE = 38 # Чтобы вырубить Mica
