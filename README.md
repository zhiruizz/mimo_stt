# MiMo STT — 语音转文字工具

基于小米 MiMo 多模态模型的离线语音转文字工具，支持常见音视频格式，自动分段转录。

## 效果预览

拖入视频/音频 → 自动提取音频 → 60秒分段 → 逐段调用 MiMo API → 拼接完整文本

支持格式：MP3、WAV、FLAC、M4A、OGG、MP4、MKV、AVI、MOV、WebM 等

---

## 快速开始

### 1. 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| **Python** | 3.8+ | [下载地址](https://www.python.org/downloads/)（推荐更高的版本） |
| **FFmpeg** | 任意 | [下载地址](https://www.gyan.dev/ffmpeg/builds/)，下载后将 `bin` 目录加入系统 PATH |
| **pip** | 随 Python 自带 | 用于安装依赖 |

> **检查是否安装成功：**
> ```
> python --version
> ffmpeg -version
> ```
> 两个命令都能正常输出版本号即可。

### 2. 获取项目文件

将整个 `STT` 文件夹复制到你的电脑上，保持文件结构完整：

```
STT/
├── backend.py          # 后端服务
├── frontend/
│   └── index.html      # 前端页面
├── start.bat           # 一键启动脚本
├── requirements.txt    # Python 依赖
├── output/             # 转录结果输出目录（自动创建）
└── README.md           # 本文件
```

### 3. 启动

**双击 `start.bat`** 即可。

脚本会自动：
- 检查 Python 和 FFmpeg 是否已安装
- 安装所需 Python 依赖（首次会慢一些）
- 启动后端服务
- 自动打开浏览器

启动后会看到一个命令行窗口和浏览器页面。**不要关闭命令行窗口**，那是后端服务。

### 4. 使用

1. 在浏览器页面中填写 **API Key** 和 **API Endpoint**（首次填写后会自动记住）
2. 选择或拖入音视频文件
3. 点击 **🚀 开始转录**
4. 等待转录完成，可复制、下载或保存为 Markdown

---

## API 配置

启动后在网页设置区域填写：

| 字段 | 说明 |
|------|------|
| **API Endpoint** | MiMo API 地址，例如 `https://token-plan-cn.xiaomimimo.com/v1/chat/completions` |
| **API Key** | 你的 API 密钥 |
| **模型名称** | 默认 `mimo-v2.5`，也可自定义 |

> 所有设置填写一次后会自动保存在浏览器中（localStorage），下次打开自动恢复。

### 关于 mimo-v2.5

`mimo-v2.5` 是推理模型，转录结果可能出现在 `content` 或 `reasoning_content` 字段。程序已自动处理，优先取 `content`，为空时取 `reasoning_content`。

---

## 输出说明

### 网页端

- 实时显示转录进度（分段数、当前段）
- 完整文本 + 分段详情均可查看
- 支持 **复制到剪贴板** 和 **下载 TXT**

### Markdown 文件

- 可手动点击 **💾 保存 Markdown** 按钮
- 也可勾选 **转录完成后自动保存**
- 默认保存到项目下的 `output/` 文件夹，可自定义路径

生成的 Markdown 文件格式：

```markdown
# 转录结果: video.mp4

- **转录时间**: 2026-05-31 12:00:00
- **分段数量**: 7

---

## 完整文本

（全部转录内容拼接）

---

## 分段详情

### 第 1 段

（第1段内容）

### 第 2 段

（第2段内容）
```

---

## 关闭服务

两种方式：

1. **网页端**：点击右上角 **⏻ 关闭服务** 按钮
2. **命令行**：直接关闭命令行窗口，或按 `Ctrl+C`

---

## 常见问题

### Q: 双击 start.bat 闪退

在 `STT` 文件夹空白处按住 Shift + 右键 → "在此处打开 PowerShell/终端"，输入：
```
python backend.py
```
查看具体报错信息。

### Q: 提示 "Python not found"

Python 未安装或未加入 PATH。安装时勾选 **"Add Python to PATH"**。

### Q: 提示 "ffmpeg not found"

FFmpeg 未安装或未加入 PATH。下载 FFmpeg 后，将 `bin` 目录路径添加到系统环境变量 PATH 中。

### Q: 转录结果为空

- 检查音频是否正常（用播放器试听）
- 检查 API Key 和 Endpoint 是否正确
- 尝试换一个模型

### Q: 请求超时

- 音视频过长时会自动分为 60 秒一段，每段有 120 秒超时
- 检查网络连接
- 检查 API 服务是否正常

### Q: 想修改分段时长或超时时间

编辑 `backend.py` 顶部的配置：
```python
SEGMENT_DURATION = 60   # 每段秒数
REQUEST_TIMEOUT = 120   # 每次请求超时秒数
```

---

## 技术架构

```
浏览器 (前端)  ←→  Flask (后端)  ←→  MiMo API
   │                   │
   │                   ├─ ffmpeg 提取音频
   │                   ├─ ffmpeg 分段
   │                   ├─ base64 编码
   │                   └─ 逐段调用 API
   │
   └─ localStorage 保存设置
```

---

## 依赖列表

- Flask >= 3.0
- flask-cors >= 4.0
- requests >= 2.31
- FFmpeg（系统级）
