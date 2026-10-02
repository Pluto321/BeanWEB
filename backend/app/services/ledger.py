import os
import re

class LedgerManager:
    MANAGED_BEGIN = ";; ===== BeanWEB MANAGED BEGIN ====="
    MANAGED_END = ";; ===== BeanWEB MANAGED END ====="
    # 账户自动声明的托管块：导出时确保分录用到的账户已 open（追加式，不碰用户手写行）
    AUTO_OPEN_BEGIN = ";; ===== BeanWEB AUTO-OPEN BEGIN ====="
    AUTO_OPEN_END = ";; ===== BeanWEB AUTO-OPEN END ====="

    _OPEN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) open ([A-Za-z][\w:.-]*)")

    def __init__(self, ledger_dir: str):
        self.ledger_dir = ledger_dir
        self.generated_dir = os.path.join(ledger_dir, "generated")
        os.makedirs(self.generated_dir, exist_ok=True)

    def _atomic_write(self, path: str, content: str):
        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)

    def ensure_accounts_opened(self, accounts: list, open_date: str, currency: str = "CNY"):
        """确保 accounts 里的账户在 accounts.bean 中已 open（自动消除「未知账户」gap）。

        规则：
        - 已 open 的账户（无论手写还是托管块内）跳过；托管块内的行允许把日期改早
          （导出更早日期的交易时，仅调整托管块，用户手写行绝不修改）
        - 未 open 的账户按字母序追加到托管块（BEGIN/END 标记之间）
        - accounts.bean 不存在时创建（main.bean 的 include 链已有 accounts.bean）
        幂等：无变化不写文件。
        """
        accounts_path = os.path.join(self.ledger_dir, "accounts.bean")

        if not os.path.exists(accounts_path):
            content = (
                f";; BeanWEB 账户声明（手写区 + BeanWEB 自动声明托管区）\n"
                f"{self.AUTO_OPEN_BEGIN}\n{self.AUTO_OPEN_END}\n"
            )
            self._atomic_write(accounts_path, content)

        with open(accounts_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        opened: dict = {}          # account -> (date, 手写?)，用于跳过与日期比较
        body: list = []            # 非托管行
        auto_lines: list = []     # 托管块内的行（不含标记行）
        in_auto = False
        auto_begin_idx = auto_end_idx = None

        for i, line in enumerate(lines):
            if self.AUTO_OPEN_BEGIN in line:
                in_auto = True
                auto_begin_idx = i
                continue
            if self.AUTO_OPEN_END in line:
                in_auto = False
                auto_end_idx = i
                continue
            m = self._OPEN_RE.match(line.strip())
            if m:
                opened[m.group(2)] = (m.group(1), in_auto)
            if in_auto:
                auto_lines.append(line)
            else:
                body.append(line)

        missing = sorted({a for a in accounts if a and a not in opened})
        # 托管块内日期需要改早的：仅限本次 ensure 的账户（导出了更早日期的交易），
        # 不影响托管块内其它账户的 open 日期
        ensure_set = {a for a in accounts if a}
        adjusted_auto: list = []
        date_adjusted = False
        for line in auto_lines:
            m = self._OPEN_RE.match(line.strip())
            if m and m.group(2) in ensure_set and m.group(1) > open_date:
                adjusted_auto.append(f"{open_date} open {m.group(2)} {currency}\n")
                date_adjusted = True
            else:
                adjusted_auto.append(line)

        if not missing and not date_adjusted:
            return  # 幂等：全部已 open 且日期无需调整

        new_lines = adjusted_auto + [f"{open_date} open {a} {currency}\n" for a in missing]
        # 托管块整体按账户名排序：保持稳定字母序（追加新账户不破坏既有顺序）
        def _acct(line):
            m = self._OPEN_RE.match(line.strip())
            return m.group(2) if m else ""
        auto_lines = sorted(new_lines, key=_acct)

        # 托管块不存在时（旧版 accounts.bean）：追加到文件尾部
        if auto_begin_idx is None:
            content = "".join(body)
            if content and not content.endswith("\n"):
                content += "\n"
            content += f"{self.AUTO_OPEN_BEGIN}\n" + "".join(auto_lines) + f"{self.AUTO_OPEN_END}\n"
        else:
            content = "".join(body) + f"{self.AUTO_OPEN_BEGIN}\n" + "".join(auto_lines) + f"{self.AUTO_OPEN_END}\n"

        self._atomic_write(accounts_path, content)

    def update_include(self, main_bean_path: str, include_path: str):
        if not os.path.exists(main_bean_path):
            content = f"{self.MANAGED_BEGIN}\ninclude \"accounts.bean\"\ninclude \"{include_path}\"\n{self.MANAGED_END}\n"
            self._atomic_write(main_bean_path, content)
            return

        with open(main_bean_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_content = []
        in_managed = False
        included = False
        managed_lines = []

        for line in lines:
            if self.MANAGED_BEGIN in line:
                in_managed = True
                new_content.append(line)
                continue
            if self.MANAGED_END in line:
                if not included:
                    managed_lines.append(f'include "{include_path}"\n')
                new_content.extend(managed_lines)
                new_content.append(line)
                in_managed = False
                continue
            
            if in_managed:
                if f'include "{include_path}"' in line:
                    included = True
                managed_lines.append(line)
            else:
                new_content.append(line)
        
        self._atomic_write(main_bean_path, "".join(new_content))

    def write_fragment(self, date_str: str, content: str):
        year, month = date_str.split("-")[:2]
        year_dir = os.path.join(self.generated_dir, year)
        os.makedirs(year_dir, exist_ok=True)
        fragment_path = os.path.join(year_dir, f"{month}.bean")
        
        # 追加写入，先写临时文件
        with open(fragment_path, "a", encoding="utf-8") as f:
            f.write(content + "\n")
            f.flush()
            os.fsync(f.fileno())
        return fragment_path
