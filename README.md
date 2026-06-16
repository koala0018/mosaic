# mosaic

`mosaic` 是一个面向长视频的本地化视频修复项目，目标是在免费、可复现、可离线运行的前提下，改善低清、压缩块、像素化马赛克等画面退化问题。

> 使用边界：本项目只面向本人拥有版权或已获得明确授权的视频修复、压缩伪影修复、旧素材增强和研究学习。不要用于绕过隐私遮挡、身份保护、新闻/执法/医疗等敏感遮盖，AI 也无法可靠恢复被遮挡的真实信息。

## 技术预判

- 免费实现“比较好的效果”是可行的，但最佳结果来自组合流水线，而不是单一模型。
- 对低码率压缩块、轻中度像素化、旧视频低清增强，开源模型通常能显著改善观感。
- 对人为打码、强马赛克或遮挡区域，模型只能生成“看起来合理”的内容，不能还原真实细节。
- 长视频处理的关键不是模型本身，而是分段、显存控制、断点续跑、音视频封装和时序稳定。
- 第一版应优先做 CLI 批处理和可复现流水线，再做桌面或 Web UI。

## 技术选型

- 语言：Python 3.11+
- 视频 IO：FFmpeg + PyAV/OpenCV
- 推理框架：PyTorch，后续按需导出 ONNX Runtime / TensorRT
- 画质增强：Real-ESRGAN、SwinIR、BasicVSR++、VRT 等开源方向
- 区域修复：ProPainter / LaMa / STTN 等视频或图像修复方向
- 长视频调度：按 scene/chunk 切片，临时帧缓存，断点续跑，最终 FFmpeg 合成
- UI 方向：先 CLI，后 Gradio 本地 Web UI；稳定后再考虑 PySide6 桌面壳

完整路线见 [docs/technical-selection.md](docs/technical-selection.md) 和 [docs/roadmap.md](docs/roadmap.md)。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
mosaic --help
```

当前 CLI 是项目骨架，用来固定命令结构和处理策略。后续会逐步接入真实检测、增强、修复和合成模块。

## 示例

```powershell
mosaic plan input.mp4 --output outputs/input-restored.mp4 --quality balanced
```

## 开发原则

- 默认本地运行，不上传用户视频。
- 所有模型权重放在 `models/` 或 `weights/`，不提交到 Git。
- 长视频任务必须支持断点续跑。
- 输出结果必须保留原音轨和基础元数据。
- 对无法真实恢复的信息保持明确提示，避免把生成内容伪装成事实。
