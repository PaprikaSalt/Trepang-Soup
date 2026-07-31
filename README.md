# Trepang Soup

多人在线、AI担任主持人的好友海龟汤桌面平台。

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

脚本会建立两个独立客户端，验证成员同步、讨论、问答、提示、结算前汤底保密、全员续局投票
和原房间进入第二轮。
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
见 `CHANGELOG.md`。公网迁移前按 `docs/公网部署清单.md` 完成环境、TLS、密钥、备份和
端到端验收。
