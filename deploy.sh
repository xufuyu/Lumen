#!/usr/bin/env bash
# 本地手动部署脚本 — 复用 CI 的逻辑
# 用法: RELAY_CA_PEM_FILE=./ca.pem DEPLOY_HOST=x.x.x.x DEPLOY_USER=ubuntu bash deploy.sh

set -euo pipefail
cd "$(dirname "$0")"

RELAY_HOST="${RELAY_HOST:-218.244.157.7}"
OLD_HOST="advx.fzxufuyu.eu.org"
DEPLOY_HOST="${DEPLOY_HOST:?需要环境变量 DEPLOY_HOST}"
DEPLOY_USER="${DEPLOY_USER:-ubuntu}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
RELAY_CA_PEM_FILE="${RELAY_CA_PEM_FILE:?需要环境变量 RELAY_CA_PEM_FILE 指向本地 CA PEM 文件}"

echo "==> 前端构建"
(cd frontend && npm ci --prefer-offline --no-audit --no-fund && npx vite build --outDir ../deploy/static --emptyOutDir)

echo "==> 后端打包"
mkdir -p deploy/backend
cp -r backend/* deploy/backend/
find deploy/backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
rm -f deploy/backend/.env

echo "==> 替换 $OLD_HOST → $RELAY_HOST"
grep -rl "$OLD_HOST" deploy/ 2>/dev/null | xargs -I{} sed -i "s|$OLD_HOST|$RELAY_HOST|g" {}

echo "==> 注入 CA 证书"
mkdir -p deploy/backend/certs
cp "$RELAY_CA_PEM_FILE" deploy/backend/certs/relay-ca.pem
openssl x509 -in deploy/backend/certs/relay-ca.pem -noout -subject -dates

echo "==> 生成 .env"
cat > deploy/lumen.env <<ENV
RELAY_BASE_URL=https://${RELAY_HOST}/v1
RELAY_API_KEY=sk-relay
ASR_RELAY_WS_URL=wss://${RELAY_HOST}/v1/realtime/asr/stream
RELAY_CA_BUNDLE=/opt/lumen/backend/certs/relay-ca.pem
RELAY_TLS_INSECURE=false
MODEL_PRO=deepseek-v4-flash
MODEL_FLASH=deepseek-v4-flash
DATABASE_URL=sqlite+aiosqlite:////opt/lumen/data/adventurex.db
AUTO_PROCESS=true
ENV

echo "==> rsync 到 $DEPLOY_HOST"
rsync -avz --delete -e "ssh -p $DEPLOY_PORT" \
    deploy/ "$DEPLOY_USER@$DEPLOY_HOST:/tmp/lumen-deploy/"

echo "==> 远端安装 & 重启"
ssh -p "$DEPLOY_PORT" "$DEPLOY_USER@$DEPLOY_HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
APP_DIR=/opt/lumen

if [ ! -d "$APP_DIR" ]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3 python3-venv python3-pip
  sudo id lumen &>/dev/null || sudo useradd -r -s /bin/false -d $APP_DIR lumen
  sudo mkdir -p $APP_DIR/data
fi

sudo systemctl stop lumen 2>/dev/null || true
sudo mkdir -p $APP_DIR/backend $APP_DIR/static
sudo rsync -a --delete --exclude='.venv' --exclude='certs' \
    /tmp/lumen-deploy/backend/ $APP_DIR/backend/
sudo rsync -a /tmp/lumen-deploy/backend/certs/ $APP_DIR/backend/certs/
sudo rsync -a --delete /tmp/lumen-deploy/static/ $APP_DIR/static/
sudo cp /tmp/lumen-deploy/lumen.env $APP_DIR/.env
sudo chmod 600 $APP_DIR/.env

if [ ! -x $APP_DIR/backend/.venv/bin/python ]; then
  sudo python3 -m venv $APP_DIR/backend/.venv
fi
sudo $APP_DIR/backend/.venv/bin/pip install --upgrade pip -q
sudo $APP_DIR/backend/.venv/bin/pip install -r $APP_DIR/backend/requirements.txt -q
sudo chown -R lumen:lumen $APP_DIR

sudo tee /etc/systemd/system/lumen.service >/dev/null <<'UNIT'
[Unit]
Description=拾光 · Lumen API
After=network-online.target

[Service]
Type=simple
User=lumen
Group=lumen
WorkingDirectory=/opt/lumen/backend
EnvironmentFile=/opt/lumen/.env
ExecStart=/opt/lumen/backend/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/lumen/data

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable lumen
sudo systemctl restart lumen
rm -rf /tmp/lumen-deploy

sleep 3
sudo systemctl is-active --quiet lumen && echo "✓ 运行中" || {
  sudo journalctl -u lumen -n 30 --no-pager
  exit 1
}
curl -sf http://127.0.0.1:8000/api/health && echo
REMOTE

rm -rf deploy
echo "==> 部署完成"
