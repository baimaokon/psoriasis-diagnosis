"""
SQLite 到 MySQL 数据迁移脚本
用于将旧数据库的数据迁移到新的 MySQL 数据库中
"""

import sqlite3
from pathlib import Path
from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import User, DiagnosisRecord, TrainingJob, ModelVersion


def parse_datetime(datetime_str):
    """解析时间字符串，支持多种格式"""
    if not datetime_str:
        return datetime.now()
    
    # 尝试多种时间格式
    formats = [
        '%Y-%m-%d %H:%M:%S.%f',  # 带微秒
        '%Y-%m-%d %H:%M:%S',      # 不带微秒
        '%Y-%m-%d %H:%M:%S.%f',   # 微秒格式
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(str(datetime_str), fmt)
        except ValueError:
            continue
    
    # 如果都失败，尝试直接返回当前时间
    print(f"  ⚠️  时间格式解析失败：{datetime_str}，使用当前时间")
    return datetime.now()


def get_sqlite_connection():
    """获取 SQLite 数据库连接"""
    base_dir = Path(__file__).resolve().parent
    sqlite_path = base_dir / "storage" / "data" / "app.db"
    
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite 数据库文件不存在：{sqlite_path}")
    
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row  # 返回字典格式
    return conn


def migrate_users(sqlite_conn):
    """迁移用户数据"""
    print("=" * 50)
    print("开始迁移用户数据...")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    
    migrated_count = 0
    for row in rows:
        # 检查用户是否已存在（按用户名判断）
        existing = User.query.filter_by(username=row['username']).first()
        if existing:
            print(f"  ⚠️  用户 {row['username']} 已存在，跳过")
            continue
        
        user = User(
            # 不指定 id，让 MySQL 自动生成
            username=row['username'],
            password_hash=row['password_hash'],
            role=row['role'],
            created_at=parse_datetime(row['created_at'])
        )
        db.session.add(user)
        migrated_count += 1
        print(f"  ✓ 迁移用户：{row['username']} (原 ID: {row['id']})")
    
    db.session.commit()
    print(f"✓ 用户数据迁移完成，共迁移 {migrated_count} 个用户")
    return migrated_count


def migrate_diagnosis_records(sqlite_conn):
    """迁移诊断记录"""
    print("=" * 50)
    print("开始迁移诊断记录...")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT dr.*, u.username 
        FROM diagnosis_records dr
        LEFT JOIN users u ON dr.user_id = u.id
        ORDER BY dr.created_at DESC
    """)
    rows = cursor.fetchall()
    
    migrated_count = 0
    failed_count = 0
    
    for row in rows:
        # 检查用户是否存在
        user = User.query.filter_by(username=row['username']).first()
        if not user:
            print(f"  ⚠️  记录 ID {row['id']} 的用户 {row['username']} 不存在，跳过")
            failed_count += 1
            continue
        
        # 检查记录是否已存在（按用户和创建时间判断）
        existing = DiagnosisRecord.query.filter_by(
            user_id=user.id,
            image_path=row['image_path'],
            created_at=parse_datetime(row['created_at'])
        ).first()
        
        if existing:
            print(f"  ⚠️  记录 ID {row['id']} 已存在，跳过")
            continue
        
        try:
            record = DiagnosisRecord(
                # 不指定 id，让 MySQL 自动生成
                user_id=user.id,
                image_path=row['image_path'] or "",
                heatmap_path=row['heatmap_path'] or "",
                predicted_label=row['predicted_label'] or "",
                confidence=float(row['confidence']) if row['confidence'] else 0.0,
                prediction_json=row['prediction_json'] or "[]",
                created_at=parse_datetime(row['created_at'])
            )
            db.session.add(record)
            migrated_count += 1
            print(f"  ✓ 迁移记录：用户={row['username']}, 预测={row['predicted_label']}")
        except Exception as e:
            print(f"  ✗ 迁移记录 ID {row['id']} 失败：{e}")
            failed_count += 1
    
    db.session.commit()
    print(f"✓ 诊断记录迁移完成，成功 {migrated_count} 条，失败 {failed_count} 条")
    return migrated_count, failed_count


def migrate_training_jobs(sqlite_conn, model_id_map=None):
    """迁移训练任务"""
    print("=" * 50)
    print("开始迁移训练任务...")
    
    if model_id_map is None:
        model_id_map = {}
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM training_jobs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    migrated_count = 0
    
    for row in rows:
        # 检查任务是否已存在（按名称和创建时间判断）
        existing = TrainingJob.query.filter_by(
            name=row['name'],
            created_at=parse_datetime(row['created_at'])
        ).first()
        
        if existing:
            print(f"  ⚠️  任务 '{row['name']}' 已存在，跳过")
            continue
        
        # 尝试映射 model_version_id
        old_model_id = row['model_version_id'] if row['model_version_id'] else None
        new_model_id = model_id_map.get(old_model_id) if old_model_id else None
        
        if old_model_id and not new_model_id:
            print(f"  ⚠️  任务 '{row['name']}' 关联的模型 ID {old_model_id} 未找到映射")
        
        try:
            job = TrainingJob(
                # 不指定 id，让 MySQL 自动生成
                name=row['name'] or "未命名任务",
                status=row['status'] or "queued",
                dataset_dir=row['dataset_dir'] or "",
                params_json=row['params_json'] or "{}",
                logs_json=row['logs_json'] or "[]",
                message=row['message'] or "",
                progress=float(row['progress']) if row['progress'] else 0.0,
                current_epoch=int(row['current_epoch']) if row['current_epoch'] else 0,
                total_epochs=int(row['total_epochs']) if row['total_epochs'] else 0,
                train_loss=float(row['train_loss']) if row['train_loss'] else 0.0,
                val_loss=float(row['val_loss']) if row['val_loss'] else 0.0,
                val_accuracy=float(row['val_accuracy']) if row['val_accuracy'] else 0.0,
                val_precision=float(row['val_precision']) if row['val_precision'] else 0.0,
                val_recall=float(row['val_recall']) if row['val_recall'] else 0.0,
                val_f1=float(row['val_f1']) if row['val_f1'] else 0.0,
                # 使用映射后的 model_version_id
                model_version_id=new_model_id,
                created_at=parse_datetime(row['created_at']),
                updated_at=parse_datetime(row['updated_at']),
                started_at=parse_datetime(row['started_at']) if row['started_at'] else None,
                finished_at=parse_datetime(row['finished_at']) if row['finished_at'] else None,
            )
            db.session.add(job)
            migrated_count += 1
            print(f"  ✓ 迁移任务：{row['name']} ({row['status']})" + 
                  (f" [关联模型：{new_model_id}]" if new_model_id else ""))
        except Exception as e:
            print(f"  ✗ 迁移任务 ID {row['id']} 失败：{e}")
    
    db.session.commit()
    print(f"✓ 训练任务迁移完成，共迁移 {migrated_count} 个任务")
    return migrated_count


def migrate_model_versions(sqlite_conn):
    """迁移模型版本"""
    print("=" * 50)
    print("开始迁移模型版本...")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM model_versions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    migrated_count = 0
    model_id_map = {}
    
    for row in rows:
        # 检查模型是否已存在（按名称和创建时间判断）
        existing = ModelVersion.query.filter_by(
            name=row['name'],
            created_at=parse_datetime(row['created_at'])
        ).first()
        
        if existing:
            print(f"  ⚠️  模型 '{row['name']}' 已存在，跳过")
            continue
        
        try:
            model = ModelVersion(
                # 不指定 id，让 MySQL 自动生成
                name=row['name'] or "未命名模型",
                backbone=row['backbone'] or "unknown",
                model_path=row['model_path'] or "",
                params_json=row['params_json'] or "{}",
                metrics_json=row['metrics_json'] or "{}",
                labels_json=row['labels_json'] or "[]",
                is_active=bool(row['is_active']) if row['is_active'] is not None else False,
                created_at=parse_datetime(row['created_at'])
            )
            db.session.add(model)
            migrated_count += 1
            print(f"  ✓ 迁移模型：{row['name']} ({row['backbone']})")
            model_id_map[row['id']] = model.id
        except Exception as e:
            print(f"  ✗ 迁移模型 ID {row['id']} 失败：{e}")
    
    db.session.commit()
    print(f"✓ 模型版本迁移完成，共迁移 {migrated_count} 个模型")
    return migrated_count, model_id_map


def verify_migration():
    """验证迁移结果"""
    print("=" * 50)
    print("验证迁移结果...")
    
    user_count = User.query.count()
    record_count = DiagnosisRecord.query.count()
    job_count = TrainingJob.query.count()
    model_count = ModelVersion.query.count()
    
    print(f"\nMySQL 数据库统计:")
    print(f"  - 用户数：{user_count}")
    print(f"  - 诊断记录数：{record_count}")
    print(f"  - 训练任务数：{job_count}")
    print(f"  - 模型版本数：{model_count}")
    
    # 检查是否有激活的模型
    active_model = ModelVersion.query.filter_by(is_active=True).first()
    if active_model:
        print(f"\n✓ 当前在线模型：{active_model.name} (ID: {active_model.id})")
    else:
        print(f"\n⚠️  警告：当前没有激活的模型，无法进行诊断")


def main():
    """主函数"""
    print("=" * 60)
    print("SQLite → MySQL 数据迁移工具")
    print("=" * 60)
    
    # 创建 Flask 应用
    app = create_app()
    
    with app.app_context():
        try:
            # 连接 SQLite
            print("\n正在连接 SQLite 数据库...")
            sqlite_conn = get_sqlite_connection()
            print("✓ SQLite 数据库连接成功")
            
            # 开始迁移
            print("\n" + "=" * 60)
            print("开始数据迁移...")
            print("=" * 60 + "\n")
            
            # 1. 先迁移用户（其他表的基础）
            migrate_users(sqlite_conn)
            print()
            
            # 2. 迁移模型版本（训练任务依赖它）
            model_count, model_id_map = migrate_model_versions(sqlite_conn)
            print()
            
            # 3. 迁移训练任务（需要模型 ID 映射）
            migrate_training_jobs(sqlite_conn, model_id_map)
            print()
            
            # 4. 最后迁移诊断记录（依赖用户）
            migrate_diagnosis_records(sqlite_conn)
            
            # 验证迁移
            print("\n" + "=" * 60)
            verify_migration()
            print("=" * 60)
            
            print("\n✓ 数据迁移完成！")
            print("\n提示:")
            print("  1. 刷新管理端页面查看数据")
            print("  2. 如果有模型未激活，请在管理端激活")
            print("  3. 检查图片和热力图文件是否存在")
            
        except FileNotFoundError as e:
            print(f"\n✗ 错误：{e}")
            print("请确保 SQLite 数据库文件存在：backend/storage/data/app.db")
        except Exception as e:
            print(f"\n✗ 迁移过程中发生错误：{e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                sqlite_conn.close()
            except:
                pass


if __name__ == "__main__":
    main()
