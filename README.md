# 银屑病图像辅助诊断系统

基于深度学习的皮肤疾病图像辅助诊断平台，支持银屑病、湿疹、黑色素瘤等多种常见皮肤病的 AI 诊断。系统采用 Flask + Vue 3 前后端分离架构，集成了 EfficientNet-B0 / ResNet50 / InceptionV3 等多种预训练模型，支持 Grad-CAM 热力图可视化、中文 PDF 诊断报告生成，并提供完善的模型训练管理和人机协同反馈机制。

## 功能特性

**用户端**
- 上传皮肤镜像图片，AI 自动诊断并给出类别与置信度
- Grad-CAM 热力图叠加，直观展示模型关注区域
- 诊断历史记录查看、搜索与分页
- 对诊断结果提交纠错反馈（人机协同）
- 一键生成中文 PDF 诊断报告

**管理端**
- 数据集管理：类别分布统计、数据质量分析（模糊检测 + SHA256 去重）
- 模型训练：支持模型选择、超参数调整、K 折交叉验证
- SSE 实时推送训练进度（loss、准确率曲线）
- 模型版本管理：多版本并存，一键上线/下线切换，支持下载
- 诊断记录管理：全量检索与详情查看
- 反馈统计：AI 诊断准确率统计面板

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python 3 + Flask + SQLAlchemy |
| 前端框架 | Vue 3 + Vite + Element Plus + Pinia |
| 深度学习 | PyTorch + torchvision（EfficientNet-B0 / ResNet50 / InceptionV3） |
| 数据库 | MySQL（开发库 `skin_diagnosis`），PyMySQL 驱动 |
| 认证 | PyJWT，Bearer Token，双角色（0=普通用户，1=管理员） |
| 实时通信 | SSE（Server-Sent Events，训练进度推送） |
| 报告生成 | fpdf2（中文 PDF） |
| 图像处理 | Pillow + OpenCV |

## 项目结构

```
├── backend/                    # Flask 后端服务
│   ├── run.py                  # 应用入口
│   ├── config.py               # 配置管理（数据库、密钥）
│   ├── requirements.txt        # Python 依赖
│   ├── .env.example            # 环境变量模板
│   └── app/
│       ├── __init__.py         # Flask 工厂函数，注册蓝图
│       ├── models/             # SQLAlchemy 数据模型
│       │   ├── user.py         # 用户（role=0 普通用户, role=1 管理员）
│       │   ├── diagnosis_record.py   # 诊断记录
│       │   ├── diagnosis_feedback.py # 诊断反馈
│       │   ├── training_job.py       # 训练任务
│       │   └── model_version.py      # 模型版本
│       ├── routes/             # API 路由（Blueprint）
│       │   ├── auth.py         # 认证 /api/auth/*
│       │   ├── user.py         # 用户端 /api/user/*
│       │   ├── admin.py        # 管理端 /api/admin/*
│       │   └── feedback.py     # 反馈 /api/feedback/*
│       ├── services/           # 核心业务逻辑
│       │   ├── inference_service.py   # 推理引擎 + Grad-CAM + 模型缓存
│       │   ├── training_service.py    # 训练流程管理 + DDP
│       │   ├── dataset_service.py     # 数据集加载与划分
│       │   ├── model_factory.py       # 模型构建（预训练 + 冻结）
│       │   ├── quality_service.py     # 数据质量分析
│       │   └── report_service.py      # PDF 报告生成
│       ├── utils/              # 工具函数
│       │   ├── auth.py         # JWT 装饰器（login_required）
│       │   ├── response.py     # 统一响应格式
│       │   └── label_mapping.py # 疾病标签映射
│       ├── tests/              # pytest 单元测试（88 个用例）
│       └── storage/            # 运行时数据存储
│           ├── uploads/        # 用户上传图片
│           ├── heatmaps/       # Grad-CAM 热力图
│           ├── models/         # 训练好的模型权重
│           ├── checkpoints/    # 训练检查点
│           └── datasets/       # 数据集
│               ├── IMG_CLASSES/          # 默认数据集（按类别分子目录）
│               ├── IMG_CLASSES_QUICK1660/ # 轻量数据集
│               └── ISIC2020/             # ISIC 2020 皮肤镜数据集
├── frontend/                   # Vue 3 前端
│   ├── vite.config.js          # Vite 配置（含 /api 代理）
│   └── src/
│       ├── router/index.js     # 路由 + 导航守卫（角色权限）
│       ├── utils/auth.js       # Token 与用户信息管理
│       ├── api/                # API 请求封装
│       │   ├── request.js      # Axios 拦截器（注入 Token，解包响应）
│       │   ├── auth.js         # 认证 API
│       │   ├── user.js         # 用户端 API
│       │   ├── admin.js        # 管理端 API
│       │   └── feedback.js     # 反馈 API
│       ├── views/              # 页面组件
│       │   ├── user/           # 用户端页面（诊断、历史、报告）
│       │   └── admin/          # 管理端页面（数据集、训练、模型管理）
│       └── components/         # 可复用组件
```

## 快速启动

### 环境要求

- Python 3.8+
- Node.js 16+
- MySQL 5.7+（或 MariaDB 10.2+）

### 1. 数据库准备

创建 MySQL 数据库：

```sql
CREATE DATABASE skin_diagnosis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 后端启动

```powershell
cd backend

