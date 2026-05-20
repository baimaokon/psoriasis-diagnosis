# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
# 后端
cd backend
pip install -r requirements.txt          # 首次：安装依赖
cp .env.example .env                     # 首次：配置数据库密码
python -m flask init-db                   # 首次：初始化数据库表 + 默认账户
python -m flask init-db --drop            # 删表重建（重设默认账户密码）
python run.py                             # 启动后端 (http://127.0.0.1:5000)

# 测试（使用 SQLite 内存库，无需 MySQL）
python -m pytest tests/ -v                # 全部 55 项
python -m pytest tests/test_auth.py -v    # 单文件
python -m pytest tests/ -q --tb=short     # 快速冒烟

# 前端
cd frontend
npm install                               # 首次
npm run dev                               # 启动前端 (http://127.0.0.1:5173)
```

## 架构总览

```
frontend (Vue 3 + Vite :5173) ──proxy /api──> backend (Flask :5000) ──> MySQL
```

**后端分层（4 层）**：
1. `routes/` — HTTP 入口，5 个 Blueprint（test/auth/user/admin/feedback），只做参数提取和响应返回
2. `services/` — 核心业务逻辑，不依赖 Flask request/response，可独立测试
3. `models/` — SQLAlchemy ORM，5 张表（User/DiagnosisRecord/DiagnosisFeedback/TrainingJob/ModelVersion）
4. `utils/` — 工具函数（JWT 装饰器、统一响应格式、标签映射）

**前端分层**：
- `api/` — Axios 封装，`request.js` 统一注入 Token + 解包响应 + 401 跳转
- `store/modules/session.js` — Pinia 双角色会话管理（role=0 用户，role=1 管理员）
- `router/index.js` — 路由守卫，按 meta.role 限制页面访问

## 关键设计

### 数据库
- 开发：MySQL `skin_diagnosis`，密码通过 `backend/.env` 的 `DB_PASSWORD` 设置
- 测试：SQLite `:memory:`，由 `conftest.py` 通过 `DATABASE_URL=sqlite:///:memory:` 注入，无需 MySQL
- `config.py` 中 `SQLALCHEMY_ECHO` 仅在 `FLASK_ENV=development` 时开启

### 认证机制
- JWT HS256，7 天过期，载荷含 `user_id` + `role`
- `login_required` 装饰器 → 提取 Bearer Token → 解码注入 `g.user_id` / `g.user_role`
- `admin_required` 装饰器 → 检查 `g.user_role == 1`，否则 403
- 前端 `request.js` 拦截器：所有请求自动注 Token，401 自动清除会话并跳转登录页
- 登录接口自身的 401 不触发热跳转（通过 URL 判断 `/auth/login`、`/auth/admin/login`）

### 默认账户
- 首次运行 `flask init-db` 自动创建 `admin` (role=1) 和 `demo` (role=0)
- 密码优先级：环境变量 `DEFAULT_ADMIN_PASSWORD` / `DEFAULT_DEMO_PASSWORD` → `.default_passwords` 缓存文件 → 随机生成并打印到控制台

### 推理引擎
- 单例 `inference_engine`（`InferenceEngine` 实例）
- 模型缓存：首次请求加载，后续复用，上线新模型自动热切换
- 线程安全：双重检查锁（`threading.Lock`）防并发竞态
- `predict()` 返回：预测标签、置信度、Top-3、Grad-CAM 热力图文件名

### 训练流程
- 后台线程 `TrainingManager` 执行训练，`TrainEventHub` 通过 SSE 推送进度
- `AsyncJobWriter` / `AsyncCheckpointWriter` 异步写库和保存权重
- DDP 分布式训练支持：`module.` 前缀权重自动兼容

### Grad-CAM
- Hook 捕获最后卷积层特征图 → 全局平均池化梯度 → 加权求和 + ReLU → 双线性上采样 → 伪彩色叠加原图

## 注意事项

- **Windows 开发**：`requirements.txt` 指定了 CUDA 12.1 版本，CPU 推理需手动改为 CPU 版 PyTorch
- **`.env` 和 `.secret_key` 已 gitignore**，切勿提交
- **`storage/` 目录 7.4GB**（含 3.3 万张图片的数据集），不在版本库中
- **`config.py` 中 LOG_FILE** 在模块加载时求值，比 `create_app()` 早
- 测试中的 `test_app` fixture 设置 `FLASK_ENV=testing` → `DEBUG=False`，`_seed_default_accounts_safe()` 不自动执行
- `user.py` 中的 `imghdr` 在 Python 3.13 已弃用，后续需迁移
