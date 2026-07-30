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

Windows 客户端已经实现完整模拟流程。服务端已经提供创建、加入、恢复、WebSocket 快照与
事件补发，以及讨论、串行问答、提示和结案流程，可以开始替换客户端模拟传输层。

当前服务端使用可替换的确定性开发主持人；DeepSeek、管理员题库和 SQLite 持久化仍待实现。
客户端目前尚未连接服务端，也不会在本地保存 API Key。

## 运行客户端

```powershell
cd client
pnpm install
pnpm tauri dev
```

## 运行服务端

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
cp .env.example .env
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

## 构建安装包

```powershell
cd client
pnpm tauri build
```

客户端接入步骤见 `docs/客户端对接指南.md`，桌面构建说明见 `client/README.md`。
