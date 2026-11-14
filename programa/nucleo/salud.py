"""Cuanto usa el bot del equipo: CPU y memoria (sin dependencias nuevas).

Se mira la ventana y sus procesos (una cuenta por proceso) con las funciones
de Windows; si algo no esta, se devuelve None y la ventana enseña «—».
Nunca lanza excepciones."""
from __future__ import annotations

import os
import time

_ultimo: tuple[float, float] | None = None      # (momento, segundos de CPU)
_cerrojo_valido = ""


def _hijos(pid: int | None = None) -> list[int]:
    """Procesos hijos directos de `pid` (las cuentas, cuando van en procesos)."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]

        class _PE32(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_void_p),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_char * 260)]
        padre = os.getpid() if pid is None else int(pid)
        snap = k32.CreateToolhelp32Snapshot(0x2, 0)          # TH32CS_SNAPPROCESS
        if not snap or snap == ctypes.c_void_p(-1).value:
            return []
        e = _PE32()
        e.dwSize = ctypes.sizeof(_PE32)
        out: list[int] = []
        try:
            if not k32.Process32First(c_void_p_ok(snap), ctypes.byref(e)):
                return []
            while True:
                if e.th32ParentProcessID == padre and e.th32ProcessID != padre:
                    out.append(int(e.th32ProcessID))
                if not k32.Process32Next(c_void_p_ok(snap), ctypes.byref(e)):
                    break
        finally:
            try:
                k32.CloseHandle(c_void_p_ok(snap))
            except Exception:                                # noqa: BLE001
                pass
        return out
    except Exception:                                        # noqa: BLE001
        return []


def c_void_p_ok(manejador):
    """El manejador tal cual (los de Windows son punteros)."""
    import ctypes
    return ctypes.c_void_p(manejador)


def _memoria_mb(pid: int | None = None) -> float | None:
    """Memoria en uso (working set) de un proceso, en MB."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        propio = pid is None
        h = k32.GetCurrentProcess() if propio else k32.OpenProcess(0x1000 | 0x0400, False, int(pid))
        if not h:
            return None
        try:
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            if not ctypes.windll.psapi.GetProcessMemoryInfo(c_void_p_ok(h), ctypes.byref(pmc), pmc.cb):
                return None
            return round(pmc.WorkingSetSize / 1048576.0, 1)
        finally:
            if not propio:
                try:
                    k32.CloseHandle(c_void_p_ok(h))
                except Exception:                            # noqa: BLE001
                    pass
    except Exception:                                        # noqa: BLE001
        return None


def _cpu_s(pid: int | None = None) -> float | None:
    """Segundos de procesador que lleva usado un proceso."""
    if os.name != "nt":
        return None if pid is not None else time.process_time()
    try:
        import ctypes
        from ctypes import wintypes

        class _FT(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        propio = pid is None
        h = k32.GetCurrentProcess() if propio else k32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return None
        try:
            cre, exi, ker, usr = _FT(), _FT(), _FT(), _FT()
            if not k32.GetProcessTimes(c_void_p_ok(h), ctypes.byref(cre), ctypes.byref(exi),
                                       ctypes.byref(ker), ctypes.byref(usr)):
                return None
            seg = lambda ft: ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7   # noqa: E731
            return seg(ker) + seg(usr)
        finally:
            if not propio:
                try:
                    k32.CloseHandle(c_void_p_ok(h))
                except Exception:                            # noqa: BLE001
                    pass
    except Exception:                                        # noqa: BLE001
        return None


def uso() -> dict:
    """{"cpu_pct": %, "memoria_mb": MB, "procesos": n, "equipo_pct": %} del bot.

    La CPU es desde la llamada anterior (hay que llamarlo cada pocos segundos).
    cpu_pct puede pasar de 100 si el bot usa varios nucleos."""
    global _ultimo
    pids = [None] + _hijos()
    cpu_total = 0.0
    mem_total = 0.0
    n = 0
    for p in pids:
        cpu = _cpu_s(p)
        if cpu is not None:
            cpu_total += cpu
            n += 1
        mem = _memoria_mb(p)
        if mem is not None:
            mem_total += mem
    ahora = time.time()
    cpu_pct = None
    if _ultimo is not None and ahora > _ultimo[0]:
        cpu_pct = round(100.0 * (cpu_total - _ultimo[1]) / (ahora - _ultimo[0]), 1)
        cpu_pct = max(0.0, cpu_pct)
    _ultimo = (ahora, cpu_total)
    return {"cpu_pct": cpu_pct, "memoria_mb": round(mem_total, 1) if mem_total else None,
            "procesos": n, "equipo_pct": _equipo_pct()}


def _equipo_pct() -> float | None:
    """Memoria del equipo en uso (para saber si el bot es mucho o poco)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _MEMSTAT(ctypes.Structure):
            _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = _MEMSTAT()
        m.dwLength = ctypes.sizeof(_MEMSTAT)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return None
        return float(m.dwMemoryLoad)
    except Exception:                                        # noqa: BLE001
        return None
