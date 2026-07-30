# Trepang Soup 服务端

Trepang Soup 的 FastAPI 后端。目前已形成可供客户端开始联调的内存服务：

- 创建、加入和令牌轮换式会话恢复。
- WebSocket 握手、完整快照、事件缓存与断线补发。
- 玩家在线状态、房主操作和离线房主转移。
- 讨论、幂等命令、严格串行问题队列与撤回规则。
- 公共提示、结案判断、放弃和赛后结算。
- 结案前汤底保密、协议错误封装和开发端跨域配置。

当前主持实现是确定性的开发替身，接口位于 `app/ai/host.py`，后续 DeepSeek
适配器不需要修改房间和传输层。

## 本地初始化

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
cp .env.example .env
```

## 运行

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
```

健康检查：

```bash
curl http://127.0.0.1:8787/health
```

除 `/health` 外，所有 `/api/v1` HTTP 请求必须带上：

```text
X-Protocol-Version: 1
```

## 检查

```bash
ruff check .
mypy
pytest
```

## 传输冒烟测试

先启动服务，再在另一个终端运行：

```bash
python tools/smoke_transport.py --base-url http://127.0.0.1:8787
```

脚本会实际执行健康检查、创建房间、WebSocket 握手、开局、讨论、正式问答和
正确结案，并检查 `game.settled` 之前没有汤底泄露。

## 当前未实现

- DeepSeek 网络客户端、结构化输出修复与重试。
- SQLite 私人题库、近期抽题和管理员认证。
- 完成对局的客户端 SQLite 保存。
- 空闲房间销毁和公网 TLS 部署。

这些缺口不阻塞客户端建立 `ServerTransport`、状态归并和重连机制，但当前服务
不能视为生产后端。

`requirements.lock` 固定完整解析后的依赖树；修改依赖时，应在干净虚拟环境中重新
生成并运行全部检查。
