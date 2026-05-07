# 银屑病图像辅助诊断系统（运行说明）

## 目录结构
- `backend`：后端服务、数据库、模型文件、训练与推理逻辑
- `frontend`：前端页面（用户端 + 管理端）

## 后端启动（虚拟环境）
```powershell
cd app/backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

后端默认地址：`http://127.0.0.1:5000`

## 前端启动
```powershell
cd app/frontend
npm install
npm run dev
```

前端默认地址：`http://127.0.0.1:5173`（已代理`/api`到后端）

## 默认账号
- 管理员：`admin / admin123`
- 用户：`demo / demo123`

## 数据集位置
- 默认读取：`app/backend/storage/datasets/IMG_CLASSES`
- 当前工程已将该目录映射到现有数据集，可直接在管理端查看数据统计并发起训练。

