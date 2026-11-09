# 映序 AI 视频创作工作室

## 安装与启动

需要 Python 3.11、Python 3.12 和 uv。首次在项目根目录执行：

```sh
./install-quick.sh
./run.sh
```

打开 http://127.0.0.1:4180 ，API 位于 4173。可通过 `PORT`、`STUDIO_UI_PORT` 改端口。
安装脚本通过 `uv sync --locked` 创建两个项目内环境：
`.venv`（Python 3.11，媒体与 UI）以及 `.venv-api`
（Python 3.12，仅安装 `api` 依赖组）。API 保持原服务所用的系统 Python 主版本，
便于继续访问已授权的 macOS 钥匙串。首次访问仍遵循系统授权策略。
**无需原 内置媒体引擎 源码目录或它的虚拟环境。**

每次修改完成并通过验证后，必须重启 API 和前端，并检查 4180 的 `/_stcore/health` 与 4173 的 `/api/bootstrap` 正常响应。

项目总览的每张项目卡片提供「删除项目」，二次确认后删除项目、项目素材及制作记录；有排队、运行或已提交任务时需等待任务结束。

## 包与依赖管理

```text
FrameFlow-Studio/
├── studio/
│   ├── paths.py                  # 应用、资源和运行数据的统一路径
│   ├── integrations/quick_api.py # 快速制作 API、输入校验、项目归属、产物收集
│   └── engine/
│       ├── worker.py             # 独立子进程中的第三方媒体适配层
│       └── runtime.py            # 内置引擎就绪检测
├── vendor/（内置媒体引擎）/
│   ├── app/                      # 保持原样的第三方源码
│   │   └── _assets/              # 配置模板、默认字体和音乐
│   ├── LICENSE                   # 原始 MIT 许可
│   ├── MANIFEST.json             # 导入文件的 SHA-256 清单
│   └── README.md                 # 来源与维护规则
├── server.py                     # 本地 API 与自定义分镜工作流
├── streamlit_app.py              # 项目、快速制作、素材、设置页面
├── storyboard_ui.py              # 自定义制作工作区
├── quick_api.py / quick_worker.py / quick_engine.py  # 旧调用入口的薄兼容层
├── launch.py / run.sh            # 分别启动项目内 API 与媒体/UI 环境
├── pyproject.toml / uv.lock      # 统一依赖声明与锁文件
└── data/                         # 运行数据（不纳入版本管理）
```

应用层不直接导入第三方 `app` 命名空间；只有独立 worker 将 vendor 加入模块路径。
引擎通过标准输入 JSON 接收所需参数，标准输出返回结果。运行配置位于
`data/quick-engine/config.toml`，产物位于该目录的 `storage/`；素材副本在
`data/quick/`，归档素材在 `data/media/`，项目与任务存入 `data/studio.db`。
`STUDIO_DATA` 可指定另一运行数据根目录。API Key 继续使用本应用的 macOS 钥匙串。
不会导入原项目的用户配置、凭据、虚拟环境或生成文件。

维护规则：业务变更放在 `studio/`；vendor 保持原样。升级 vendor 时同时更新来源、
许可与文件清单，重新运行隔离合成测试。依赖变更编辑 pyproject 后运行 `uv lock`
与 `uv sync --locked`，不要手动修改锁文件。

兼容例外：沿用上游安全策略，将 Pillow 覆盖为 13.x（MoviePy 2.2.1 的元数据仍声明
`Pillow<12`）。因此 `uv pip check` 会报告这一项已知版本上限冲突；没有篡改第三方
元数据来隐藏它。隔离测试通过实际视频合成验证兼容性，其余依赖不得忽略冲突。

## 使用

在项目总览点击创建项目，选择「快速生成视频」或「自定义」。快速项目支持文案、
素材、配音、字幕与合成；编辑时恢复上次提交生成的表单状态。自定义包含故事、
分镜、画风、首尾帧、提交前准备、逐镜视频生成、视频合成七步。

设置中的角色模型独立保存，快速文案复用总导演。模型检查可选，生成任务由用户
点击提交；不会自动充值或重试付费 POST。视频预算使用估算单价并保留任务预留，
实际费用以服务商账单为准。支持生成分辨率选择和 720p/1080p 本地合成放大。

