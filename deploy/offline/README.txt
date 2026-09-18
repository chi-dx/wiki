鲲鹏知识库 ARM64 离线安装包
============================

目标机器要求：
- ARM64 Linux（uname -m 显示 aarch64 或 arm64）
- 已离线安装 Docker Engine 和 Docker Compose 插件
- 能访问配置的 DeepSeek 或 OpenAI 兼容模型地址

安装：
1. tar -xzf wiki-arm64-offline-*.tar.gz
2. cd wiki-arm64-offline
3. cp .env.example .env
4. 编辑 .env，填写 DEEPSEEK_API_KEY 和模型地址
5. chmod +x install.sh
6. ./install.sh

日常命令：
- docker compose ps
- docker compose logs -f
- docker compose restart
- docker compose down（保留数据）

不要执行 docker compose down -v，除非明确要删除全部知识数据和反馈。
