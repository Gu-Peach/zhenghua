# Agent 环境配置来源

Agent 服务现在只从 `services/agent/.env` 读取 dotenv 文件，不再读取仓库根目录 `.env` 或 `backend/.env`。显式的进程环境变量仍优先于该文件；Agent 配置以 `AGENT_*` 为主。

通过临时配置目录测试确认，即使根目录和 `backend/.env` 存在不同模型设置，也只加载 `services/agent/.env` 中的值。
