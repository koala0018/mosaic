# mosaic

`mosaic` 是一个面向 Windows 的本地长视频马赛克修复应用。第一版集成开源项目 [Lada](https://github.com/ladaapp/lada) 作为外部修复引擎：Lada 负责自动识别和修复马赛克，本项目负责 Windows 应用体验，包括选择视频、选择输出目录、启动长任务、显示日志、取消处理、完成后弹窗提醒，以及把最终视频保存到电脑指定位置。

项目同时提供一个可选的 OpenCV 美白滤镜模块。它会在本地逐帧处理视频，通过肤色蒙版、人脸肤色采样、亮度增强、CLAHE 对比度增强和羽化融合，让面部和身体皮肤获得更自然的提亮效果。该能力是可选功能，不会改变默认的马赛克修复流程。

## 项目目标

- 支持本地长视频文件，目标场景约 2 小时，最长约 3 小时。
- 支持常见视频格式，例如 `.mp4`、`.mkv`、`.mov`、`.avi`、`.webm`。
- 自动调用 Lada 识别视频内的马赛克区域并进行修复。
- 可选使用 OpenCV 给视频添加自然美白滤镜，主要作用于面部和身体皮肤区域。
- 尽量保持原视频分辨率、帧率、时间戳和音轨，避免跳帧、卡顿和音画不同步。
- 完成后弹出通知，并将输出视频保存到用户指定目录。
- 默认本地运行，不上传用户视频。

重要边界：AI 不能真正恢复已经被强马赛克或隐私遮挡永久隐藏的信息。模型输出是基于上下文生成的修复结果。请只处理你拥有版权或已经获得明确授权的视频。

## 当前功能

- Windows 桌面应用，基于系统自带的 Tkinter。
- 可选择输入视频、输出目录、输出文件名和 `lada-cli.exe`。
- 支持质量预设：
  - `fast`：速度优先，使用 GPU 快速编码，CPU 设备会自动回退。
  - `balanced`：平衡模式，使用 GPU 高质量编码和快速检测。
  - `accelerated`：默认高质量加速模式，使用 GPU UHQ 编码、`v4-fast` 检测和 FP16。
  - `best`：极致质量优先，使用 `v4-accurate`、GPU UHQ 编码和 FP32，速度更慢。
- 支持设备选择：`auto`、`cuda:0`、`cuda`、`xpu`、`cpu`。
- 支持 FP16 加速选项，适合支持半精度加速的 GPU。
- 后台运行长视频处理任务，界面不会卡死。
- 实时显示 Lada 日志。
- 支持 OpenCV 美白滤镜，可调美白强度，并显示完整进度条和日志。
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

## 从 0 开始安装

下面步骤适合第一次在 Windows 电脑上从源码运行本项目。

### 1. 安装基础工具

需要准备：

- Windows 10/11。
- Python 3.11 或更高版本。
- Git，用于克隆仓库。
- 如果要使用马赛克修复：下载 Lada Windows 发布包。
- 如果要使用美白滤镜并保留原音轨：安装 FFmpeg，或者使用带 Lada 的便携包，因为 Lada 包里通常自带 `ffmpeg.exe`。

可以用 PowerShell 检查 Python 和 Git：

```powershell
python --version
git --version
```

如果没有 FFmpeg，但希望美白输出保留原音轨，可以安装：

```powershell
winget install -e --id Gyan.FFmpeg
```

如果不安装 FFmpeg，美白滤镜仍可生成视频，但在源码运行模式下可能无法把原视频音轨合并回输出文件。

### 2. 克隆项目

```powershell
git clone https://github.com/koala0018/mosaic.git
cd mosaic
```

如果你已经下载了源码压缩包，也可以直接解压后进入项目目录。

### 3. 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

如果 PowerShell 阻止激活虚拟环境，可以先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 4. 安装项目依赖

只使用马赛克修复：

```powershell
pip install -e .
```

需要同时使用 OpenCV 美白滤镜：

```powershell
pip install -e ".[beauty]"
```

`beauty` 可选依赖会安装 `opencv-python` 和 `numpy`。默认安装不强制安装 OpenCV，因此不会影响原有马赛克修复功能。

### 5. 启动桌面应用

```powershell
mosaic app
```

也可以运行：

```powershell
mosaic-app
```

应用打开后默认是 `Restore mosaic` 模式。需要美白时切换到 `Beauty whitening`。

## 运行应用

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[beauty]"
mosaic app
```

也可以运行：

```powershell
mosaic-app
```

打开应用后：

1. 点击 `Add videos`，一次选择多个视频，或多次点击继续追加；重复文件会自动去重。
2. 选择输出目录。
3. 选择任务模式：
   - `Restore mosaic`：马赛克修复，默认模式。
   - `Beauty whitening`：OpenCV 美白滤镜。
4. 如果选择 `Restore mosaic`，需要选择 `lada-cli.exe`，然后选择质量和设备。
5. 如果选择 `Beauty whitening`，设置 `Beauty intensity`，建议先使用默认值 `55`。
6. 点击 `Start queue` 开始处理。
7. 在任务队列查看每个视频的状态和进度，在下方执行日志查看当前视频的完整日志。
8. 当前视频完成后会自动输出并继续下一个，最终视频会保存到你指定的位置。

## 使用美白滤镜

美白滤镜是本地 OpenCV 处理流程，不上传视频，也不调用 Lada 模型。它适合给人物面部和身体皮肤做自然提亮，不适合用来改变背景、衣服或五官颜色。

### GUI 使用步骤

1. 启动应用：

```powershell
mosaic app
```

2. 点击 `Add videos` 选择一个或多个本地视频。
3. 选择 `Output folder`。
4. 在 `Task` 中选择 `Beauty whitening`。
5. 设置 `Output name`，默认会使用类似 `input.beauty.mp4` 的文件名。
6. 调整 `Beauty intensity`：
   - `30` 到 `45`：轻微提亮，更自然。
   - `50` 到 `65`：推荐范围，适合大多数人像视频。
   - `70` 以上：效果更明显，但可能出现偏白或妆容变淡。
7. 保持 `Preserve original audio` 勾选，可尽量保留原视频音轨。
8. 点击 `Start queue`。
9. 处理过程中可以同时查看任务进度和执行日志，也可以点击 `Cancel queue` 取消。

完成后输出视频会写入你选择的输出目录。如果找不到 FFmpeg，程序会在日志中提示，并输出无音轨视频。

### CLI 使用步骤

先确认已经安装美白依赖：

```powershell
pip install -e ".[beauty]"
```

使用默认强度处理：

```powershell
mosaic beautify D:\Videos\input.mp4 --output D:\Videos\input.beauty.mp4
```

指定输出目录：

```powershell
mosaic beautify D:\Videos\input.mp4 --output-dir D:\Videos\Beauty
```

指定美白强度：

```powershell
mosaic beautify D:\Videos\input.mp4 --output D:\Videos\input.beauty.mp4 --strength 60
```

不保留原音轨：

```powershell
mosaic beautify D:\Videos\input.mp4 --output D:\Videos\input.beauty.mp4 --no-preserve-audio
```

### 美白算法说明

处理流程大致如下：

1. 用 OpenCV `VideoCapture` 读取本地视频。
2. 每帧转换到 YCrCb 和 HSV 色彩空间，生成基础肤色蒙版。
3. 使用 OpenCV Haar 人脸检测辅助采样肤色，让蒙版更贴近当前视频人物肤色。
4. 排除头发、眉眼、嘴唇、浓妆和暗部细节，减少五官被错误提亮。
5. 对皮肤区域做亮度提升、轻微降饱和、CLAHE 局部对比度增强和双边平滑。
6. 使用羽化蒙版把美白结果和原图融合，保留非皮肤区域细节。
7. 用 `VideoWriter` 写出临时视频。
8. 如果可用，调用 FFmpeg 将原音轨合并回最终输出文件。

该算法偏向“自然、保守”，不会把整帧画面直接拉白。不同视频的光线、妆容、肤色、压缩质量差异较大，建议先用短片段测试强度，再处理长视频。

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
mosaic process input.mp4 --output D:\Videos\Restored\input.restored.mp4 --quality accelerated --device cuda:0
```

CPU-only：

```powershell
mosaic process input.mp4 --output-dir D:\Videos\Restored --quality fast --device cpu --no-fp16
```

美白滤镜：

```powershell
mosaic beautify input.mp4 --output input.beauty.mp4 --strength 55
```

查看美白命令参数：

```powershell
mosaic beautify --help
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

也可以直接使用解压后的便携目录：

```text
dist/mosaic-portable/mosaic.exe
```

如果要安装到当前用户目录并创建桌面快捷方式：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-from-portable.ps1
```

生成可点击安装包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -Installer -LadaVariant nvidia
```

安装包位置：

```text
dist/mosaic-setup-nvidia.exe
```

注意：Windows 自带 IExpress 对大文件安装包支持不好。NVIDIA 版内置 Lada 后体积约 2.5GB，IExpress 可能无法生成单个安装 exe。此时请使用 `dist/mosaic-portable-nvidia.zip` 分发，解压后运行 `mosaic.exe`，或者运行上面的 `install-from-portable.ps1` 安装到本机。

如果目标电脑不是 NVIDIA 显卡，可以构建 Intel 版本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -Installer -LadaVariant intel
```

构建脚本会下载 Lada 官方 Windows 发布包，并把 `lada-cli.exe` 内置到最终包里。最终用户安装后不需要再手动选择 Lada 路径，应用会自动查找安装目录内的 `lada\lada-cli.exe`。

便携包和安装包构建时会自动安装并收集 `opencv-python` 和 `numpy`，因此最终用户可以直接在界面里选择 `Beauty whitening` 使用美白滤镜，不需要单独安装 Python 或 OpenCV。

注意：Lada Windows 包体积很大，NVIDIA 版本约 2.5GB，Intel 版本约 1.3GB。第一次构建需要较长下载时间和足够磁盘空间。构建脚本会优先使用系统自带 `tar.exe` 解压；如果失败，会尝试系统里的 7-Zip；如果都没有，会下载 7-Zip 官方的 `7zr.exe` 到 `vendor/tools` 用于解压。

## 长视频注意事项

- 2 到 3 小时视频可能需要很长处理时间。
- GPU 显存、CPU 性能和硬盘临时空间都会影响速度。
- 临时目录默认在输出目录下的 `.mosaic-temp`。
- `best` 模式质量更高，但速度更慢，临时文件和最终文件也可能更大。
- 如果显存不足，可以改用 `fast` 模式或把设备设为 `cpu`。
- 强马赛克无法保证恢复真实细节，只能生成视觉上更自然的结果。

## 美白滤镜常见问题

### 美白会影响原有马赛克修复功能吗？

不会。应用默认仍然是 `Restore mosaic` 模式。只有选择 `Beauty whitening`，或者在命令行运行 `mosaic beautify` 时，才会启用 OpenCV 美白流程。

### 为什么美白输出没有声音？

OpenCV 自身写视频时不会保留原音轨。本项目会尽量调用 FFmpeg 把原音轨合并回输出文件。如果找不到 FFmpeg，程序会输出无音轨视频并在日志中提示。源码运行时可以安装 FFmpeg；打包版通常会从内置 Lada 目录中找到 `ffmpeg.exe`。

### 为什么有些皮肤没有被明显提亮？

滤镜会尽量只处理肤色区域，并排除头发、五官、嘴唇和高饱和区域。暗光、强压缩、彩色灯光、遮挡、夸张妆容或肤色与背景过于接近时，蒙版可能比较保守。可以适当提高 `Beauty intensity`，建议从 `55` 调到 `65` 先试。

### 为什么背景或衣服有时也被轻微提亮？

如果背景、衣服或道具颜色接近肤色，OpenCV 肤色阈值可能误选。当前算法通过人脸肤色采样、形态学清理和五官排除来降低误选，但不能保证每个场景完全准确。建议先处理短片段确认效果。

### 长视频应该怎么使用？

先用 10 到 30 秒片段测试强度和效果，确认自然后再处理完整视频。长视频会占用较多 CPU、磁盘写入和临时空间，输出目录下的 `.mosaic-temp` 是默认临时目录。

## 开发文档

- [Lada 集成说明](docs/lada-integration.md)
- [技术选型](docs/technical-selection.md)
- [开发路线](docs/roadmap.md)
