from decimal import Decimal

from app.models.models import Transaction


class BeancountGenerator:
    """单笔 Transaction → Beancount 文本（测试与展示用）。
    正式导出渲染逻辑在 services/export_service.py 的 render_preview()，
    两者必须保持同一业务口径。"""

    @staticmethod
    def generate_transaction(txn: Transaction) -> str:
        lines = []
        # 日期 * "Payee" "Description"
        payee = txn.merchant or ""
        description = txn.description or ""
        lines.append(f'{txn.date} * "{payee}" "{description}"')

        # Metadata
        lines.append(f'  id: "{txn.id}"')
        if txn.raw_transaction_id:
            lines.append(f'  raw_id: "{txn.raw_transaction_id}"')

        # Splits
        for split in txn.splits:
            amount = Decimal(split.amount).quantize(Decimal("0.01"))
            lines.append(f'  {split.account:<30} {amount:>12} {txn.currency}')

        return "\n".join(lines)
