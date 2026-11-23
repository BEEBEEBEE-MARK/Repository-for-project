# CLAUDE.md — 旅梦规划助手（旅行计划生成）

带登录注册的 AI 旅行计划生成应用：填写出行条件 → DeepSeek 生成结构化行程 → 保存 / 历史管理 / PDF 导出。
采用 **Spec Coding 流程**：需求文档 → 原型 → 接口/数据库设计 → 编码 → 测试。**编码前必须先读对应需求文档（见「文档导航」），接口与文案以需求文档为准，不得自行发挥。**

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | 原生 HTML + CSS + JavaScript（ES6，无框架、无构建工具） |
| 后端 | Python 3.12+ · FastAPI · uv 管理依赖 |
| 数据库 | SQLite（SQLAlchemy 2.x 访问） |
| AI | DeepSeek API（`deepseek-flash`，Anthropic 兼容端点） |

## 目录结构

```
/travel plan/
├── 需求文档/      # 6 份需求文档 + user-stories.md（开发的唯一依据）
├── 原型图/        # 原型 HTML（frontend 由此复制完善）
├── 开发文档/      # 接口文档、数据库设计（编码前产出，前后端契约）
├── backend/       # FastAPI 后端
│   ├── app/
│   │   ├── main.py        # 应用入口
│   │   ├── cli.py         # 命令行工具（邀请码签发 / 查看 / 停用）
│   │   ├── core/          # 配置(.env)、安全(JWT/密码哈希)
│   │   ├── models/        # SQLAlchemy 模型
│   │   ├── schemas/       # Pydantic 模型（请求/响应）
│   │   ├── api/           # 路由：auth / plans / export
│   │   └── services/      # LLM 封装、图库、PDF 渲染
│   ├── pyproject.toml     # uv 依赖清单
│   ├── .env               # 配置与密钥（不入库、不外发；见「部署约定」）
│   ├── scripts/init_db.py # 建库脚本（标准库 sqlite3，可重复执行）
│   └── travel.db          # SQLite 正式数据库（运行时/初始化生成）
├── frontend/      # 前端静态站
│   ├── login.html         # 登录 / 注册
│   ├── index.html         # 主页面
│   ├── generate.html      # 生成页（表单 + 结果两态）
│   ├── plans.html         # 我的旅行计划 · 列表
│   ├── plan-detail.html   # 我的旅行计划 · 详情
│   ├── css/base.css          # 设计 token + 公共组件（顶部栏、toast、模态框）
│   ├── css/plan-content.css  # 计划内容渲染样式（生成结果页 / 详情页共用）
│   ├── css/home.css          # 主页面样式
│   ├── css/generate.css      # 生成页表单样式
│   ├── css/plans.css         # 列表 / 详情页样式
│   └── js/
│       ├── api.js         # 请求封装 + token 注入 + 统一响应 + 401 处理 + 文件下载
│       ├── auth.js        # 登录态、路由守卫、退出登录
│       ├── layout.js      # 顶部栏公共组件（三处业务页共用）
│       ├── plan-render.js # 计划内容渲染 + 复制文本（结果页 / 详情页共用）
│       └── common.js      # toast / 二次确认 / 剪贴板 / 时间格式化
└── test/          # pytest 后端测试
```

## 开发命令

```bash
# 后端（在 backend/ 下执行）
uv sync                                                   # 按 pyproject.toml 安装依赖
uv run uvicorn app.main:app --reload --port 8000
uv run pytest ../test/

# 邀请码管理
uv run python -m app.cli invite create --note "老王" --max-uses 1 --days 30
uv run python -m app.cli invite list

# 生产启动（无 --reload，单 worker 足够；详见「部署约定」）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# 前端：任意静态服务器（如 VS Code Live Server）打开 frontend/
```

- 后端固定 **8000 端口**；开发期 CORS 放开 localhost 来源（正则匹配任意端口）。
- 密码哈希使用 **bcrypt 库直接调用**（不使用 passlib：passlib 1.7.4 与 bcrypt 4.x 存在已知兼容警告）。
- SQLite 文件 `backend/travel.db`；结构以 `scripts/init_db.py` 为准（可重复执行，与 `create_all` 结果一致）。开发期表结构变更 = **删除该文件后执行 `uv run python scripts/init_db.py`**，不引入 alembic。
- PDF 渲染库：**reportlab**（已拍板）。纯 Python 依赖、Windows/Linux 一致、内存占用低；**不使用 weasyprint**（依赖 GTK/Cairo，Windows 安装复杂且 2G 服务器并发压力大）。
- PDF 生成**零 LLM**（纯数据渲染）：交通/住宿复用保存数据，行前准备按规则生成，景点速查表由每日安排重组；不调用图库。
- 中文字体查找顺序：`app/assets/fonts/` → Windows `simhei.ttf`/`msyh.ttc` → Linux Noto/文泉驿。**simhei 不含半角 ¥（U+00A5）**，渲染前统一替换为全角 ￥（U+FFE5），否则显示空白。

