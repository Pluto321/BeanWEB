"""存量交易 Layer 4 跨源去重回填（一次性运维工具，默认 dry-run）。

背景：银行 ↔ 银行转账对匹配（形态 3）上线前导入的存量交易不会被回溯标记。
本脚本用与导入时完全相同的口径（DeduplicationService.is_cross_source_pair）
扫描存量交易，把每对「后创建的一侧」标为 POSSIBLE_DUPLICATE +
duplicate_reason=CROSS_SOURCE——与导入时行为一致：先导入的一侧保持原状态；
只标记，绝不自动跳过，裁决权永远在人。

用法（backend/ 目录下运行）：
  ..\\.venv\\Scripts\\python.exe scripts\\backfill_cross_source_dedup.py           # dry-run，只打印计划
  ..\\.venv\\Scripts\\python.exe scripts\\backfill_cross_source_dedup.py --apply   # 落库（自动先备份）

原则 14：--apply 前自动快照到 BACKUP_DIR；生产库写操作需用户明确授权。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.models import Transaction  # noqa: E402
from app.services.backup_service import create_backup  # noqa: E402
from app.services.deduplication import DeduplicationService  # noqa: E402
from app.services.review import AuditService  # noqa: E402

# 候选/标记口径与导入时 find_cross_source_match 一致：
# 候选（可被匹配到）= 未忽略 + 已确认；标记对象 = 仅 REVIEW_REQUIRED
# （导入时 Layer 4 只在 L1–L3 判 UNIQUE 后运行，已 CONFIRMED/已疑似的行不重判）
CANDIDATE_STATUSES = ("REVIEW_REQUIRED", "POSSIBLE_DUPLICATE", "CONFIRMED")
MARKABLE_STATUSES = ("REVIEW_REQUIRED",)


def _txn_view(t: Transaction) -> dict:
    return {
        "date": t.date,
        "amount": t.amount,
        "direction": t.direction,
        "merchant": t.merchant,
        "description": t.description,
        "counterparty": t.counterparty,
        "payment_method": t.payment_method,
        "source_type": t.source_type,
    }


def _desc(t: Transaction) -> str:
    return (f"#{t.id} {t.source_type} {t.date} {t.amount}{t.direction} "
            f"{(t.merchant or '')[:24]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="存量交易 Layer 4 跨源去重回填")
    parser.add_argument("--apply", action="store_true", help="落库（默认 dry-run 只打印计划）")
    args = parser.parse_args()

    db = SessionLocal()
    svc = DeduplicationService()
    try:
        rows = (
            db.query(Transaction)
            .filter(Transaction.status.in_(CANDIDATE_STATUSES))
            .order_by(Transaction.created_at, Transaction.id)
            .all()
        )
        pairs = []
        for i, later in enumerate(rows):
            if later.status not in MARKABLE_STATUSES:
                continue
            later_view = _txn_view(later)
            for earlier in rows[:i]:
                if svc.is_cross_source_pair(later_view, _txn_view(earlier)):
                    pairs.append((earlier, later))
                    break  # 与导入一致：命中首个候选即标
        if not pairs:
            print("未发现需要补标的跨源重复对")
            return 0
        print(f"发现 {len(pairs)} 对（标记后创建的一侧，先导入一侧不动）：")
        for earlier, later in pairs:
            print(f"  标记 {_desc(later)}  ← 对手方 {_desc(earlier)}")
        if not args.apply:
            print("\ndry-run：未写库。确认无误后加 --apply 执行（会先自动备份）。")
            return 0
        backup = create_backup(db)
        print(f"已备份: {backup['file']}（{settings.BACKUP_DIR}）")
        for earlier, later in pairs:
            AuditService.log_change(
                db, "transaction", later.id, "STATUS_CHANGE",
                {"status": later.status, "duplicate_reason": later.duplicate_reason},
                {"status": "POSSIBLE_DUPLICATE", "duplicate_reason": "CROSS_SOURCE"},
                "Layer 4 cross-source backfill",
            )
            later.status = "POSSIBLE_DUPLICATE"
            later.duplicate_reason = "CROSS_SOURCE"
        db.commit()
        print(f"已更新 {len(pairs)} 笔 → POSSIBLE_DUPLICATE/CROSS_SOURCE（人工裁决后确认/忽略）")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
