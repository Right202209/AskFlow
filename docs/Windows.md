下面是一份 **Windows / PowerShell 环境、不使用 Makefile** 的 AskFlow 开始指南，按当前仓库代码整理。

**1. 前置环境**

需要安装：

- Python 3.11+
- Node.js 20+
- Docker Desktop，并确保 Docker Compose 可用
- 可选：Ollama 或其他 OpenAI-compatible LLM 服务

确认版本：

```powershell
python --version
node --version
npm --version
docker --version
docker compose version
```

**2. 进入项目目录**

```powershell
cd D:\TSET\python\AskFlow
```

**3. 创建并激活 Python 虚拟环境**

推荐用 `.venv`：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 阻止脚本执行，可以临时放开当前窗口策略：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**4. 安装后端依赖**

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

**5. 安装前端依赖**

```powershell
cd web
npm install
cd ..
```

**6. 准备环境变量**

仓库已有 `.env.example`，如果你还没有 `.env`：

```powershell
Copy-Item .env.example .env
```

本地开发至少确认 `.env` 里有：

```env
APP_ENV=development
SECRET_KEY=change-me-to-a-random-secret-key

DATABASE_URL=postgresql+asyncpg://askflow:askflow@localhost:5432/askflow
REDIS_URL=redis://localhost:6379/0

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=askflow-docs
MINIO_SECURE=false

CHROMA_HOST=localhost
CHROMA_PORT=8100

LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b
```

注意：后端代码里有启动保护。如果 `APP_ENV` 不是 `development`，就不能继续使用默认 `SECRET_KEY`。

**7. 启动基础设施**

在项目根目录执行：

```powershell
docker compose up -d
```

这会启动：

- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- ChromaDB: `localhost:8100`
- MinIO API: `localhost:9000`
- MinIO Console: `localhost:9001`

查看容器状态：

```powershell
docker compose ps
```

**8. 执行数据库迁移**

```powershell
alembic upgrade head
```

**9. 写入种子数据**

```powershell
python scripts\seed_data.py
```

默认账号：

```text
admin / admin123
user1 / user123
```

**10. 启动后端**

保持虚拟环境已激活，然后执行：

```powershell
uvicorn askflow.main:create_app --factory --reload --host 0.0.0.0 --port 8000
```

后端地址：

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Metrics: `http://localhost:8000/metrics`

**11. 启动前端**

另开一个 PowerShell 窗口：

```powershell
cd D:\TSET\python\AskFlow\web
npm run dev
```

前端地址：

```text
http://localhost:5173
```

Vite 已配置代理，前端的 `/api` 和 WebSocket 会转发到 `http://localhost:8000`。

**12. 首次使用流程**

1. 打开 `http://localhost:5173`
2. 用 `admin / admin123` 登录
3. 进入文档管理，上传知识库文档
4. 进入聊天页测试 RAG 问答
5. 用类似下面的问题测试 Agent 路由：

```text
退款政策是什么？
我的订单 AB12345678 到哪了？
页面 500 报错了
我要转人工
```

**常用无 Make 命令**

```powershell
# 启动基础设施
docker compose up -d

# 停止基础设施
docker compose down

# 数据库迁移
alembic upgrade head

# 填充数据
python scripts\seed_data.py

# 后端开发服务
uvicorn askflow.main:create_app --factory --reload --host 0.0.0.0 --port 8000

# 前端开发服务
cd web
npm run dev

# 后端测试
python -m pytest tests\ -v --cov=src/askflow --cov-report=term-missing

# 后端 lint
python -m ruff check src\ tests\
python -m ruff format --check src\ tests\

# 前端构建
cd web
npm run build
```

一个实用提醒：如果你没有运行本地 Ollama/OpenAI-compatible 服务，涉及 LLM 的聊天、意图二次判断、RAG 生成可能会失败；但基础登录、工单、管理页、健康检查等仍可先验证。