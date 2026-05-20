# Video Sentence Splitter

外语学习工具：YouTube / B站 / 本地视频 → 字幕提取（Whisper） → LLM 语义断句 → 翻译 → 流媒体播放 + 交互编辑。

## 功能

- **多来源视频**：YouTube、B站、本地文件上传
- **智能字幕提取**：Whisper 语音识别
- **AI 语义断句**：基于 LLM 将字幕切分为自然句子
- **多引擎翻译**：LLM / Google 翻译 / Microsoft 翻译（F0 免费层）
- **交互式学习**：点击句子跳转播放、双击编辑、拆分合并句子、滚动时播放器自动缩小

## 快速开始

从 [Releases](../../releases) 下载最新打包版本，解压后双击 `start.bat`，浏览器自动打开即可使用。

首次使用需要配置 **LLM API Key**（支持所有 OpenAI 兼容接口，如 DeepSeek、OpenAI、Groq 等），以及可选的 YouTube/B站 Cookie。

## 开发

### 环境要求

- Python >= 3.10（测试于 3.12）
- Node.js >= 18
- ffmpeg

### 安装与运行

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 构建前端
cd frontend
npm install
npm run build
cd ..

# 3. 启动后端
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 4. 前端开发模式（可选）
cd frontend
npm run dev       # http://localhost:3000
```

### 项目结构

```
├── backend/              # FastAPI 后端
│   ├── main.py           # 应用入口
│   ├── config.py         # 配置（ffmpeg/node 发现、目录管理）
│   ├── database.py       # SQLAlchemy + SQLite
│   ├── models/           # ORM 模型 + Pydantic schemas
│   ├── routers/          # API 路由
│   ├── services/         # 核心服务
│   │   ├── fetcher.py    # yt-dlp 视频下载
│   │   ├── whisper.py    # 语音识别
│   │   ├── segmenter.py  # LLM 断句
│   │   ├── translator.py # 翻译引擎
│   │   └── workflow.py   # 编排流水线
│   ├── prompts/          # LLM prompt 模板
│   └── utils/            # 工具函数
├── frontend/             # Vue 3 + Vite + Element Plus
│   └── src/
│       ├── views/        # 页面（Dashboard、Settings、AddVideo、VideoDetail）
│       ├── components/   # UI 组件
│       ├── api/          # API 封装
│       └── stores/       # Pinia 状态管理
└── requirements.txt      # Python 依赖
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI (async) + Uvicorn |
| 数据库 | SQLAlchemy + SQLite |
| 语音识别 | faster-whisper (CTranslate2) |
| LLM | OpenAI 兼容接口（支持 DeepSeek、OpenAI、Groq 等） |
| 视频下载 | yt-dlp |
| 音视频处理 | ffmpeg |
| 前端 | Vue 3 + Vite + Element Plus + Pinia |

## License

GLP3.0