# 创建虚拟环境（首次）
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 配置数据库密码
cp .env.example .env
# 编辑 .env 文件，填写 DB_PASSWORD=你的MySQL密码

# 初始化数据库表（首次运行）
.\.venv\Scripts\python -m flask init-db

# 启动后端服务
.\.venv\Scripts\python run.py
```

后端默认地址：`http://127.0.0.1:5000`

### 3. 前端启动

```powershell
cd frontend
npm install
npm run dev
```

前端默认地址：`http://127.0.0.1:5173`（已配置代理将 `/api` 转发到后端 `127.0.0.1:5000`）

### 4. 默认账户

首次启动系统会自动创建两个默认账户，密码随机生成并打印到控制台。也可通过环境变量预设：

| 用户名 | 角色 | 环境变量预设密码 |
|--------|------|-----------------|
| `admin` | 管理员 (role=1) | `DEFAULT_ADMIN_PASSWORD` |
| `demo` | 普通用户 (role=0) | `DEFAULT_DEMO_PASSWORD` |

## 数据集

### 数据集结构

系统默认读取 `backend/storage/datasets/IMG_CLASSES/`，要求按类别分子目录存放：

```
IMG_CLASSES/
├── 银屑病/
│   ├── img001.jpg
│   ├── img002.jpg
│   └── ...
├── 湿疹/
│   ├── img001.jpg
│   └── ...
└── 黑色素瘤/
    └── ...
```

当前已包含的数据集：

| 数据集 | 路径 | 说明 |
|--------|------|------|
| IMG_CLASSES | `storage/datasets/IMG_CLASSES/` | 10 个类别，约 4 万张皮肤镜像 |
| IMG_CLASSES_QUICK1660 | `storage/datasets/IMG_CLASSES_QUICK1660/` | 轻量子集，1660 张，用于快速验证 |
| ISIC2020 | `storage/datasets/ISIC2020/` | ISIC 2020 皮肤镜挑战数据集（需预处理） |

### 添加新数据集

有两种方式将新数据集融入现有训练：

**方式一：合并到 IMG_CLASSES（推荐）**

如果新数据集类别与现有数据集重合，直接将图片按类别放入 `IMG_CLASSES/` 对应子目录即可：

```bash
# 例如将 ISIC2020 中某类别图片合并到对应目录
cp ISIC2020/某类别/*.jpg IMG_CLASSES/类别名/
```

之后在管理端刷新数据统计即可看到更新后的类别分布。

**方式二：独立数据集训练**

如果新数据集类别不重合或希望单独训练，将数据集按类别分子目录放到 `storage/datasets/` 下，通过管理端的"数据集路径"指定该目录训练即可。

### 数据集要求

- 至少 2 个类别
- 总图片数 ≥ 20 张
- 支持格式：jpg / jpeg / png / bmp / webp

## 核心工作流

### 诊断流程

```
用户上传图片 → 魔数校验 + PIL 安全验证
  → InferenceEngine 加载当前上线模型
  → 模型推理 → 输出类别 + 置信度
  → Grad-CAM 生成热力图（叠加原图）
  → 返回诊断结果 + 热力图 URL
```

### 训练流程

```
管理端配置参数（模型/批次/学习率/折数）
  → 提交训练任务 → 后台线程启动训练
  → 数据集分层随机划分（训练/验证/测试）
  → ImageCache 缓存预处理图像
  → 训练循环（支持 K 折交叉验证）
  → SSE 实时推送 loss/accuracy 到前端
  → 训练完成 → 保存模型权重到 ModelVersion
```

### 模型上线

管理端的"模型版本"页面列出所有已训练的模型，点击"上线"（设置 `is_active=true`），推理引擎会立即切换到新模型，无需重启服务。

### Grad-CAM 可视化

训练/推理时自动生成：注册 hook 捕获最后卷积层特征图 → 全局平均池化梯度作为权重 → 加权求和 + ReLU → 双线性上采样到原图分辨率 → 伪彩色叠加并保存到 `storage/heatmaps/`。

## 运行测试

```bash
cd backend
.\.venv\Scripts\python -m pytest tests/ -v
```

测试使用 SQLite 内存数据库（`conftest.py`），无需 MySQL 环境。

## 配置说明

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `DB_PASSWORD` | 数据库密码（必填） | — |
| `DB_USER` | 数据库用户名 | `root` |
| `DB_HOST` | 数据库主机 | `localhost` |
| `DB_PORT` | 数据库端口 | `3306` |
| `DB_NAME` | 数据库名称 | `skin_diagnosis` |
| `DATABASE_URL` | 完整连接字符串（优先于上述字段） | — |
| `DEFAULT_ADMIN_PASSWORD` | 预设管理员密码 | 随机生成 |
| `DEFAULT_DEMO_PASSWORD` | 预设演示用户密码 | 随机生成 |

所有配置通过 `backend/.env` 文件管理（不会提交到版本库）。

## 安全说明

- 镜像上传使用魔数校验 + PIL 二次验证，防止文件伪装和像素炸弹攻击
- 密码通过 `.env` 管理，`.env` 和 `.secret_key` 已加入 `.gitignore`
- JWT Token 认证，前端 Axios 拦截器自动注入 Bearer Token
- 路由守卫根据角色（0/1）限制页面访问权限
