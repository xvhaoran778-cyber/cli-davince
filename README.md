# cli-anything-resolve

一个基于 [CLI-Anything](https://github.com/HKUDS/CLI-Anything) 思路构建的 **DaVinci Resolve 智能剪辑命令行工具**。

它通过 Blackmagic Design 官方 Scripting API 控制本机正在运行的 DaVinci Resolve，将项目管理、素材导入、时间线剪辑、片段调整、自动字幕和视频渲染等能力封装成结构化命令。Codex、Claude Code、OpenClaw 等具备终端执行能力的通用 Agent，可以通过稳定的 JSON 输入与输出调用这些功能。

## 主要功能

- 检查 Resolve、Python 环境、脚本 SDK 和连接状态
- 创建、打开、查询和保存 Resolve 项目
- 导入素材并查看媒体池内容
- 创建、检查、替换和删除时间线
- 按源素材入点、出点和目标位置添加片段
- 调整缩放、位置、旋转、裁切和透明度等片段属性
- 调用 Resolve 自动字幕功能
- 查询渲染格式与预设，启动并等待渲染任务
- 使用声明式 JSON 剪辑方案一次完成整套自动剪辑流程
- 为人类提供可读输出，为 Agent 提供统一的 `--json` 输出

## 运行要求

- Python 3.10 至 3.13
- DaVinci Resolve Studio
- 在 Resolve 设置中允许本机外部脚本访问
- 调用 CLI 前需要先启动 DaVinci Resolve

当前真实验证环境为 macOS + DaVinci Resolve Studio 20.2。代码包含 Windows 和 Linux 的 SDK 路径发现逻辑，但这两个平台尚未完成真实 Resolve 环境测试。

## 安装

```bash
git clone https://github.com/xvhaoran778-cyber/cli-davince.git
cd cli-davince

python3.13 -m venv .venv
.venv/bin/pip install '.[dev]'
.venv/bin/cli-anything-resolve doctor
```

如果 Resolve 没有安装在系统默认位置，可以手动指定 SDK 与动态库路径：

```bash
export RESOLVE_SCRIPT_API="/path/to/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/path/to/fusionscript.so"
```

## 快速使用

检查环境和连接状态：

```bash
cli-anything-resolve doctor
cli-anything-resolve --json status
```

创建项目、导入素材并建立时间线：

```bash
cli-anything-resolve project create Demo --frame-rate 25
cli-anything-resolve media import /absolute/path/intro.mp4
cli-anything-resolve timeline create Main
cli-anything-resolve clip append intro.mp4 --source-in 50 --source-out 200
```

使用 Resolve 预设进行渲染：

```bash
cli-anything-resolve render start \
  --preset "YouTube - 1080p" \
  --target-dir /absolute/output \
  --name demo \
  --wait
```

## JSON 剪辑方案

复杂剪辑建议使用声明式 JSON 方案。Agent 可以生成方案文件，CLI 负责校验并确定性执行。

```bash
cli-anything-resolve --json plan validate edit-plan.json
cli-anything-resolve --json plan apply edit-plan.json
```

示例结构：

```json
{
  "version": 1,
  "project": {
    "name": "Demo",
    "create": true,
    "settings": {
      "frame_rate": 25,
      "width": 1920,
      "height": 1080
    }
  },
  "timeline": {
    "name": "Main",
    "replace": false
  },
  "media": [
    {
      "id": "intro",
      "path": "/absolute/path/intro.mp4"
    }
  ],
  "edits": [
    {
      "media": "intro",
      "source_in": {"seconds": 2},
      "source_out": {"seconds": 8},
      "record_at": {"seconds": 0},
      "track": 1,
      "properties": {"ZoomX": 1.1, "ZoomY": 1.1}
    }
  ]
}
```

时间位置支持帧数、秒数和 SMPTE timecode。源素材入出点按照素材自身帧率换算，`record_at` 按时间线帧率换算并相对于时间线起点。公开格式中的 `source_out` 使用半开区间语义。

完整示例见 [examples/edit-plan.example.json](examples/edit-plan.example.json)，架构和退出码说明见 [RESOLVE.md](RESOLVE.md)。

## Agent 调用

仓库同时提供 [SKILL.md](skills/cli-anything-resolve/SKILL.md)，便于支持 Skill 的 Agent 发现和调用本工具。

```bash
cli-anything-resolve --json project list
cli-anything-resolve --json timeline inspect Main
cli-anything-resolve --json plan apply /absolute/edit-plan.json
```

所有机器可读结果都使用统一的成功或错误 JSON 结构。删除片段和时间线需要显式传入 `--yes`；覆盖同名时间线必须显式使用 `--replace`。

## 隐私与安全

CLI 只连接本机运行的 Resolve Scripting API，不会主动上传项目、素材或渲染文件。

需要注意，`project list`、`media list` 和 `timeline inspect` 等命令可能返回项目名称、素材名称及本机绝对路径。如果使用云端 Agent，应将这些命令输出视为私人数据。除非确实需要远程控制，否则建议始终将 Resolve 外部脚本权限设置为仅允许本机访问。

仓库默认忽略以下本地内容：

- `.env` 配置文件
- 本地 `edit-plan.json`
- 素材与渲染输出目录
- Resolve 项目、时间线和归档文件

提交公开仓库前，请只保留使用占位路径的脱敏示例。

## 测试状态

- 14 项自动化测试通过
- 已在 DaVinci Resolve Studio 20.2 上完成真实连接测试
- 已验证项目创建、素材导入、混合帧率选段、时间线编辑和 720p 视频渲染

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。
