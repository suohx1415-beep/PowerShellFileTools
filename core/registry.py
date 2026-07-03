"""
Registry Module - PowerShellFileTools
Registers/unregisters context menu entries in Windows Explorer.
Uses HKCU (per-user) so no admin privileges are required.

Uses the cascading submenu approach via nested shell\\shell pattern.
"""

import os
import sys
import winreg


# Registry constants
HKCU = winreg.HKEY_CURRENT_USER

# Registry paths for file and directory context menus
REG_BASE_FILE = r"SOFTWARE\Classes\*\shell"
REG_BASE_DIR = r"SOFTWARE\Classes\Directory\shell"

APP_KEY_NAME = "PowerShellFileTools"


def _get_exe_path() -> str:
    """Get the absolute path to the running executable."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        # Always use absolute path for the script
        return os.path.abspath(sys.argv[0])


def register_context_menu() -> dict:
    """
    Register right-click context menu entries for files and directories.

    Creates a cascading submenu with two options:
      - 🔒 粉碎文件 (Shred)
      - 🔓 解除占用 (Unlock)

    Returns:
        dict: {success, message}
    """
    try:
        exe_path = _get_exe_path()
        is_frozen = getattr(sys, 'frozen', False)

        # Register for files (*)
        _register_cascading_menu(
            REG_BASE_FILE,
            exe_path,
            is_frozen
        )

        # Register for directories
        _register_cascading_menu(
            REG_BASE_DIR,
            exe_path,
            is_frozen
        )

        return {
            "success": True,
            "message": f"右键菜单注册成功!\n程序路径: {exe_path}"
        }

    except Exception as e:
        return {"success": False, "message": f"注册右键菜单失败: {str(e)}"}


def _register_cascading_menu(reg_base: str, exe_path: str, is_frozen: bool):
    r"""
    Register a cascading submenu using the nested shell\shell pattern.

    Structure created:
      <reg_base>\PowerShellFileTools
        (Default) = "PowerShellFileTools"
        Icon       = shell32.dll,47   (generic app icon)
        SubCommands = ""
        <reg_base>\PowerShellFileTools\shell\shred
          (Default) = "🔒 粉碎文件"
          Icon      = shell32.dll,131  (delete icon)
          <reg_base>\PowerShellFileTools\shell\shred\command
            (Default) = "<exe_path> --action shred "%1""
        <reg_base>\PowerShellFileTools\shell\unlock
          (Default) = "🔓 解除占用"
          Icon      = shell32.dll,17   (lock icon)
          <reg_base>\PowerShellFileTools\shell\unlock\command
            (Default) = "<exe_path> --action unlock "%1""
    """
    app_key = f"{reg_base}\\{APP_KEY_NAME}"

    # 1. Create the parent menu entry with MUIVerb (required for cascading submenu)
    key = winreg.CreateKey(HKCU, app_key)
    winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "PowerShellFileTools")
    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "shell32.dll,47")
    winreg.SetValueEx(key, "SubCommands", 0, winreg.REG_SZ, "")
    winreg.CloseKey(key)

    # 2. Build the command string (use pythonw.exe to avoid console window)
    if is_frozen:
        shred_cmd = f'"{exe_path}" --action shred "%1"'
        unlock_cmd = f'"{exe_path}" --action unlock "%1"'
    else:
        # Use pythonw.exe (no console window) instead of python.exe
        python_dir = os.path.dirname(sys.executable)
        pythonw = os.path.join(python_dir, "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable  # fallback to python.exe
        shred_cmd = f'"{pythonw}" "{exe_path}" --action shred "%1"'
        unlock_cmd = f'"{pythonw}" "{exe_path}" --action unlock "%1"'

    # 3. Register shred subcommand
    shred_key = f"{app_key}\\shell\\shred"
    key = winreg.CreateKey(HKCU, shred_key)
    winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "粉碎文件")
    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "shell32.dll,131")
    winreg.CloseKey(key)

    cmd_key = winreg.CreateKey(HKCU, f"{shred_key}\\command")
    winreg.SetValueEx(cmd_key, None, 0, winreg.REG_SZ, shred_cmd)
    winreg.CloseKey(cmd_key)

    # 4. Register unlock subcommand
    unlock_key = f"{app_key}\\shell\\unlock"
    key = winreg.CreateKey(HKCU, unlock_key)
    winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "解除占用")
    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, "shell32.dll,17")
    winreg.CloseKey(key)

    cmd_key = winreg.CreateKey(HKCU, f"{unlock_key}\\command")
    winreg.SetValueEx(cmd_key, None, 0, winreg.REG_SZ, unlock_cmd)
    winreg.CloseKey(cmd_key)


def unregister_context_menu() -> dict:
    r"""
    Remove all PowerShellFileTools entries from the context menu.

    Deletes keys recursively from:
      - HKCU\SOFTWARE\Classes\*\shell\PowerShellFileTools
      - HKCU\SOFTWARE\Classes\Directory\shell\PowerShellFileTools
      - HKCU\...\CommandStore\shell\PowerShellFileTools.shred (legacy cleanup)
      - HKCU\...\CommandStore\shell\PowerShellFileTools.unlock (legacy cleanup)

    Returns:
        dict: {success, message}
    """
    errors = []

    # Recursively delete main menu entries (handles all subkeys automatically)
    for reg_base in [REG_BASE_FILE, REG_BASE_DIR]:
        app_key = f"{reg_base}\\{APP_KEY_NAME}"
        try:
            _delete_key_recursive(HKCU, app_key)
        except Exception as e:
            errors.append(f"{app_key}: {str(e)}")

    # Legacy CommandStore cleanup (from old registration method) - best effort
    cmd_store = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell"
    for subcmd in [f"{APP_KEY_NAME}.shred", f"{APP_KEY_NAME}.unlock"]:
        try:
            _delete_key_recursive(HKCU, f"{cmd_store}\\{subcmd}")
        except Exception:
            pass  # Ignore legacy cleanup failures (may need admin)

    if not errors:
        return {"success": True, "message": "右键菜单已成功注销"}
    else:
        return {
            "success": False,
            "message": "注销过程中出现错误:\n" + "\n".join(errors)
        }


def _delete_key_recursive(root_key, sub_key):
    """Recursively delete a registry key and all its subkeys."""
    try:
        key = winreg.OpenKey(root_key, sub_key)
    except FileNotFoundError:
        return
    except Exception:
        return

    # Enumerate and delete all subkeys
    while True:
        try:
            child_name = winreg.EnumKey(key, 0)
            _delete_key_recursive(root_key, f"{sub_key}\\{child_name}")
        except OSError:
            break

    winreg.CloseKey(key)

    try:
        winreg.DeleteKey(root_key, sub_key)
    except (FileNotFoundError, OSError):
        pass


def is_registered() -> bool:
    """Check if the context menu is currently registered."""
    try:
        winreg.OpenKey(HKCU, f"{REG_BASE_FILE}\\{APP_KEY_NAME}")
        return True
    except FileNotFoundError:
        return False
