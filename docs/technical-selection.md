# 技术选型与效果预判

## 目标

构建一个免费、本地、可批处理长视频的视频修复工具，主要改善：

- 压缩导致的块状伪影
- 低清视频的细节不足
- 轻中度像素化区域
- 旧素材的噪声、锐度和观感

本项目不承诺恢复被遮挡的真实内容。对于强遮挡和人为马赛克，输出本质上是生成式补全。

## 核心判断

1. 长视频场景优先解决工程问题。
   模型推理只是其中一环，真正决定可用性的通常是切片策略、显存管理、失败恢复、音视频合成和批处理体验。

2. 免费方案应采用“多模型可插拔”。
   不同视频退化原因差异很大，固定单模型会很快遇到天花板。项目需要让增强、修复、超分、去噪模块可以替换。

3. 时序稳定比单帧锐化更重要。
   长视频最怕闪烁、脸部/纹理漂移和局部跳变。第一版就要记录 chunk 边界、重叠帧和一致性检查。

4. 强马赛克无法真实复原。
   AI 可以生成合理纹理，但不能找回已经被遮挡或丢失的信息。产品文案和默认配置都要避免误导。

## 推荐架构

```text
input video
  -> ffprobe metadata
  -> scene/chunk split
  -> frame extraction
  -> ROI detection or manual mask
  -> restoration pipeline
       -> deblocking / denoise
       -> video inpainting or enhancement
       -> super-resolution
       -> temporal consistency pass
  -> ffmpeg encode
  -> audio/subtitle remux
  -> output video
```

## 组件选择

### CLI 与任务调度

- Python 标准库 `argparse` 起步，命令稳定后可迁移到 Typer。
- 任务状态写入 `outputs/<job-id>/manifest.json`。
- 每个 chunk 独立处理，失败后可以从最近 chunk 恢复。

### 视频处理

- FFmpeg：负责探测、抽帧、编码、音轨和字幕复用。
- PyAV/OpenCV：用于局部预览、帧级检测和调试。

### 模型方向

- Real-ESRGAN：免费、成熟，适合通用超分和观感增强。
- SwinIR：图像复原能力强，适合去噪、去压缩、超分实验。
- BasicVSR++ / VRT：更适合视频超分和时序稳定，但环境配置更重。
- ProPainter / STTN / LaMa：适合遮挡区域补全或局部修复，需要谨慎标注生成属性。

### UI

- 第一阶段：CLI。
- 第二阶段：Gradio 本地 Web UI，用于预览、选择 ROI、对比参数。
- 第三阶段：PySide6 或 Tauri 桌面壳，适合普通用户分发。

## 免费效果预期

| 场景 | 预期 |
| --- | --- |
| 低码率压缩块 | 好，通常能明显改善 |
| 老视频低清 | 中到好，取决于原始信息量 |
| 小面积像素化 | 中，可能需要手动 mask |
| 大面积强马赛克 | 差到中，只能生成近似纹理 |
| 长视频批处理 | 可行，但必须做 chunk、缓存和断点续跑 |

## 第一版 MVP

- `mosaic plan <video>`：生成处理计划，不改动视频。
- `mosaic extract <video>`：按 chunk 抽帧。
- `mosaic enhance <video>`：接入一个免费增强模型。
- `mosaic render <job>`：合成输出，保留音轨。
- `mosaic ui`：启动本地预览界面。

## 风险

- 模型权重许可证不一致，需要逐个确认。
- Windows CUDA / PyTorch / FFmpeg 环境会带来安装摩擦。
- 长视频可能产生巨大临时文件，需要清理策略。
- 生成式修复可能产生不稳定或误导性的细节。
