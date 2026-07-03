# PowerShellFileTools

PowerShellFileTools is a Windows desktop utility for secure file shredding and file unlock operations. It provides a PyWebView-based UI, Windows Explorer context menu integration, and a drag-and-drop workflow for local files.

## Features

- **Secure file shredding**: overwrites files with multiple passes before deletion.
- **Folder shredding**: recursively shreds files inside a folder.
- **File unlock detection**: uses the Windows Restart Manager API to find processes that lock a file.
- **Process termination**: can terminate detected locking processes after confirmation.
- **Explorer context menu**: adds a per-user right-click submenu for files and directories.
- **Modern desktop UI**: dark industrial console design with confirmation dialogs and process lists.
- **No admin required for registration**: context menu entries are written under `HKCU`.

## Screens and Workflow

PowerShellFileTools supports two entry points:

1. **Explorer context menu**
   - Right-click a file or folder.
   - Open `PowerShellFileTools`.
   - Choose `粉碎文件` or `解除占用`.

2. **Standalone app**
   - Launch the program directly.
   - Drag a file or folder into the window.
   - Choose an operation.

> Note: WebView2 drag-and-drop events may not expose absolute local paths in every environment. The app attempts to recover paths from drag metadata, but the Explorer context menu remains the most reliable way to pass exact paths.

## Requirements

- Windows 10/11
- Python 3.10+
- Microsoft Edge WebView2 Runtime
- Python packages from `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the UI directly:

```bash
python main.py
```

Register the Explorer context menu:

```bash
python main.py --install
```

Unregister it:

```bash
python main.py --uninstall
```

Launch a specific operation manually:

```bash
python main.py --action shred "C:\path\to\file.txt"
python main.py --action unlock "C:\path\to\file.txt"
```

## Build

Use the bundled build script:

```bat
build.bat
```

The packaged app is generated under:

```text
dist\PowerShellFileTools\
```

After building, register the packaged executable:

```bat
dist\PowerShellFileTools\PowerShellFileTools.exe --install
```

## Security Notes

- File shredding is destructive. Shredded files cannot be recovered by normal means.
- On SSDs, wear leveling, snapshots, cloud sync, and filesystem journaling can affect secure deletion guarantees.
- Unlocking a file works by terminating locking processes. Unsaved data in those processes may be lost.
- The app shows confirmation dialogs before destructive operations.

## Project Structure

```text
PowerShellFileTools/
├── core/
│   ├── registry.py   # Explorer context menu registration
│   ├── shredder.py   # Secure overwrite and deletion
│   └── unlocker.py   # Restart Manager and process termination
├── ui/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── main.py
├── build.bat
└── requirements.txt
```

## License

This project is currently distributed without a formal license. Add a license before redistributing or accepting external contributions.
