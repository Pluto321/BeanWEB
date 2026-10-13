#!/usr/bin/env bash
# BeanWEB 服务器部署脚本（Linux + systemd --user 单元）
# 用法：git pull 后在仓库根执行：bash deploy/install.sh
# 幂等：可重复执行；每次重新生成单元文件并重启服务，改完 .env 后重跑即生效。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/beanweb.service"
UVICORN="$REPO_DIR/.venv/bin/uvicorn"

fail() { echo "错误: $*" >&2; exit 1; }

[ -x "$UVICORN" ] || fail "未找到 $UVICORN；先执行: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
[ -d "$REPO_DIR/frontend/dist" ] || echo "警告: frontend/dist 不存在，UI 不会被 serve；先执行: cd frontend && npm run build"

# 1) 环境变量文件（仓库根 .env，已 gitignore；模板默认 AUTH_ENABLED=false）
if [ ! -f "$ENV_FILE" ]; then
    cp "$REPO_DIR/deploy/env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "已从模板创建 $ENV_FILE（默认 AUTH_ENABLED=false）。启用登录前先填入真实值，再重跑本脚本。"
fi

# 2) 生成 systemd --user 单元（路径按仓库位置推导；DATABASE_URL 走代码默认值 backend/beanweb.db）
mkdir -p "$UNIT_DIR"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=BeanWEB FastAPI backend (uvicorn :8000)
After=network.target

[Service]
WorkingDirectory=$REPO_DIR/backend
EnvironmentFile=$ENV_FILE
ExecStart=$UVICORN main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

# 3) 重载并重启
systemctl --user daemon-reload
systemctl --user restart beanweb

# 4) linger：user 级服务默认随 SSH 登出被系统回收，必须开启
if ! loginctl show-user "$USER" --property=Linger 2>/dev/null | grep -q 'Linger=yes'; then
    if sudo -n loginctl enable-linger "$USER" 2>/dev/null; then
        echo "已开启 linger（服务不再随 SSH 登出停止）"
    else
        echo "提醒: 无法自动开启 linger，请手动执行: sudo loginctl enable-linger $USER"
        echo "      不开启的话，退出 SSH 登录后服务会被系统回收。"
    fi
fi

# 5) 验收（探活重试，覆盖 RestartSec 延迟）
sleep 1
for i in 1 2 3 4 5 6 7 8 9 10; do
    curl -sf http://127.0.0.1:8000/health >/dev/null && break
    [ "$i" = 10 ] && fail "/health 无响应；排查: journalctl --user -u beanweb -n 30"
    sleep 1
done
echo "--- 服务状态 ---"
systemctl --user --no-pager status beanweb | sed -n '1,4p' || true
echo "[OK] /health"
MODE="$(curl -sf http://127.0.0.1:8000/api/auth/me | sed -n 's/.*"mode":"\([a-z]*\)".*/\1/p')"
case "$MODE" in
    oidc)     echo "[OK] /api/auth/me → mode=oidc（登录保护已生效）" ;;
    disabled) echo "[OK] /api/auth/me → mode=disabled（AUTH_ENABLED=false，登录未启用）" ;;
    *)        fail "服务未正常响应；排查: journalctl --user -u beanweb -n 30" ;;
esac