项目和素材使用固定卡片、筛选与底部分页；成片可预览和下载。仅供单人本机使用，
服务绑定 127.0.0.1，并校验 Host/Origin。

## 角色模型与 Codex 渠道

设置支持 39 个平台/渠道，预设参考已迁入的 内置媒体引擎 注册表。
预设模型不代表当前账户已开通；可在保存后测试连接读取平台模型列表，也可手动填写
模型 ID。只有「自定义兼容接口」需要填写 HTTPS 地址，普通平台自动匹配。
自定义接口的密钥按角色和地址隔离，防止切换地址后沿用另一服务商的密钥。

总导演额外支持：

- OpenAI Codex · 本机登录：通过官方 `codex exec`，复用本机登录。可在界面发起
  官方设备登录；应用不读取或复制 Codex 登录凭据。CLI 需支持界面使用的执行选项
  （本机已检查 0.162.1）。执行在临时目录中以只读模式进行，关闭 shell、插件和
  子代理，只有最终文本返回工作流。不会改写用户 Codex 配置。
- OpenAI Codex · 官方 API：使用独立 API Key 和 `/responses`，不是 Chat Completions。
- 自定义兼容接口：支持 Chat Completions 或 Responses，模型 ID 可手动填写。

配置支持 30–1800 秒超时、自动或指定推理强度；具体模型可能不支持所有强度。
CLI 当前仅用于文本和分镜，图片与视频继续使用各自角色。CLI 连接测试只检查
登录和本地缓存，不消耗生成额度；API 连接测试读取模型列表，不保证生成权限。

官方参考：[Codex 认证](https://developers.openai.com/codex/auth)、
[非交互执行](https://developers.openai.com/codex/noninteractive)、
[GPT-5.3-Codex API](https://developers.openai.com/api/docs/models/gpt-5.3-codex)。

## 调用日志与用量

侧边栏「调用日志」提供角色、平台、项目、模型、结果和时间筛选，支持底部分页及
本页 CSV 导出。记录位于同一 SQLite 数据库的 `model_calls` 与 `model_usage` 表。
包含请求结果、耗时、HTTP 状态、请求 ID、关联项目/任务和服务商已返回的用量。
仅保留分辨率、请求秒数等必要参数，不存储认证头、API Key、请求/响应正文或图像数据。

支持 Chat Completions、Responses、Anthropic 和 Codex CLI 的 Token 用量映射；
图像数量来自返回图片数，视频秒数仅在服务商明确返回时记录。缺失用量显示未提供，
不会按字符或配置费用推算。Codex CLI 读取 `thread.completed` 的 usage 事件。
远程视频任务的累计用量按平台、接口及任务 ID 去重，重复刷新不重复累计。
日志从功能上线后的调用开始记录，不回填旧任务的未知用量。

## 验证

在应用目录使用自己的 Python 执行：

```sh
cd video-studio
.venv/bin/python test_bundled_engine.py
.venv/bin/python test_quick.py
.venv/bin/python test_model_channels.py
.venv/bin/python test_call_logs.py
.venv/bin/python test_call_logs_ui.py
.venv/bin/python test_server.py
.venv/bin/python test_storyboard_ui.py
.venv/bin/python test_project_navigation.py
.venv/bin/python test_settings_ui.py
.venv/bin/python test_button_feedback.py
.venv/bin/python test_http.py
.venv/bin/python test_streamlit.py
```

`test_bundled_engine.py` 校验源码清单，并将应用包与 vendor 复制到隔离目录，
禁用网络，使用本地合成的音视频运行真实媒体流程，验证产物和导入路径。
最后两个测试需要本机端口权限；test_streamlit 需要已启动的服务。
测试不调用真实收费模型；配音服务和在线素材平台仍需有效 Key 与网络。

第三方来源与许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 部署与完整使用手册

支持 Docker Compose、pip 本地包安装和仓库/ZIP 源码安装，详见 [使用手册](docs/使用手册.md)。当前未发布公共 PyPI 包或预构建镜像。
