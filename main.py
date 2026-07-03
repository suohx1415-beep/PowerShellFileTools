"""
PowerShellFileTools - Main Entry Point
A Windows right-click context menu tool for file shredding and file unlocking.

Usage:
    PowerShellFileTools.exe --install              Register context menu
    PowerShellFileTools.exe --uninstall            Unregister context menu
    PowerShellFileTools.exe --action shred <path>   Shred file/folder
    PowerShellFileTools.exe --action unlock <path>  Unlock file
"""

import os
import sys
import argparse
import webview  # pywebview

from core.shredder import shred_file, shred_folder, _format_size
from core.unlocker import find_locking_processes, kill_processes
from core.registry import register_context_menu, unregister_context_menu, is_registered


class Api:
    """Python API exposed to the JavaScript frontend via pywebview."""

    def __init__(self, file_path: str = None, action: str = None):
        self.file_path = os.path.abspath(file_path) if file_path else ''
        self.action = action
        self._window = None

    def set_window(self, window):
        self._window = window

    def get_action(self) -> str:
        """Get the action type passed from the context menu (shred/unlock or None)."""
        return self.action or ''

    def set_file(self, file_path: str) -> dict:
        """Set the current target file from the drag-and-drop UI."""
        if not file_path:
            return {"success": False, "message": "未获取到文件路径"}

        # PyWebView/Chromium may return file URLs for dropped local files.
        if file_path.startswith('file:///'):
            from urllib.parse import unquote, urlparse
            parsed = urlparse(file_path)
            file_path = unquote(parsed.path)
            if file_path.startswith('/') and len(file_path) > 3 and file_path[2] == ':':
                file_path = file_path[1:]

        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            return {"success": False, "message": f"路径不存在: {file_path}"}

        self.file_path = file_path
        return {"success": True, "message": "文件已选择", "info": self.get_file_info()}

    def pick_file(self) -> dict:
        """Open a native file picker and set the selected file."""
        if not self._window:
            return {"success": False, "message": "窗口尚未初始化"}

        result = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False)
        if not result:
            return {"success": False, "cancelled": True, "message": "已取消选择"}

        file_path = result[0] if isinstance(result, (list, tuple)) else result
        return self.set_file(file_path)

    def pick_folder(self) -> dict:
        """Open a native folder picker and set the selected folder."""
        if not self._window:
            return {"success": False, "message": "窗口尚未初始化"}

        result = self._window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        if not result:
            return {"success": False, "cancelled": True, "message": "已取消选择"}

        folder_path = result[0] if isinstance(result, (list, tuple)) else result
        return self.set_file(folder_path)

    def resolve_drop_entries(self, entries: list) -> dict:
        """Resolve WebView2 drop metadata to a local absolute path."""
        if not entries:
            return {"success": False, "message": "拖放事件没有包含文件信息"}

        matches = []
        for entry in entries:
            matches.extend(self._resolve_drop_entry(entry))

        if not matches:
            names = ", ".join(str(e.get("name", "")) for e in entries[:3] if e.get("name"))
            return {
                "success": False,
                "message": f"WebView 未提供完整路径，且无法在常用目录中定位: {names or '未知文件'}"
            }

        matches.sort(key=lambda item: item[0], reverse=True)
        best_score, best_path = matches[0]
        same_score = [path for score, path in matches if score == best_score]

        if len(same_score) > 1:
            return {
                "success": False,
                "message": "找到多个同名目标，无法安全判断是哪一个。请从文件所在目录直接拖入，或使用右键菜单。"
            }

        return self.set_file(best_path)

    def _resolve_drop_entry(self, entry: dict) -> list:
        name = (entry.get("name") or "").strip()
        if not name:
            return []

        candidates = []
        full_path = (entry.get("fullPath") or "").strip().replace("/", os.sep).lstrip("\\/")
        roots = self._drop_search_roots()

        for root in roots:
            if full_path:
                candidates.append(os.path.join(root, full_path))
            candidates.append(os.path.join(root, name))

        matches = []
        seen = set()
        for candidate in candidates:
            candidate = os.path.abspath(candidate)
            norm = os.path.normcase(candidate)
            if norm in seen or not os.path.exists(candidate):
                continue
            seen.add(norm)
            score = self._score_drop_candidate(candidate, entry)
            if score > 0:
                matches.append((score, candidate))

        # Last resort: shallow name search in common roots, bounded to avoid UI stalls.
        if not matches:
            matches.extend(self._shallow_find_drop_entry(entry, roots))

        return matches

    def _drop_search_roots(self) -> list:
        home = os.path.expanduser("~")
        roots = [
            os.getcwd(),
            os.path.dirname(os.path.abspath(__file__)),
            home,
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Documents"),
        ]

        unique = []
        seen = set()
        for root in roots:
            if root and os.path.isdir(root):
                norm = os.path.normcase(os.path.abspath(root))
                if norm not in seen:
                    seen.add(norm)
                    unique.append(root)
        return unique

    def _score_drop_candidate(self, path: str, entry: dict) -> int:
        name = entry.get("name") or ""
        if os.path.basename(path) != name:
            return 0

        score = 50
        is_dir = bool(entry.get("isDirectory"))
        is_file = bool(entry.get("isFile"))
        if is_dir and os.path.isdir(path):
            score += 30
        elif is_file and os.path.isfile(path):
            score += 30
        elif not is_dir and not is_file:
            score += 10
        else:
            return 0

        size = entry.get("size")
        if size is not None and os.path.isfile(path):
            try:
                if int(size) == os.path.getsize(path):
                    score += 25
            except (TypeError, ValueError, OSError):
                pass

        last_modified = entry.get("lastModified")
        if last_modified:
            try:
                dropped_mtime = float(last_modified) / 1000
                if abs(os.path.getmtime(path) - dropped_mtime) < 3:
                    score += 25
            except (TypeError, ValueError, OSError):
                pass

        return score

    def _shallow_find_drop_entry(self, entry: dict, roots: list) -> list:
        import time

        name = entry.get("name") or ""
        deadline = time.monotonic() + 2.0
        matches = []
        visited = 0
        max_depth = 3
        max_dirs = 1200

        for root in roots:
            root = os.path.abspath(root)
            root_depth = root.rstrip(os.sep).count(os.sep)
            for current, dirs, files in os.walk(root):
                if time.monotonic() > deadline or visited > max_dirs:
                    return matches
                visited += 1

                depth = current.rstrip(os.sep).count(os.sep) - root_depth
                if depth >= max_depth:
                    dirs[:] = []

                possible = []
                if name in dirs:
                    possible.append(os.path.join(current, name))
                if name in files:
                    possible.append(os.path.join(current, name))

                for path in possible:
                    score = self._score_drop_candidate(path, entry)
                    if score > 0:
                        matches.append((score - 5, path))
        return matches

    def get_file_info(self) -> dict:
        """Get information about the target file."""
        try:
            path = self.file_path
            if not path:
                return {
                    "file_path": "",
                    "name": "等待拖入文件",
                    "directory": "--",
                    "is_directory": False,
                    "exists": False,
                    "has_file": False,
                    "size": "--",
                    "type": "未选择"
                }

            is_dir = os.path.isdir(path)

            info = {
                "file_path": path,
                "name": os.path.basename(path) or path,
                "directory": os.path.dirname(path),
                "is_directory": is_dir,
                "exists": os.path.exists(path),
                "has_file": True,
            }

            if is_dir:
                # Count files in directory
                file_count = sum(len(files) for _, _, files in os.walk(path))
                info["size"] = f"{file_count} 个文件"
                info["type"] = "文件夹"
            elif os.path.exists(path):
                size = os.path.getsize(path)
                info["size"] = _format_size(size)
                # Get file extension type
                ext = os.path.splitext(path)[1].lower()
                type_map = {
                    ".txt": "文本文件", ".doc": "Word文档", ".docx": "Word文档",
                    ".xls": "Excel表格", ".xlsx": "Excel表格",
                    ".ppt": "PPT演示", ".pptx": "PPT演示",
                    ".pdf": "PDF文档", ".jpg": "JPEG图片", ".jpeg": "JPEG图片",
                    ".png": "PNG图片", ".gif": "GIF图片", ".bmp": "BMP图片",
                    ".mp3": "MP3音频", ".wav": "WAV音频", ".flac": "FLAC音频",
                    ".mp4": "MP4视频", ".avi": "AVI视频", ".mkv": "MKV视频",
                    ".zip": "ZIP压缩包", ".rar": "RAR压缩包", ".7z": "7z压缩包",
                    ".exe": "可执行文件", ".msi": "安装程序", ".dll": "动态链接库",
                    ".py": "Python脚本", ".js": "JavaScript文件", ".html": "HTML文件",
                    ".css": "CSS样式表", ".json": "JSON文件", ".xml": "XML文件",
                    ".log": "日志文件", ".cfg": "配置文件", ".ini": "配置文件",
                    ".tmp": "临时文件", ".bak": "备份文件",
                }
                info["type"] = type_map.get(ext, f"{ext.upper()} 文件" if ext else "未知类型")
            else:
                info["size"] = "--"
                info["type"] = "不存在"

            return info

        except Exception as e:
            return {
                "file_path": self.file_path,
                "name": "获取信息失败",
                "directory": "--",
                "is_directory": False,
                "exists": False,
                "size": "--",
                "type": str(e)
            }

    def shred_file(self, path: str = None) -> dict:
        """Shred a file or folder."""
        target = path or self.file_path
        if not target:
            return {"success": False, "message": "请先拖入或选择一个文件"}
        if os.path.isdir(target):
            return shred_folder(target)
        else:
            return shred_file(target)

    def find_locking_processes(self, path: str = None) -> dict:
        """Find processes locking a file."""
        target = path or self.file_path
        if not target:
            return {"success": False, "processes": [], "message": "请先拖入或选择一个文件"}
        return find_locking_processes(target)

    def kill_processes(self, pids: list) -> dict:
        """Kill processes by PID list."""
        return kill_processes(pids)

    def close_window(self):
        """Close the application window."""
        if self._window:
            self._window.destroy()


