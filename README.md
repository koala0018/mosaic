# mosaic

`mosaic` 是一个面向 Windows 的本地长视频马赛克修复应用。第一版集成开源项目 [Lada](https://github.com/ladaapp/lada) 作为外部修复引擎：Lada 负责自动识别和修复马赛克，本项目负责 Windows 应用体验，包括选择视频、选择输出目录、启动长任务、显示日志、取消处理、完成后弹窗提醒，以及把最终视频保存到电脑指定位置。

## 项目目标

- 支持本地长视频文件，目标场景约 2 小时，最长约 3 小时。
- 支持常见视频格式，例如 `.mp4`、`.mkv`、`.mov`、`.avi`、`.webm`。
- 自动调用 Lada 识别视频内的马赛克区域并进行修复。
- 尽量保持原视频分辨率、帧率、时间戳和音轨，避免跳帧、卡顿和音画不同步。
- 完成后弹出通知，并将输出视频保存到用户指定目录。
- 默认本地运行，不上传用户视频。

重要边界：AI 不能真正恢复已经被强马赛克或隐私遮挡永久隐藏的信息。模型输出是基于上下文生成的修复结果。请只处理你拥有版权或已经获得明确授权的视频。

## 当前功能

- Windows 桌面应用，基于系统自带的 Tkinter。
- 可选择输入视频、输出目录、输出文件名和 `lada-cli.exe`。
- 支持质量预设：
  - `fast`：速度优先，CPU 编码较快。
  - `balanced`：平衡模式，让 Lada 根据当前机器选择默认编码策略。
  - `best`：质量优先，使用 Lada 的高质量 CPU 编码预设，速度更慢。
- 支持设备选择：`auto`、`cuda`、`xpu`、`cpu`。
- 支持强制 FP16 选项，适合支持半精度加速的 GPU。
- 后台运行长视频处理任务，界面不会卡死。
- 实时显示 Lada 日志。
- 支持取消当前处理任务。
- 成功或失败后弹窗提示。
- 同时提供 CLI 命令，方便调试和批处理。

## 为什么使用 Lada

Lada 已经提供了本项目最关键的能力：

- 自动马赛克检测；
- 视频马赛克修复模型；
- Windows 可用的 `lada.exe` / `lada-cli.exe` 发布包；
- 长视频处理管线；
- 输出时尽量保留原始视频尺寸、帧率、时间戳，并重新合并音轨。

Lada 使用 AGPL-3.0 许可证。本仓库目前使用 MIT 许可证，所以第一版不会复制或改写 Lada 源码，而是通过外部进程调用 `lada-cli.exe`，保持许可证边界清晰。

## 安装 Lada

从 Lada 项目页面下载 Windows 版本：

[https://github.com/ladaapp/lada](https://github.com/ladaapp/lada)

下载后找到发布包里的 `lada-cli.exe`。你可以使用以下任意一种方式让 `mosaic` 找到它：

- 在 `mosaic` 应用里手动选择 `lada-cli.exe`。
- 把 `lada-cli.exe` 加入系统 `PATH`。
- 设置环境变量 `LADA_CLI_PATH` 为 `lada-cli.exe` 的完整路径。
- 将它放到本项目的 `tools/lada/lada-cli.exe`。

注意：Lada 可能还需要它自己的模型权重和运行时文件，请以 Lada 官方发布包说明为准。

## 运行应用

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
mosaic app
```

也可以运行：

```powershell
mosaic-app
```

打开应用后：

1. 选择要处理的视频文件。
2. 选择输出目录。
3. 选择 `lada-cli.exe`。
4. 选择质量和设备。
5. 点击 `Start` 开始处理。
6. 等待完成弹窗，最终视频会保存到你指定的位置。

## 命令行使用

检查 Lada 是否可用：

```powershell
mosaic lada-info --lada-cli C:\path\to\lada-cli.exe
```

处理视频：

```powershell
mosaic process input.mp4 --output-dir D:\Videos\Restored --quality balanced --device auto --lada-cli C:\path\to\lada-cli.exe
```

质量优先：

```powershell
mosaic process input.mp4 --output D:\Videos\Restored\input.restored.mp4 --quality best --device cuda
```

CPU-only：

```powershell
mosaic process input.mp4 --output-dir D:\Videos\Restored --quality fast --device cpu --no-fp16
```

## 打包 Windows 程序

### 推荐：先手动下载 Lada 包

如果构建机访问 GitHub / Pixeldrain 很慢，可以先用浏览器或下载工具手动下载 Lada 官方包，然后让脚本离线整合。

NVIDIA 版本，推荐用于 NVIDIA 显卡：

- 国内加速分卷 1：[lada-v0.11.0_windows_nvidia.7z.001](https://gh-proxy.com/https://github.com/ladaapp/lada/releases/download/v0.11.0/lada-v0.11.0_windows_nvidia.7z.001)
- 国内加速分卷 2：[lada-v0.11.0_windows_nvidia.7z.002](https://gh-proxy.com/https://github.com/ladaapp/lada/releases/download/v0.11.0/lada-v0.11.0_windows_nvidia.7z.002)
- Pixeldrain 单文件：[lada-v0.11.0_windows_nvidia.7z](https://pixeldrain.com/u/vWJKV7X5)
- GitHub 分卷 1：[lada-v0.11.0_windows_nvidia.7z.001](https://github.com/ladaapp/lada/releases/download/v0.11.0/lada-v0.11.0_windows_nvidia.7z.001)
- GitHub 分卷 2：[lada-v0.11.0_windows_nvidia.7z.002](https://github.com/ladaapp/lada/releases/download/v0.11.0/lada-v0.11.0_windows_nvidia.7z.002)

Intel Arc 版本：

- 国内加速单文件：[lada-v0.11.0_windows_intel.7z](https://gh-proxy.com/https://github.com/ladaapp/lada/releases/download/v0.11.0/lada-v0.11.0_windows_intel.7z)
- Pixeldrain 单文件：[lada-v0.11.0_windows_intel.7z](https://pixeldrain.com/u/YAZgG4Pw)
- GitHub 单文件：[lada-v0.11.0_windows_intel.7z](https://github.com/ladaapp/lada/releases/download/v0.11.0/lada-v0.11.0_windows_intel.7z)

下载后放到：

```text
vendor/downloads/
```

NVIDIA 版本可以放 Pixeldrain 单文件，也可以放 GitHub 的 `.001` 和 `.002` 两个分卷。文件名必须保持不变。

脚本会校验 Lada 官方 sha256：

```text
405d053f76e5f773b8b27bbaf921a44fdcf2c59c9fc91ed3f68f1a8daa3a8511 lada-v0.11.0_windows_intel.7z
861caf4bc3fb08bb4f145a0ef53172d051d39401e9f5b1c6cbab7206b32e518b lada-v0.11.0_windows_nvidia.7z.001
472b8012f676cca0ef0eb6af9a69ba1256370dbe6c1c84740ab34d4c2650b796 lada-v0.11.0_windows_nvidia.7z.002
fa0f571964a947402cfaad564180cffd3ef61526c739b5278e64fd0ddec5ca13 lada-v0.11.0_windows_nvidia.7z
```

离线构建安装包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -Installer -LadaVariant nvidia -Offline
```

离线构建便携包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -LadaVariant nvidia -Offline
```

### 自动下载构建

如果网络足够稳定，也可以让脚本自动下载 Lada：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -LadaVariant nvidia
```

自动下载会优先使用 `gh-proxy.com` 的 GitHub Release 加速链接。如果加速服务临时不可用，请手动下载上面的国内加速链接，然后使用 `-Offline` 构建。

生成便携版：

```text
dist/mosaic-portable-nvidia.zip
```

生成可点击安装包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -Installer -LadaVariant nvidia
```

安装包位置：

```text
dist/mosaic-setup-nvidia.exe
```

如果目标电脑不是 NVIDIA 显卡，可以构建 Intel 版本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -Installer -LadaVariant intel
```

构建脚本会下载 Lada 官方 Windows 发布包，并把 `lada-cli.exe` 内置到最终包里。最终用户安装后不需要再手动选择 Lada 路径，应用会自动查找安装目录内的 `lada\lada-cli.exe`。

注意：Lada Windows 包体积很大，NVIDIA 版本约 2.5GB，Intel 版本约 1.3GB。第一次构建需要较长下载时间和足够磁盘空间。构建脚本会优先使用系统自带 `tar.exe` 解压；如果失败，会尝试系统里的 7-Zip；如果都没有，会下载 7-Zip 官方的 `7zr.exe` 到 `vendor/tools` 用于解压。

## 长视频注意事项

- 2 到 3 小时视频可能需要很长处理时间。
- GPU 显存、CPU 性能和硬盘临时空间都会影响速度。
- 临时目录默认在输出目录下的 `.mosaic-temp`。
- `best` 模式质量更高，但速度更慢，临时文件和最终文件也可能更大。
- 如果显存不足，可以改用 `fast` 模式或把设备设为 `cpu`。
- 强马赛克无法保证恢复真实细节，只能生成视觉上更自然的结果。

## 开发文档

- [Lada 集成说明](docs/lada-integration.md)
- [技术选型](docs/technical-selection.md)
- [开发路线](docs/roadmap.md)
