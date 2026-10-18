"""Bind Microsoft semantic engine PIDs to their owning Desktop processes.

ListLocalInstances.processId is msmdsrv.exe (the engine), NOT the
PBIDesktop.exe PID passed to Bridge. Use a Windows OS snapshot and prove
the direct parent is a live PBIDesktop.exe; never infer PID equality.
"""
from __future__ import annotations

import os


class ProcessOwnershipError(OSError):
    pass


def desktop_owner_pid(engine_pid: int) -> int:
    """Return exact parent Desktop PID or refuse unknown/non-Windows."""
    if type(engine_pid) is not int or engine_pid <= 0:
        raise ProcessOwnershipError("semantic engine process ID invalid")
    if os.name != "nt":
        raise ProcessOwnershipError(
            "Desktop engine ownership requires Windows process evidence")
    import ctypes
    from ctypes import wintypes as w

    class Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", w.DWORD),
            ("cntUsage", w.DWORD),
            ("th32ProcessID", w.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", w.DWORD),
            ("cntThreads", w.DWORD),
            ("th32ParentProcessID", w.DWORD),
            ("pcPriClassBase", w.LONG),
            ("dwFlags", w.DWORD),
            ("szExeFile", w.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32FirstW.restype = w.BOOL
    kernel.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)
    if snapshot == w.HANDLE(-1).value:
        raise ProcessOwnershipError(
            f"Windows process inventory unavailable: {ctypes.get_last_error()}")
    processes: dict[int, tuple[int, str]] = {}
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(entry)
        status = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while status:
            processes[entry.th32ProcessID] = (
                entry.th32ParentProcessID, entry.szExeFile.lower())
            status = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    process = processes.get(engine_pid)
    if process is None or process[1] != "msmdsrv.exe":
        raise ProcessOwnershipError(
            f"semantic engine PID {engine_pid} missing or not msmdsrv.exe")
    parent = processes.get(process[0])
    if parent is None or parent[1] != "pbidesktop.exe":
        raise ProcessOwnershipError(
            "semantic engine direct parent is not a live Power BI Desktop")
    return process[0]
