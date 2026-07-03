# PowerShellFileTools

一个 Windows 桌面文件工具，提供 **文件粉碎** 和 **解除占用** 两个核心功能。程序使用 PyWebView + HTML/CSS/JavaScript 构建界面，并支持注册到 Windows 资源管理器右键菜单。

## 功能特性

- **文件粉碎**：对文件进行多轮覆写后删除，降低普通恢复工具找回的可能性。
- **文件夹粉碎**：递归处理文件夹内文件，完成后删除空目录。
- **解除占用**：检测正在占用目标文件的进程，并在确认后终止进程。
- **占用进程识别**：显示占用程序名称、PID 等信息。
- **右键菜单集成**：注册到 Windows 文件/文件夹右键菜单，无需管理员权限。
- **二次确认**：粉碎和解除占用都会先弹出确认窗口。
- **现代桌面 UI**：深色工业控制台风格界面，支持拖放识别目标文件。

## 界面入口

### 1. 右键菜单

注册后，在 Windows 资源管理器中右键文件或文件夹：

```text
PowerShellFileTools
├── 粉碎文件
└── 解除占用
```

右键菜单是最稳定的入口，因为 Windows 会直接把完整路径传给程序。

### 2. 直接打开程序

直接运行程序会进入拖放界面。将文件或文件夹拖入窗口后，可以执行粉碎或解除占用。

> 注意：WebView2 的网页拖放事件在部分环境中不会暴露本地完整路径。程序会尝试根据文件名、大小、修改时间和相对路径恢复目标路径，但右键菜单仍然是最可靠的方式。

## 安装依赖

```bash
pip install -r requirements.txt
```

依赖：

```text
pywebview>=5.0
psutil>=5.9
```

运行环境：

- Windows 10/11
- Python 3.10+
- Microsoft Edge WebView2 Runtime

## 使用方法

### 启动程序

```bash
python main.py
```

### 注册右键菜单

```bash
python main.py --install
```

### 注销右键菜单

```bash
python main.py --uninstall
```

### 手动执行操作

```bash
python main.py --action shred "C:\path\to\file.txt"
python main.py --action unlock "C:\path\to\file.txt"
```

## 打包

项目提供了 `build.bat`：

```bat
build.bat
```

构建输出目录：

```text
dist\PowerShellFileTools\
```

打包后注册右键菜单：

```bat
dist\PowerShellFileTools\PowerShellFileTools.exe --install
```

## 实现说明

### 文件粉碎

文件粉碎逻辑位于：

```text
core/shredder.py
```

默认执行 3 次覆写：

1. `0x00`
2. `0xFF`
3. 随机数据

覆写后会调用 Windows `FlushFileBuffers`，再截断并删除文件。

### 解除占用

解除占用逻辑位于：

```text
core/unlocker.py
```

主要使用：

- Windows Restart Manager API
- `psutil` 进程检测与终止
- `taskkill /F` 作为备用终止方式

### 右键菜单

注册表逻辑位于：

```text
core/registry.py
```

注册位置为当前用户：

```text
HKCU\SOFTWARE\Classes\*\shell\PowerShellFileTools
HKCU\SOFTWARE\Classes\Directory\shell\PowerShellFileTools
```

因此注册右键菜单通常不需要管理员权限。

## 项目结构

```text
PowerShellFileTools/
├── core/
│   ├── registry.py      # 右键菜单注册/注销
│   ├── shredder.py      # 文件粉碎逻辑
│   └── unlocker.py      # 文件占用检测与进程终止
├── ui/
│   ├── index.html       # PyWebView 页面
│   ├── style.css        # 页面样式
│   └── app.js           # 前端交互逻辑
├── docs/
│   └── USAGE.zh-CN.md   # 中文使用说明
├── main.py              # 程序入口
├── build.bat            # PyInstaller 打包脚本
├── requirements.txt
└── README.md
```

## 安全提示

- 文件粉碎是破坏性操作，请确认目标无误后再执行。
- 对 SSD、云同步目录、快照、日志型文件系统等场景，安全删除效果可能受到系统机制影响。
- 解除占用会终止进程，可能导致对应程序中未保存的数据丢失。
- 建议优先通过右键菜单使用，这样路径最准确。

## 许可证

当前项目尚未添加正式开源许可证。如需分发、二次开发或接受外部贡献，建议先添加明确的 LICENSE 文件。
