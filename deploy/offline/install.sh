#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

case "$(uname -m)" in
  aarch64|arm64) ;;
  *) echo "错误：这个离线包只适用于 ARM64，当前架构是 $(uname -m)" >&2; exit 1 ;;
esac

command -v docker >/dev/null 2>&1 || { echo "错误：没有安装 Docker" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "错误：没有安装 Docker Compose 插件" >&2; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "已生成 .env。请填写 DEEPSEEK_API_KEY 和模型地址，然后重新执行："
  echo "  ./install.sh"
  exit 2
fi

if ! grep -Eq '^DEEPSEEK_API_KEY=.+$' .env; then
  echo "错误：.env 中尚未填写 DEEPSEEK_API_KEY" >&2
  exit 2
fi

for archive in images/team-wiki-arm64.tar images/team-wiki-compiler-arm64.tar; do
  [ -f "$archive" ] || { echo "错误：缺少镜像文件 $archive" >&2; exit 1; }
  echo "导入 $(basename "$archive") ..."
  docker load -i "$archive"
done

echo "启动 compiler 和 web ..."
docker compose up -d compiler web

echo "等待服务健康 ..."
attempt=0
while [ "$attempt" -lt 60 ]; do
  compiler_id="$(docker compose ps -q compiler)"
  web_id="$(docker compose ps -q web)"
  compiler_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$compiler_id" 2>/dev/null || true)"
  web_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$web_id" 2>/dev/null || true)"
  [ "$compiler_health" = healthy ] && [ "$web_health" = healthy ] && break
  attempt=$((attempt + 1))
  sleep 5
done

if [ "${compiler_health:-}" != healthy ] || [ "${web_health:-}" != healthy ]; then
  echo "错误：服务未能按时启动，请检查日志：docker compose logs compiler web" >&2
  exit 1
fi

echo "执行首次知识同步与编译，这一步会调用模型 ..."
docker compose run --rm --no-deps sync /app/.venv/bin/python -m app.sync --once

echo "启动周期同步 ..."
docker compose up -d sync

docker compose exec -T web /app/.venv/bin/python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=10).read().decode())"

port="$(sed -n 's/^WEB_PORT=//p' .env | tail -n 1)"
port="${port:-8000}"
echo "安装完成：浏览器访问 http://<ARM机器IP>:$port"
echo "查看状态：cd $(pwd) && docker compose ps"
echo "查看日志：cd $(pwd) && docker compose logs -f"
