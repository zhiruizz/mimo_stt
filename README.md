# MiMo STT — 语音转文字工具

本地运行、通过小米 MiMo 云端 API 转录的语音转文字工具，支持常见音视频格式，自动分段转录。音频分段会上传至所配置的 API 服务。

应室友要求使用agnet制作，顺手开源。欢迎使用和folk。

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
│   └── index.html      # 前端页面（含旧模型配置迁移）
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
| **模型名称** | 默认 `mimo-v2.6-flash`；可选 `mimo-v2.5-asr`，也可自定义 |

> 所有设置填写一次后会自动保存在浏览器中（localStorage），下次打开自动恢复。

### 2026 年 10 月模型迁移

根据[官方下线公告](https://mimo.mi.com/docs/zh-CN/updates/deprecate)，
`mimo-v2.5` / `mimo-v2.5-pro` 从 2026-10-14 18:00（北京时间）开始自动转发，
2026-10-21 10:00 正式失效；`mimo-v2-omni` 已于 2026-06-30 退役。
更新本项目并重新打开页面后，旧 localStorage 中的模型名称会自动迁移并保存；
后端也会规范化旧客户端提交的模型名。映射仅匹配完整名称，不会把 ASR/TTS 等带后缀模型误替换。

| 旧名称（包括自定义输入中保存的名称） | 迁移后 |
|---|---|
| `mimo-v2.5`、`mimo-v2-omni`、`mimo-v2-flash` | `mimo-v2.6-flash` |
| `mimo-v2.5-pro`、`mimo-v2-pro` | `mimo-v2.6-pro` |
| 空名称／空自定义输入 | `mimo-v2.6-flash` |
| `mimo-v2.5-asr`、其他自定义名称 | 保留原名称 |

迁移保留原有 API Endpoint、API Key、提示词、输出目录及自动保存设置，无须清空浏览器数据。
浏览器禁止写入 localStorage 时，当前页面仍使用迁移后的名称，但无法持久保存。
模型、Endpoint 和密钥类型应匹配自己的服务／套餐；程序不会自动更换服务地址或切换付费方式。

### Flash 与专用 ASR：默认保留现有流程

本版选择 **V2.6 Flash 为默认迁移方案**，延续音频理解接口、逐段转录及自定义提示词。
这是兼容性选择；尚未进行真实 API 音质／准确率对照，不能据此断言哪个模型更准、更快或更省。
专用 ASR 作为手动可选项，使用独立的请求参数，不能只替换模型字符串。

| 项目 | `mimo-v2.6-flash`（默认） | `mimo-v2.5-asr`（可选） |
|---|---|---|
| 适用性 | 音频理解、可用提示词控制转录指令 | 专用中英文、方言语音识别 |
| 请求内容 | system 转录指令 + user 音频和提示词 | 仅 user 音频，`asr_options.language=auto` |
| 输出控制 | 显式关闭思考，保留 `max_completion_tokens=4096` | 不发送通用模型的思考、提示词或 token 上限参数 |
| Base64 限制 | 官方上限 50 MB | 官方上限 10 MB，本程序在发送前检查 |
| 按量计费（中国区，截至 2026-10-16） | 输入未命中缓存 ¥1／百万 token，输出 ¥2／百万 token | 按输入音频时长 ¥0.5／小时 |
| Token Plan | 按 token 扣 Credits | 按输入音频时长扣额度，30M Credits／小时 |

两者均调用 `/v1/chat/completions`，本程序统一发送 **16 kHz、单声道、16-bit PCM WAV**。
60 秒分段的 Base64 约 2.56 MB，在两者大小限制内。ASR 仅接收 WAV/MP3，现有 FFmpeg 转换因此保留。
ASR 模式下界面会禁用提示词输入，但保留原提示词，切回 Flash 可继续使用。
Token Plan 官方也列出 ASR 支持；按量 API 与 Token Plan 的 Key、Endpoint 和额度不互通，
请使用与现有账户对应的配置，勿直接将普通 API Key 与套餐地址混用。

程序只将响应 `content` 用作转录文本；仅返回 `reasoning_content` 时报告错误，避免把思考内容保存为转录。
响应被输出长度／内容过滤等原因截断时报告错误；分段转换失败时停止任务，避免漏段后误报成功。

参考：[音频理解](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/multimodal-understanding/audio-understanding)、
[专用 ASR](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/audio/Speech-Recognition)、
[ASR API 参数](https://mimo.mi.com/docs/en-US/api/audio/Speech-Recognition)、
[按量价格](https://mimo.mi.com/docs/en-US/price/pay-as-you-go)、
[Token Plan](https://mimo.mi.com/docs/en-US/tokenplan/Token%20Plan/subscription)。价格和额度以官方最新文档为准。

### 无密钥回归测试与本地验收

安装 Python 依赖和 FFmpeg 后，从项目根目录执行：

```bash
python -m unittest discover -s tests -v
node --test tests/frontend.test.cjs
```

前端测试需要 Node.js 18+，运行应用不需要 Node.js。测试使用模拟 API，**不会发送真实请求或读取密钥**。
Python 回归通过真实 FFmpeg 将 125 秒的合成双声道 8 kHz WAV 转为 16 kHz 单声道音频，验证
60／60／5 秒无丢帧分段、Base64 请求、顺序拼接、状态查询及 Markdown 保存。
无 FFmpeg 时音频回归会显示跳过，不能视为通过。前端通过 Node VM 和最小 DOM 验证页面脚本、
localStorage 迁移及提交参数；这不能替代真实浏览器的界面验收。

更新正在运行的本地部署前，请先自行审查代码。在隔离副本中重新启动服务，检查旧浏览器设置的恢复，
再由操作者手动填写密钥，用一段 5–10 秒、无敏感信息的语音各调用 Flash／ASR 一次进行对照；
检查识别文本、方言／术语、返回用量和账单后再决定是否切换 ASR。测试后再验证代表性的视频文件、
跨段连续语音及 Windows 的 FFmpeg 路径。此版本的离线回归不证明云端模型质量、账户权限或计费已通过验收。

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
