"""
File Unlocker Module - PowerShellFileTools
Uses Windows Restart Manager API to detect processes locking a file.
Provides process info and the ability to kill locking processes.
"""

import os
import time
import ctypes
import ctypes.wintypes
from typing import List, Dict


# Windows Restart Manager API constants
RmRebootReasonNone = 0
ERROR_MORE_DATA = 234

# RM_UNIQUE_PROCESS structure (contains process ID + start time)
class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.wintypes.DWORD),
        ("dwHighDateTime", ctypes.wintypes.DWORD),
    ]

class RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwProcessId", ctypes.wintypes.DWORD),
        ("ProcessStartTime", FILETIME),
    ]

# RM_PROCESS_INFO structure (correct full layout)
class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", RM_UNIQUE_PROCESS),
        ("strAppName", ctypes.c_wchar * 256),
        ("strServiceShortName", ctypes.c_wchar * 64),
        ("ApplicationType", ctypes.wintypes.DWORD),
        ("AppStatus", ctypes.wintypes.ULONG),
        ("TSSessionId", ctypes.wintypes.DWORD),
        ("bRestartable", ctypes.wintypes.BOOL),
    ]


def find_locking_processes(file_path: str) -> dict:
    """
    Find processes that have a lock on the given file using the Restart Manager API.

    Returns:
        dict: {
            success: bool,
            processes: [{"pid": int, "name": str, "app_type": str}, ...],
            message: str
        }
    """
    if not os.path.exists(file_path):
        return {"success": False, "processes": [], "message": f"文件不存在: {file_path}"}

    file_path = os.path.abspath(file_path)

    try:
        rstrtmgr = ctypes.WinDLL("Rstrtmgr.dll")

        # Define function signatures explicitly
        rstrtmgr.RmStartSession.restype = ctypes.wintypes.DWORD
        rstrtmgr.RmStartSession.argtypes = [
            ctypes.POINTER(ctypes.wintypes.DWORD),  # pSessionHandle
            ctypes.wintypes.DWORD,                   # dwSessionFlags
            ctypes.c_wchar_p,                        # strSessionKey
        ]

        rstrtmgr.RmRegisterResources.restype = ctypes.wintypes.DWORD
        rstrtmgr.RmRegisterResources.argtypes = [
            ctypes.wintypes.DWORD,                   # dwSessionHandle
            ctypes.wintypes.UINT,                    # nFiles
            ctypes.POINTER(ctypes.c_wchar_p),        # rgsFileNames
            ctypes.wintypes.UINT,                    # nApplications
            ctypes.c_void_p,                         # rgApplications
            ctypes.wintypes.UINT,                    # nServices
            ctypes.c_void_p,                         # rgsServiceNames
        ]

        rstrtmgr.RmGetList.restype = ctypes.wintypes.DWORD
        rstrtmgr.RmGetList.argtypes = [
            ctypes.wintypes.DWORD,                   # dwSessionHandle
            ctypes.POINTER(ctypes.wintypes.UINT),    # pnProcInfoNeeded
            ctypes.POINTER(ctypes.wintypes.UINT),    # pnProcInfo
            ctypes.c_void_p,                         # rgAffectedApps
            ctypes.POINTER(ctypes.wintypes.DWORD),   # lpdwRebootReasons
        ]

        rstrtmgr.RmEndSession.restype = ctypes.wintypes.DWORD
        rstrtmgr.RmEndSession.argtypes = [ctypes.wintypes.DWORD]

        # Step 1: Start session
        session_handle = ctypes.wintypes.DWORD()
        session_key = ctypes.create_unicode_buffer(256)
        session_key.value = "PSFileTools_" + str(os.getpid())

        ret = rstrtmgr.RmStartSession(
            ctypes.byref(session_handle),
            0,
            session_key
        )

        if ret != 0:
            return {"success": False, "processes": [], "message": f"无法启动 RM 会话 (错误码: {ret})"}

        handle = session_handle.value

        try:
            # Step 2: Register the file
            file_array = (ctypes.c_wchar_p * 1)(file_path)

            ret = rstrtmgr.RmRegisterResources(
                handle,
                1,
                file_array,
                0,
                None,
                0,
                None
            )

            if ret != 0:
                return {"success": False, "processes": [], "message": f"无法注册资源 (错误码: {ret})"}

            # Step 3: Get process list
            n_proc_info_needed = ctypes.wintypes.UINT(0)
            n_proc_info = ctypes.wintypes.UINT(0)
            reboot_reasons = ctypes.wintypes.DWORD(0)

            # First call to determine buffer size
            ret = rstrtmgr.RmGetList(
                handle,
                ctypes.byref(n_proc_info_needed),
                ctypes.byref(n_proc_info),
                None,
                ctypes.byref(reboot_reasons)
            )

            # ERROR_MORE_DATA (234) means there are processes; 0 means none.
            # Restart Manager can miss plain file handles, so fall back to psutil.
            if ret == 0 and n_proc_info_needed.value == 0:
                processes = _find_processes_by_open_files(file_path)
                return {
                    "success": True,
                    "processes": processes,
                    "message": f"发现 {len(processes)} 个进程正在占用此文件" if processes else "没有发现占用此文件的进程"
                }

            if ret != ERROR_MORE_DATA and ret != 0:
                processes = _find_processes_by_open_files(file_path)
                if processes:
                    return {
                        "success": True,
                        "processes": processes,
                        "message": f"发现 {len(processes)} 个进程正在占用此文件"
                    }
                return {"success": False, "processes": [], "message": f"RmGetList 失败 (错误码: {ret})"}

            # Allocate and call again
            count = n_proc_info_needed.value
            n_proc_info.value = count
            process_info_array = (RM_PROCESS_INFO * count)()

            ret = rstrtmgr.RmGetList(
                handle,
                ctypes.byref(n_proc_info_needed),
                ctypes.byref(n_proc_info),
                ctypes.cast(process_info_array, ctypes.c_void_p),
                ctypes.byref(reboot_reasons)
            )

            if ret != 0:
                return {"success": False, "processes": [], "message": f"获取进程列表失败 (错误码: {ret})"}

            # Extract results
            processes = []
            app_type_map = {
                0: "未知类型",
                1: "主窗口程序",
                2: "系统服务",
                3: "资源管理器",
                4: "控制台程序",
                5: "其他"
            }

            for i in range(n_proc_info.value):
                info = process_info_array[i]
                pid = info.Process.dwProcessId
                name = info.strAppName.strip() or f"进程 {pid}"

                processes.append({
                    "pid": pid,
                    "name": name,
                    "service_name": info.strServiceShortName,
                    "app_type": app_type_map.get(info.ApplicationType, f"类型{info.ApplicationType}"),
                    "restartable": bool(info.bRestartable),
                })

            # Merge psutil fallback results to catch plain open file handles.
            existing_pids = {p["pid"] for p in processes}
            for process in _find_processes_by_open_files(file_path):
                if process["pid"] not in existing_pids:
                    processes.append(process)
                    existing_pids.add(process["pid"])

            return {
                "success": True,
                "processes": processes,
                "message": f"发现 {len(processes)} 个进程正在占用此文件" if processes else "没有发现占用此文件的进程"
            }

        finally:
            rstrtmgr.RmEndSession(handle)

    except Exception as e:
        return {"success": False, "processes": [], "message": f"查找占用进程失败: {str(e)}"}


