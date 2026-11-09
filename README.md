# 映序 AI 视频创作工作室

FrameFlow Studio 是本地运行的视频创作工具，支持快速视频制作，以及从故事、分镜、首尾帧到视频生成与成片合成的完整流程。

当前界面使用 Streamlit，后端使用 FastAPI。支持角色模型配置、素材管理、调用日志及本地项目持久化。

## 启动

需要 Python 3.11、Python 3.12 和 uv：

```sh
./video-studio/install-quick.sh
./video-studio/run.sh
```

打开 http://127.0.0.1:4180 。详细安装、配置、测试和 Docker 使用说明见 [应用文档](video-studio/README.md)。

API Key 通过本机设置配置。运行数据、生成素材、虚拟环境和本地工具不纳入仓库。内置第三方引擎的来源和许可见 [第三方声明](video-studio/THIRD_PARTY_NOTICES.md)。