def start_gui(file_path: str, action: str = None):
    """Launch the PyWebView GUI window."""
    api = Api(file_path, action)

    # Determine the UI directory
    if getattr(sys, 'frozen', False):
        ui_dir = os.path.join(sys._MEIPASS, 'ui')
    else:
        ui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui')

    html_file = os.path.join(ui_dir, 'index.html')
    if not os.path.exists(html_file):
        # Fallback: try relative path
        html_file = os.path.join('ui', 'index.html')

    # Create window
    window = webview.create_window(
        title="PowerShellFileTools",
        url=html_file,
        js_api=api,
        width=540,
        height=520,
        min_size=(440, 440),
        resizable=True,
        frameless=False,
        easy_drag=True,
    )

    api.set_window(window)

    # Start webview event loop
    webview.start(debug=False)


def main():
    parser = argparse.ArgumentParser(
        description="PowerShellFileTools - 文件粉碎与解除占用工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  PowerShellFileTools.exe --install              注册右键菜单
  PowerShellFileTools.exe --uninstall            注销右键菜单
  PowerShellFileTools.exe --action shred "C:\\test.txt"   粉碎文件
  PowerShellFileTools.exe --action unlock "C:\\test.txt"  解除占用
"""
    )

    parser.add_argument('--install', action='store_true', help='注册右键菜单')
    parser.add_argument('--uninstall', action='store_true', help='注销右键菜单')
    parser.add_argument('--action', choices=['shred', 'unlock'], help='操作类型')
    parser.add_argument('path', nargs='?', help='目标文件或文件夹路径')

    args = parser.parse_args()

    # Handle install/uninstall (no GUI needed)
    if args.install:
        result = register_context_menu()
        print(result["message"])
        input("\n按回车键退出...")
        sys.exit(0 if result["success"] else 1)

    if args.uninstall:
        result = unregister_context_menu()
        print(result["message"])
        input("\n按回车键退出...")
        sys.exit(0 if result["success"] else 1)

    # If no action and no path, launch drag-and-drop mode
    if not args.action and not args.path:
        start_gui(None, None)
        sys.exit(0)

    # Validate path
    if not args.path:
        print("错误: 请指定目标文件路径")
        sys.exit(1)

    if not os.path.exists(args.path):
        print(f"错误: 路径不存在: {args.path}")
        sys.exit(1)

    # Launch GUI
    start_gui(args.path, args.action)


if __name__ == '__main__':
    main()
