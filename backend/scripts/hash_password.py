"""生成本地登录密码的 scrypt 哈希（AUTH_PASSWORD_HASH）。

用法（backend/ 下）：
  Linux:   ../.venv/bin/python scripts/hash_password.py
  Windows: ..\\.venv\\Scripts\\python.exe scripts\\hash_password.py

输出一行 env 配置，填入仓库根 .env。密码本身不落任何文件。
"""
import getpass
import sys

from app.services.auth_service import hash_password


def main() -> int:
    pw = getpass.getpass("设置登录密码（至少 8 位）: ")
    if len(pw) < 8:
        print("错误: 密码至少 8 位")
        return 1
    if pw != getpass.getpass("再输入一次确认: "):
        print("错误: 两次输入不一致")
        return 1
    print("\n把下面一行填入仓库根 .env：")
    print(f"AUTH_PASSWORD_HASH={hash_password(pw)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
