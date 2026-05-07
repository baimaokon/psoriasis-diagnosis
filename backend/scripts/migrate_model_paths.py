import argparse
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.model_path import to_model_relative_path


def migrate_model_paths(db_path: Path, model_dir: Path, apply: bool = False):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, model_path FROM model_versions ORDER BY id ASC")
        rows = cur.fetchall()
        updates = []
        for row_id, raw_path in rows:
            old_path = str(raw_path or "")
            new_path = to_model_relative_path(old_path, model_dir)
            if new_path and new_path != old_path:
                updates.append((int(row_id), old_path, new_path))

        if apply and updates:
            cur.executemany(
                "UPDATE model_versions SET model_path = ? WHERE id = ?",
                [(item[2], item[0]) for item in updates],
            )
            conn.commit()

        return {
            "total": len(rows),
            "changed": len(updates),
            "updates": updates,
            "applied": bool(apply),
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="将 model_versions.model_path 迁移为 models 目录下的相对路径"
    )
    parser.add_argument(
        "--db",
        default=str(BACKEND_DIR / "storage" / "data" / "app.db"),
        help="sqlite 数据库路径",
    )
    parser.add_argument(
        "--model-dir",
        default=str(BACKEND_DIR / "storage" / "models"),
        help="模型目录路径",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行写入；不加时仅预览（dry-run）",
    )
    args = parser.parse_args()

    result = migrate_model_paths(
        db_path=Path(args.db).resolve(),
        model_dir=Path(args.model_dir).resolve(),
        apply=bool(args.apply),
    )
    print(f"total={result['total']} changed={result['changed']} applied={result['applied']}")
    for row_id, old_path, new_path in result["updates"]:
        print(f"[{row_id}] {old_path} -> {new_path}")


if __name__ == "__main__":
    main()
