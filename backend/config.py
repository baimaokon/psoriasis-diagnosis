import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")
STORAGE_DIR = BASE_DIR / "storage"
DATA_DIR = STORAGE_DIR / "data"
MODEL_DIR = STORAGE_DIR / "models"
CHECKPOINT_DIR = STORAGE_DIR / "checkpoints"
UPLOAD_DIR = STORAGE_DIR / "uploads"
HEATMAP_DIR = STORAGE_DIR / "heatmaps"
DATASET_DIR = STORAGE_DIR / "datasets" / "IMG_CLASSES"

# ========== 数据库配置 ==========
# 从环境变量读取数据库 URL（支持多环境部署）
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    # 生产环境：使用环境变量中的完整连接字符串
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
else:
    # 开发环境：使用本地 MySQL
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '3306')
    DB_NAME = os.getenv('DB_NAME', 'skin_diagnosis')

    if not DB_PASSWORD:
        raise RuntimeError(
            "未检测到数据库密码。请设置环境变量 DB_PASSWORD，"
            "或在 backend/.env 文件中写入 DB_PASSWORD=你的密码"
        )
    
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        f"?charset=utf8mb4&connect_timeout=10"
    )

# 数据库连接池配置（仅 MySQL，SQLite 不支持这些参数）
SQLALCHEMY_ENGINE_OPTIONS = {}
if SQLALCHEMY_DATABASE_URI.startswith("mysql"):
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,              # 连接池大小
        'pool_recycle': 3600,         # 连接回收时间（秒）
        'pool_pre_ping': True,        # 使用前检查连接是否有效
        'max_overflow': 20,           # 超出 pool_size 后的最大连接数
    }

SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = os.getenv('FLASK_ENV', 'production') == 'development'

# ========== 安全密钥管理 ==========
def _get_secret_key():
    """获取或生成安全的密钥"""
    # 1. 优先从环境变量读取（生产环境）
    secret_key = os.getenv('SECRET_KEY')
    if secret_key:
        return secret_key
    
    # 2. 从文件读取（开发环境持久化）
    secret_file = BASE_DIR / '.secret_key'
    if secret_file.exists():
        try:
            return secret_file.read_text().strip()
        except Exception:
            pass
    
    # 3. 生成新的随机密钥并保存到文件
    new_secret = secrets.token_hex(32)  # 64 位随机字符串
    try:
        secret_file.write_text(new_secret)
        secret_file.chmod(0o600)  # 设置文件权限为仅所有者可读写
    except Exception:
        pass
    
    return new_secret

SECRET_KEY = _get_secret_key()

# ========== 会话与 Cookie 配置 ==========
SESSION_COOKIE_SECURE = os.getenv('FLASK_ENV', 'development') != 'development'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

# ========== 文件上传配置 ==========
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB
MAX_FORM_MEMORY_SIZE = 10 * 1024 * 1024  # 表单内存限制 10MB

# ========== CORS 跨域配置 ==========
CORS_HEADERS = 'Content-Type'
CORS_SUPPORTS_CREDENTIALS = True

# ========== 日志配置 ==========
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = str(BASE_DIR / 'storage' / 'logs' / 'app.log')
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 10

# ========== 应用配置 ==========
ENV = os.getenv('FLASK_ENV', 'production')
DEBUG = ENV == 'development'
JSON_AS_ASCII = False  # 保持中文正常显示
