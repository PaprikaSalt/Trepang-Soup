# Trepang Soup

多人在线、AI担任主持人的好友海龟汤桌面平台。

## 当前交付

- `docs/Trepang Soup 项目规划.docx`：产品与实施规划
- `docs/后端实施指南.md`：Ubuntu 24.04 / WSL 后端实施说明
- `docs/通信协议-v1.md`：HTTP 与 WebSocket 首版契约
- `client/`：Tauri 2 + Vue 3 + TypeScript Windows 客户端
- `server/`：可供客户端联调的 FastAPI HTTP/WebSocket 服务端
- `release/`：本地构建的 Windows x64 安装包目录（不提交到 Git）

## 当前开发阶段

Windows 客户端已经接入服务端的 HTTP/WebSocket 多人链路，创建、加入、恢复、玩家同步、
讨论、串行问答、提示、结案和结算均可真实联调。

服务端已实现 DeepSeek 题目生成、质量复核、主持问答、提示和结案判断，并提供结构化输出
校验、超时、退避重试与格式修复。未配置 `DEEPSEEK_API_KEY` 时自动使用确定性开发主持人，
因此本地开发不需要提交 Key。

SQLite 只保存管理员私人题库和近期抽题记录；作答过程、房间事件和结算不会写入服务端
数据库。客户端不会保存 API Key，完整作答记录仍只保存在本机。

## 运行客户端

```powershell
cd client
Copy-Item .env.example .env
pnpm install
pnpm tauri dev
```

修改 `.env` 中的 `VITE_SERVER_URL` 即可连接本机、WSL 或公网服务端。开发联调默认使用
`http://127.0.0.1:8787`。

## 运行服务端

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
cp .env.example .env
# 需要真实 AI 时，只在 server/.env 设置 DEEPSEEK_API_KEY
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
```

服务端检查：

```bash
cd server
ruff check .
mypy
pytest
```

完整 HTTP/WebSocket 冒烟测试：

```bash
cd server
python tools/smoke_transport.py --base-url http://127.0.0.1:8787
```

脚本会建立两个独立客户端，验证成员同步、讨论、问答、提示、结算广播和结算前汤底保密。
真实 DeepSeek 凭据配置完成后，可额外运行：

```bash
python tools/smoke_deepseek.py
```

## 构建安装包

```powershell
cd client
pnpm tauri build
```

客户端传输结构见 `docs/客户端对接指南.md`，桌面构建说明见 `client/README.md`，版本变化
见 `CHANGELOG.md`。
