# 旅梦规划助手（Travel Plan）

带登录注册的 AI 旅行计划生成应用：填写出行条件 → DeepSeek 生成结构化行程 → 保存 / 历史管理 / PDF 导出。

采用 **Spec Coding** 流程开发：需求文档 → 原型 → 接口 / 数据库设计 → 编码 → 测试。

## 功能特性

- **用户体系**：注册（邀请码制）、登录、「记住我」、JWT 鉴权
- **计划生成**：按目的地、天数、预算、同行人等条件调用 DeepSeek 生成结构化行程
  - 每日分时段安排、景点提示、交通方式对比、附近美食
  - 参考攻略输入（文本 / 链接），有依据才输出店名级信息
  - 生成失败自动降级，接口永不因 LLM 异常返回 500
- **计划管理**：保存、列表（搜索 / 分页）、详情、删除，数据按用户隔离
- **PDF 导出**：零 LLM 纯数据渲染，含交通、住宿、每日安排、景点速查
- **邀请码管理**：命令行签发 / 查看 / 停用，防止陌生人注册消耗 API 余额

## 技术栈

| 层次 | 选型 |
|---|---|
| 前端 | 原生 HTML + CSS + JavaScript（ES6，无框架、无构建） |
| 后端 | Python 3.12+ · FastAPI · uvicorn |
| 数据库 | SQLite（SQLAlchemy 2.x） |
| AI | DeepSeek API（Anthropic 兼容端点，`deepseek-flash`） |
| PDF | reportlab |

## 目录结构

```
├── 需求文档/          # 6 份需求文档 + 用户故事（开发唯一依据）
├── 原型图/            # 高保真原型 HTML
├── 开发文档/          # 接口文档、数据库设计、邀请码管理
├── backend/
│   ├── app/
│   │   ├── main.py       # 应用入口（CORS、统一异常、静态托管）
│   │   ├── cli.py        # 邀请码命令行工具
│   │   ├── core/         # 配置、数据库、JWT / 密码安全
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── schemas/      # Pydantic 模型
│   │   ├── api/          # 路由：auth / plans
│   │   └── services/     # LLM 封装、提示词、PDF 渲染
│   ├── scripts/init_db.py
│   └── pyproject.toml
├── frontend/          # 静态站点（login / index / generate / plans / plan-detail）
└── test/              # pytest 测试
```

## 快速开始

### 1. 后端

```bash
cd backend
uv sync                                    # 安装依赖
cp .env.example .env                       # 复制后填写真实配置
uv run uvicorn app.main:app --reload --port 8000
```

首次启动会自动建表，并在邀请码表为空时创建开发默认邀请码 **`DEV-DEFAULT`**（可用 999 次）。

### 2. 前端

用任意静态服务器打开 `frontend/` 目录（如 VS Code Live Server，端口 5500）。开发期后端 CORS 已放行全部 localhost 来源。

> 生产环境无需单独部署前端：后端启动时会自动把 `frontend/` 挂载为同源静态站点。

### 3. 环境变量（`backend/.env`）

```ini
APP_ENV=development
JWT_SECRET=请改成随机长字符串
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
# DEEPSEEK_DISABLE_THINKING=true
# SQLITE_PATH=   # 可选，默认 backend/travel.db
```

> `.env` 已被 `.gitignore` 排除，**请勿提交真实密钥**。

## 接口一览

统一响应格式：`{"code": 0, "message": "ok", "data": {...}}`，`code != 0` 时 `code` 等于 HTTP 状态码。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册（需 `invite_code`） |
| POST | `/api/auth/login` | 登录 |
| GET | `/api/auth/check` | 用户名 / 手机号可用性检查 |
| GET | `/api/auth/me` | 当前用户信息 |
| POST | `/api/plans/generate` | 生成行程（同步，≤120s） |
| POST | `/api/plans` | 保存计划 |
| GET | `/api/plans` | 我的计划列表（搜索 / 分页） |
| GET | `/api/plans/{id}` | 计划详情 |
| GET | `/api/plans/{id}/pdf` | 导出 PDF |
| DELETE | `/api/plans/{id}` | 删除计划 |

所有计划接口均按 token 解析的 `user_id` 过滤，越权返回 403。

## 邀请码管理

```bash
cd backend
uv run python -m app.cli invite create --note "备注" --max-uses 1 --days 30
uv run python -m app.cli invite list
```

## 测试

```bash
cd backend
uv run pytest ../test/
```

## 数据库

- 文件：`backend/travel.db`（SQLite，生产建议开启 WAL）
- 表结构以 `backend/scripts/init_db.py` 为准，可重复执行
- 开发期表结构变更：删除数据库文件后执行 `uv run python scripts/init_db.py`

## 生产部署要点

- 单 worker 启动：`uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`
- 配置全部通过环境变量注入，代码中不含密钥与部署地址
- 若使用 nginx 反代，需设置 `proxy_read_timeout 130s`
- 建议定期备份 `travel.db`

## 文档导航

| 内容 | 位置 |
|---|---|
| 需求文档（6 份） | `需求文档/` |
| 用户故事 | `需求文档/user-stories.md` |
| 接口文档 | `开发文档/接口文档.md` |
| 数据库设计 | `开发文档/数据库设计.md` |
| 邀请码管理 | `开发文档/邀请码管理.md` |

## 开源说明

本项目为个人学习 / 实践项目，文档与代码同步演进。如需试用，请自备 DeepSeek API Key，并遵守相关服务条款。
