import os
import re

class LedgerManager:
    MANAGED_BEGIN = ";; ===== BeanWEB MANAGED BEGIN ====="
    MANAGED_END = ";; ===== BeanWEB MANAGED END ====="

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
