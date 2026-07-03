"""
File Shredder Module - PowerShellFileTools
Securely overwrites files with random data and deletes them.
Uses Windows FlushFileBuffers to ensure data is written to disk.
"""

import os
import sys
import ctypes
import ctypes.wintypes
import random
import stat
import msvcrt


def shred_file(file_path: str, passes: int = 3) -> dict:
    """
    Securely shred a single file by overwriting it multiple times then deleting it.

    Returns:
        dict: {success, message, file_path}
    """
    if not os.path.exists(file_path):
        return {"success": False, "message": f"文件不存在: {file_path}", "file_path": file_path}

    if os.path.isdir(file_path):
        return {"success": False, "message": f"这是一个文件夹，请使用粉碎文件夹功能", "file_path": file_path}

    try:
        _clear_file_attributes(file_path)
        file_size = os.path.getsize(file_path)
        kernel32 = ctypes.windll.kernel32

        # Overwrite passes: zeros, 0xFF, random data
        for pass_num in range(passes):
            with open(file_path, 'r+b') as f:
                handle = msvcrt.get_osfhandle(f.fileno())
                chunk_size = 1024 * 1024  # 1MB chunks
                remaining = file_size

                while remaining > 0:
                    size = min(chunk_size, remaining)
                    if pass_num >= 2:
                        data = bytes(random.getrandbits(8) for _ in range(size))
                    elif pass_num == 1:
                        data = b'\xFF' * size
                    else:
                        data = b'\x00' * size

                    f.write(data)
                    remaining -= size

                # Ensure data is flushed to disk
                kernel32.FlushFileBuffers(handle)

        # Truncate and delete
        with open(file_path, 'r+b') as f:
            f.truncate(0)

        os.remove(file_path)

        if os.path.exists(file_path):
            _force_delete(file_path)

        return {
            "success": True,
            "message": f"文件已安全粉碎 ({passes} 次覆写, {_format_size(file_size)})",
            "file_path": file_path
        }

    except PermissionError:
        return {"success": False, "message": "权限不足，文件可能被占用", "file_path": file_path}
    except Exception as e:
        return {"success": False, "message": f"粉碎失败: {str(e)}", "file_path": file_path}


def shred_folder(folder_path: str, passes: int = 3) -> dict:
    """
    Recursively shred all files in a folder.

    Returns:
        dict: {success, message, file_path, stats}
    """
    if not os.path.exists(folder_path):
        return {"success": False, "message": "文件夹不存在", "file_path": folder_path}

    if not os.path.isdir(folder_path):
        return {"success": False, "message": "这不是一个文件夹", "file_path": folder_path}

    success_count = 0
    fail_count = 0
    failed_files = []

    try:
        for root, dirs, files in os.walk(folder_path, topdown=False):
            for filename in files:
                result = shred_file(os.path.join(root, filename), passes)
                if result["success"]:
                    success_count += 1
                else:
                    fail_count += 1
                    failed_files.append(filename)

            for dirname in dirs:
                try:
                    os.rmdir(os.path.join(root, dirname))
                except OSError:
                    fail_count += 1

        try:
            os.rmdir(folder_path)
        except OSError:
            fail_count += 1

        total = success_count + fail_count
        message = f"粉碎完成: {success_count}/{total} 个文件成功"
        if fail_count > 0:
            message += f", {fail_count} 个失败"
            if failed_files:
                names = ", ".join(failed_files[:5])
                if len(failed_files) > 5:
                    names += "..."
                message += f" ({names})"

        return {
            "success": fail_count == 0,
            "message": message,
            "file_path": folder_path,
            "stats": {
                "total_files": total,
                "success_count": success_count,
                "fail_count": fail_count,
                "failed_files": failed_files
            }
        }

    except Exception as e:
        return {"success": False, "message": f"粉碎文件夹失败: {str(e)}", "file_path": folder_path}


def _clear_file_attributes(file_path: str) -> None:
    """Clear read-only, hidden, system attributes."""
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(file_path)
        if attrs == ctypes.wintypes.DWORD(-1):
            return

        # Clear read-only, hidden, system flags
        attrs &= ~0x00000001  # FILE_ATTRIBUTE_READONLY
        attrs &= ~0x00000002  # FILE_ATTRIBUTE_HIDDEN
        attrs &= ~0x00000004  # FILE_ATTRIBUTE_SYSTEM

        ctypes.windll.kernel32.SetFileAttributesW(file_path, attrs)
        os.chmod(file_path, stat.S_IWUSR | stat.S_IRUSR)
    except Exception:
        pass


def _force_delete(file_path: str) -> None:
    """Force delete using Windows API CreateFileW + DeleteFileW."""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            file_path,
            0x00010000,  # DELETE
            0x00000007,  # FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE
            None,
            3,           # OPEN_EXISTING
            0x80,        # FILE_ATTRIBUTE_NORMAL
            None
        )
        if handle not in (-1, 0, 0xFFFFFFFF):
            kernel32.DeleteFileW(file_path)
            kernel32.CloseHandle(handle)
    except Exception:
        pass


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