## 接口约定

1. **统一响应** `{"code": 0, "message": "ok", "data": {...}}`
   - `code=0` 成功；失败时 `code` = HTTP 状态码：400 参数错误 / 401 未登录 / 403 越权 / 404 不存在 / 429 触发锁定 / 500 服务器错误
   - `message` 为**可直接展示给用户的中文文案**，与需求文档异常场景表逐字一致
   - 分页 data 固定：`{"list": [...], "total": 12, "page": 1, "page_size": 10}`
   - JSON 字段一律 **snake_case**（与后端一致，前端不做转换）
2. **认证**：JWT（HS256），secret 从 `.env` 的 `JWT_SECRET` 读取
   - 登录/注册成功返回 token，前端存 localStorage，请求头 `Authorization: Bearer <token>`
   - 「记住我」= 7 天过期；未勾选 = 12 小时
   - 401 时前端清除 token 并跳转登录页（全局路由守卫的后端侧）
3. **数据归属（最高优先级约束）**：一切查询与操作必须按 token 解析出的 user_id 过滤；越权返回 403「无权访问」。**不允许存在仅凭资源 ID 即可读写的接口。**
4. **长耗时接口**：计划生成同步等待 ≤120s、PDF 导出 ≤30s（其中 LLM 内部预算 20s，超时静默降级）；接口内部必须设超时，不得无限等待。
5. **注册邀请码**（已拍板新增）：注册接口增加 `invite_code` 字段（必填）
   - 存储：独立表 `invite_codes`（字段见 `开发文档/邀请码管理.md`）；**用户表记录 `invite_code_id`** 用于追溯邀请来源（仅溯源，不参与登录/权限/展示）
   - 校验：码存在 + 已启用 + 未过期 + `used_count < max_uses`，任一不满足统一返回 400「邀请码错误」（不区分原因）；校验不区分大小写
   - 注册成功事务内 `used_count + 1`，用满自动失效
   - 签发：仅站长在服务器通过 CLI 执行，**不提供网页管理入口**，管理口不暴露公网
   - 目的：公网可访问后防止陌生人注册、消耗 DeepSeek 余额

## DeepSeek 调用约定

- API key 从环境变量 `DEEPSEEK_API_KEY` 读取（`backend/.env`），**严禁硬编码到代码**
- **Anthropic 兼容端点**：base_url `https://api.deepseek.com/anthropic`，请求 `POST /v1/messages`
  - 请求头 `x-api-key` + `anthropic-version: 2023-06-01`
  - `system` 必须是独立字段，不能放进 messages
  - 响应从 `content[]` 中取 `type == "text"` 的块拼接（推理模型另有 `thinking` 块，忽略）
  - Anthropic 端点**没有 `response_format`**，JSON 结构由提示词约束 + 上层 `parse_json` 兜底
- 模型 `deepseek-flash`（推理模型）。`DEEPSEEK_DISABLE_THINKING=true` 默认关闭思考：实测 5 天行程 **25s**（开启思考时 69s），结构化输出无需推理链
- 提示词要求：中文输出、字段固定，结构对应生成 PRD 3.3 / 3.3.1（含景点提示、交通方式对比、附近美食三档口径）
- **降级规则按需求文档执行，任何 LLM 失败不得让接口返回 500**：
  - 标题/摘要生成失败 → 规则文案（"目的地+天数+日游"）
  - PDF 增量内容失败 → 静默降级为 7 个复用部分
  - 参考攻略全部无效 → 静默按通用方式生成
- 距离、时长、票价类输出必须保留"以实际为准 / 估算"标注口径；无攻略依据禁止编造店名

## 前端约定

- **从 `原型图/travel-plan-ui-design2026.11.19.html` 复制起步**，按目录结构拆分为 5 个 HTML 页面
- 原型 `:root` 中的 CSS 变量（`--primary:#219C8E` 等）迁入 `css/base.css` 作为**全局设计 token，全站禁止脱离 token 造色值**，保持主题风格统一
- toast / 模态框 / loading 遮罩等公共交互沿用原型实现，抽入公共 CSS/JS
- 路由守卫：除 `login.html` 外，页面加载时 `auth.js` 检查 token，无 token 跳转登录页；接口 401 同样跳转
- `js/api.js` 统一封装 fetch：注入 token → 解析 `{code,message,data}` → `code!==0` 时 toast(message)
- 生成中离开页面需 beforeunload 拦截（PRD §3.2）

## 部署约定（预留，编码时遵守）

目标环境：**阿里云轻量服务器 2核2G + 公网 IP 小范围使用**（不买域名、暂不备案、http 直连）。

