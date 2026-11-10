"""
macos.py - Accorgimenti specifici per macOS.

App Nap: quando DXRotator non è in primo piano (ridotta a icona o coperta),
macOS ne rallenta timer e thread per risparmiare energia. Per il rotore è un
problema: il DCU-1 vuole circa 1,5 s di silenzio esatti prima di AM1; e i
comandi automatici devono partire subito, non dopo qualche secondo.

disable_app_nap() apre una "activity" di NSProcessInfo (la stessa API usata
dalle app native) tramite ctypes, senza dipendenze aggiuntive. Si affianca
alla chiave NSAppSleepDisabled che build.py scrive nell'Info.plist del bundle:
questa vale anche lanciando da sorgente con  python run_dxrotator.py.

Su Windows e Linux non fa nulla.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import sys

log = logging.getLogger(__name__)

# NSActivityOptions (Foundation/NSProcessInfo.h)
_USER_INITIATED_ALLOWING_IDLE_SLEEP = 0x00EFFFFF   # non impedisce lo stop del Mac
_LATENCY_CRITICAL = 0xFF00000000                   # timer e I/O senza ritardi

_activity = None   # va tenuta viva per tutta la durata dell'app


def disable_app_nap(reason: str = "Controllo rotore DXRotator") -> bool:
    """Impedisce ad App Nap di rallentare l'app. True se attivato."""
    global _activity
    if sys.platform != "darwin":
        return False
    if _activity is not None:
        return True
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value

        def call(restype, *argtypes):
            # su arm64 objc_msgSend va chiamato con il prototipo esatto
            return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p,
                                    *argtypes)(send)

        sel = objc.sel_registerName
        info = call(ctypes.c_void_p)(objc.objc_getClass(b"NSProcessInfo"),
                                     sel(b"processInfo"))
        text = call(ctypes.c_void_p, ctypes.c_char_p)(
            objc.objc_getClass(b"NSString"), sel(b"stringWithUTF8String:"),
            reason.encode("utf-8"))
        act = call(ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p)(
            info, sel(b"beginActivityWithOptions:reason:"),
            _USER_INITIATED_ALLOWING_IDLE_SLEEP | _LATENCY_CRITICAL, text)
        if not act:
            log.warning("App Nap: beginActivity non ha restituito nulla")
            return False
        call(ctypes.c_void_p)(act, sel(b"retain"))
        _activity = act
        log.info("App Nap disattivato (activity NSProcessInfo attiva)")
        return True
    except Exception as exc:   # mai bloccare l'avvio per questo
        log.warning("App Nap: impossibile disattivarlo (%s)", exc)
        return False
