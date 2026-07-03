# 使用说明

## 安装依赖

```bash
pip install -r requirements.txt
```

## 直接运行

```bash
python main.py
```

直接运行会打开拖放界面。将文件或文件夹拖入窗口后，可以选择：

- `粉碎文件`
- `解除占用`

## 注册右键菜单

```bash
python main.py --install
```

注册后，在 Windows 文件资源管理器中右键文件或文件夹，会看到 `PowerShellFileTools` 子菜单。

## 注销右键菜单

```bash
python main.py --uninstall
```

## 粉碎文件

粉碎文件会执行多次覆写，然后删除目标文件。此操作不可逆。

默认覆写方式：

1. `0x00`
2. `0xFF`
3. 随机数据

## 解除占用

解除占用会检测正在锁定目标文件的进程，并在确认后终止这些进程。

注意：终止进程可能导致对应程序未保存的数据丢失。

## 拖放路径说明

WebView2 的拖放事件在部分环境中不会暴露本地完整路径。程序会尝试通过文件名、大小、修改时间、相对路径等信息恢复路径。

如果拖放无法识别，请使用右键菜单入口；右键菜单由 Windows Explorer 直接传递完整路径，更可靠。

## 打包

运行：

```bat
build.bat
```

输出目录：

```text
dist\PowerShellFileTools\
```

打包后注册右键菜单：

```bat
dist\PowerShellFileTools\PowerShellFileTools.exe --install
```