def _find_processes_by_open_files(file_path: str, timeout: float = 2.0) -> list:
    """Fallback scanner for normal open file handles not reported by Restart Manager."""
    try:
        import psutil
    except ImportError:
        return []

    target = os.path.normcase(os.path.abspath(file_path))
    processes = []
    current_pid = os.getpid()
    deadline = time.monotonic() + timeout

    for proc in psutil.process_iter(["pid", "name"]):
        if time.monotonic() > deadline:
            break

        pid = proc.info.get("pid")
        if not pid or pid == current_pid:
            continue

        try:
            for opened in proc.open_files() or []:
                opened_path = os.path.normcase(os.path.abspath(opened.path))
                if opened_path == target:
                    processes.append({
                        "pid": pid,
                        "name": proc.info.get("name") or f"进程 {pid}",
                        "service_name": "",
                        "app_type": "打开文件句柄",
                        "restartable": False,
                    })
                    break
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except Exception:
            continue

    return processes


def kill_process(pid: int) -> dict:
    """
    Kill a process by PID. Uses forceful kill on Windows.

    Returns:
        dict: {success, message}
    """
    try:
        import psutil
        process = psutil.Process(pid)
        process_name = process.name()

        # On Windows, kill() calls TerminateProcess (forceful)
        process.kill()

        # Wait to confirm it's dead
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            # Still alive after kill + wait — very unusual
            return {"success": False, "message": f"无法终止进程: {process_name} (PID: {pid})，进程仍在运行"}

        # Double-check the process is actually gone
        if psutil.pid_exists(pid):
            return {"success": False, "message": f"进程 {process_name} (PID: {pid}) 仍在运行"}

        return {
            "success": True,
            "message": f"已终止进程: {process_name} (PID: {pid})"
        }

    except psutil.NoSuchProcess:
        # Process already gone — that's fine, counts as success
        return {"success": True, "message": f"进程已不存在 (PID: {pid})"}
    except psutil.AccessDenied:
        # Try taskkill /F as fallback (may have higher privilege via token)
        return _taskkill_fallback(pid)
    except ImportError:
        return _taskkill_fallback(pid)
    except Exception as e:
        return {"success": False, "message": f"终止进程失败: {str(e)}"}


def _taskkill_fallback(pid: int) -> dict:
    """Fallback: use taskkill /F to forcefully kill a process."""
    try:
        import subprocess
        result = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, text=True, timeout=10,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return {"success": True, "message": f"已终止进程 (PID: {pid})"}
        else:
            msg = result.stderr.strip() or result.stdout.strip()
            return {"success": False, "message": f"终止失败: {msg}"}
    except Exception as e:
        return {"success": False, "message": f"终止进程失败: {str(e)}"}


def kill_processes(pids: List[int]) -> dict:
    """
    Kill multiple processes by their PIDs.

    Returns:
        dict: {success, message, results}
    """
    results = []
    all_success = True

    for pid in pids:
        result = kill_process(pid)
        results.append({"pid": pid, **result})
        if not result["success"]:
            all_success = False

    success_count = sum(1 for r in results if r["success"])
    total = len(results)

    if all_success:
        message = f"已成功终止全部 {total} 个进程"
    else:
        message = f"成功终止 {success_count}/{total} 个进程"

    return {
        "success": all_success,
        "message": message,
        "results": results
    }