1. **配置全部走环境变量**（`.env`）：`JWT_SECRET`、`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`DEEPSEEK_DISABLE_THINKING`、`APP_ENV`、`SQLITE_PATH`。代码中不得出现任何密钥或部署地址。（邀请码存数据库表，不走环境变量）
2. **前端 API_BASE 同源自适应**，部署零改代码：
   ```js
   const API_BASE = ['localhost','127.0.0.1'].includes(location.hostname) ? 'http://localhost:8000' : '';
   ```
   生产由 FastAPI `StaticFiles` 挂载 `frontend/` 提供同源访问，免 CORS 配置。
3. **SQLite 生产参数**：连接时设置 `journal_mode=WAL`、`busy_timeout=5000`；每日用 SQLite backup API 备份（WAL 模式下直接 `cp` 可能不一致），脚本见「线上部署」。
4. **反向代理超时**：若前置 nginx，必须设 `proxy_read_timeout 130s`（生成接口 120s 超时）；云平台安全组放行对应端口。
5. **资源保护**：服务器开 2G swap；PDF 导出加并发信号量（同时 ≤2 份），防止内存叠峰。
6. **剪贴板降级**：http 非安全上下文下 `navigator.clipboard` 不可用，复制功能需回退 `textarea + execCommand('copy')`。
7. **部署文档**（安装 uv / systemd 守护 / 备份 / nginx 示例）在开发文档阶段产出，文件名 `开发文档/部署文档.md`。

## 线上部署（2026-11-23 已上线）

- 地址：`http://43.163.107.121:9000`（腾讯云轻量 Ubuntu 22.04，2 核 / 1.9G）
- 代码目录：`/home/ubuntu/travel-plan`，更新方式 `git pull && sudo systemctl restart travel-plan`
- 服务：systemd `travel-plan.service`（开机自启、崩溃重启、`MemoryMax=512M`）
- 端口：9000（云安全组已开放 9000-10000；9080 / 9999 已被占）
- Python：uv 管理的 3.12.11，依赖走清华源；系统 Python 3.10 未改动
- 配置：`backend/.env`（权限 600，`APP_ENV=production`）
- 备份：`/home/ubuntu/backup/travel_db_backup.sh`，cron 每日 3:00，保留 7 天
- SSH：本机 `ssh my-server` 免密（密钥 `~/.ssh/travel_deploy`）
- 邀请码：已签发正式码；`DEV-DEFAULT` 已停用
- 日志：`sudo journalctl -u travel-plan -f`

## 代码风格

- **Python**：snake_case；补类型注解；Pydantic v2 写法
- **JavaScript**：ES6+（const/let、箭头函数、模板字符串、async/await）；变量与函数 camelCase
- **CSS**：BEM（`.block__element--modifier`）
- 命名见名知意，禁止拼音缩写（如目的地用 destination，不用 mdd）

## 文档导航（编码前必读）

| 开发任务 | 必读文档 |
|---|---|
| 注册 / 登录 | `需求文档/用户注册-需求描述.md`（v1.2，含邀请码）、`需求文档/用户登录-需求描述.md` |
| 邀请码管理 | `开发文档/邀请码管理.md`（表结构 + 命令手册） |
| 主页面 | `需求文档/主页面-需求描述.md` |
| 计划生成 | `需求文档/旅行计划生成-PRD.md`（v1.8，含 3.3.1 每日子结构、3.3.2 住宿推荐、3.3.3 交通信息、3.6 补充攻略优化） |
| 我的旅行计划 | `需求文档/我的旅行计划-PRD.md`（v1.3） |
| PDF 导出 | `需求文档/旅行计划PDF导出-PRD.md`（v1.5） |
| 功能全貌 | `需求文档/user-stories.md`（12 条用户故事） |
| 接口 / 表结构 | `开发文档/`（编码前先产出，作为前后端契约） |

## 当前进度

- ✅ 需求阶段：6 份需求文档收口（生成 v1.5 / 列表 v1.3 / PDF v1.5 / 注册 v1.1 / 登录 v1.1 / 主页面 v1.0）+ 用户故事 12 条
- ✅ 原型：6 视图设计稿已产出并按需求文档核验修订
- ✅ 部署：已于 2026-11-23 上线腾讯云轻量（Ubuntu 22.04, 2核1.9G），详情见「线上部署」
- ✅ 邀请码注册：方案=数据库表 + 命令行签发；注册 PRD v1.2、原型注册页、说明文档《开发文档/邀请码管理.md》均已同步
- ✅ 后端：骨架 + 认证（注册/登录/me）+ 计划接口（生成/保存/列表/详情/删除）
- ✅ 前端：登录 / 主页面 / 生成页 / 我的计划列表 / 详情页 5 页完成
- ✅ PDF 导出：后端 `services/pdf_render.py` + `/api/plans/{id}/pdf` 已实现
- ⬜ 待办：部署文档（`开发文档/部署文档.md`）
- 📌 实测留痕：生成接口 5 天行程 17.9s、3 天 12.2s（远低于 60s 目标；120s 上限为 15 天长行程保留余量）
