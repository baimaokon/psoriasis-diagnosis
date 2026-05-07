import logging
from pathlib import Path

import click
from flask import Flask, abort, current_app, send_from_directory
from flask_cors import CORS

from app.extensions import db
from app.models import User
from app.routes import admin_bp, auth_bp, feedback_bp, test_bp, user_bp


def _ensure_storage_dirs(app: Flask):
    for key in (
        "STORAGE_DIR",
        "DATA_DIR",
        "MODEL_DIR",
        "CHECKPOINT_DIR",
        "UPLOAD_DIR",
        "HEATMAP_DIR",
    ):
        path = Path(app.config[key])
        path.mkdir(parents=True, exist_ok=True)


def _seed_default_accounts_safe():
    """安全地种子化默认账户，避免重复插入"""
    try:
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", role=1)
            admin.set_password("admin123")
            db.session.add(admin)
            current_app.logger.info("创建管理员账户：admin")
        
        if not User.query.filter_by(username="demo").first():
            demo = User(username="demo", role=0)
            demo.set_password("demo123")
            db.session.add(demo)
            current_app.logger.info("创建测试用户账户：demo")
        
        db.session.commit()
        current_app.logger.info("默认账户创建成功")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"创建默认账户失败：{e}")
        raise


def _init_database(app: Flask, drop_tables: bool = False):
    """
    初始化数据库
    
    Args:
        app: Flask 应用实例
        drop_tables: 是否先删除所有表（谨慎使用）
    """
    with app.app_context():
        try:
            if drop_tables:
                app.logger.warning("⚠️  正在删除所有数据库表...")
                db.drop_all()
                app.logger.info("所有表已删除")
            
            app.logger.info("正在创建数据库表...")
            db.create_all()
            app.logger.info("数据库表创建成功")
            
            app.logger.info("正在初始化默认账户...")
            _seed_default_accounts_safe()
            
            app.logger.info("✅ 数据库初始化完成")
        except Exception as e:
            app.logger.error(f"数据库初始化失败：{e}")
            raise


def create_app():
    app = Flask(__name__)
    app.config.from_object("config")
    CORS(app)
    
    # 配置日志
    log_dir = Path(app.config.get("STORAGE_DIR", "storage")) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    handler = logging.FileHandler(log_dir / "app.log", encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s] %(message)s'
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG)
    app.logger.info("=" * 50)
    app.logger.info("应用启动中...")
    app.logger.info(f"数据库连接：{app.config.get('SQLALCHEMY_DATABASE_URI')}")

    _ensure_storage_dirs(app)
    db.init_app(app)

    # 注册 Flask CLI 命令
    @app.cli.command("init-db")
    @click.option("--drop", is_flag=True, help="先删除所有表并重新初始化（危险操作）")
    def init_db_command(drop):
        """
        初始化数据库
        
        用法:
            flask init-db              # 正常初始化
            flask init-db --drop       # 删除所有表后重新初始化
        """
        _init_database(app, drop_tables=drop)
        click.echo("✅ 数据库初始化完成")

    app.register_blueprint(test_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(feedback_bp)

    @app.route("/api/files/<path:relative_path>", methods=["GET"])
    def get_storage_file(relative_path):
        file_path = Path(relative_path)
        if file_path.is_absolute() or ".." in file_path.parts:
            abort(400)
        root_dir = Path(app.config["STORAGE_DIR"])
        full_path = root_dir / file_path
        if not full_path.exists() or not full_path.is_file():
            abort(404)
        return send_from_directory(root_dir, file_path.as_posix())

    @app.route("/api/files/datasets/<path:relative_path>", methods=["GET"])
    def get_dataset_file(relative_path):
        """专门用于访问数据集文件的端点"""
        from urllib.parse import unquote
        
        decoded_path = unquote(relative_path)
        file_path = Path(decoded_path)
        
        if file_path.is_absolute() or ".." in file_path.parts:
            abort(400)
        
        dataset_root = Path(app.config["DATASET_DIR"])
        full_path = dataset_root / file_path
        
        if not full_path.exists() or not full_path.is_file():
            app.logger.warning(f"数据集文件不存在: {full_path}")
            abort(404)
        
        return send_from_directory(dataset_root, file_path.as_posix())

    # 开发环境下自动初始化数据库（生产环境建议使用 CLI 命令）
    if app.debug:
        with app.app_context():
            try:
                db.create_all()
                app.logger.info("数据库表检查完成（开发模式）")
                _seed_default_accounts_safe()
            except Exception as e:
                app.logger.error(f"数据库初始化失败：{e}")
                raise

    return app
