# Trepang Soup 服务端

Trepang Soup 的 FastAPI 后端。房间和玩家会话只存在于内存，SQLite 仅保存私人题库和
近期抽题记录：

- 创建、加入和令牌轮换式会话恢复。
- WebSocket 握手、完整快照、事件缓存与断线补发。
- 玩家在线状态、房主操作和离线房主转移。
- 讨论、幂等命令、严格串行问题队列与撤回规则。
- 公共提示、结案判断、放弃和赛后结算。
- 结案前汤底保密、协议错误封装和开发端跨域配置。
- DeepSeek V4 Flash 题目生成、独立质量复核、主持问答、提示和结案判断。
- DeepSeek 结构化输出校验、一次格式修复、超时、并发限制和退避重试。
- SQLite 私人题库、近期排除、管理员认证、CRUD、导入和导出。
- 主动关闭、结算宽限和全员离线超时后的房间销毁。

## 本地初始化

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
cp .env.example .env
```

本地开发可以不配置 DeepSeek Key，此时使用确定性主持人和演示题目。真实 AI 只在
`server/.env` 中设置：

```dotenv
DEEPSEEK_API_KEY=<server-only-key>
DEEPSEEK_MODEL=deepseek-v4-flash
```

Key 不得进入客户端、日志或 Git。DeepSeek 当前 JSON 模式需要提示词明确要求 JSON；
适配器同时使用 `response_format={"type":"json_object"}`，并再次使用 Pydantic 校验。
接口行为以 DeepSeek 官方的 [Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)、
[JSON Output](https://api-docs.deepseek.com/guides/json_mode/) 和
[错误码](https://api-docs.deepseek.com/quick_start/error_codes/) 文档为准。

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
提示。它会建立两个客户端，验证广播一致性，最后同步结算，并检查 `game.settled`
之前没有汤底泄露。

真实 DeepSeek 凭据配置后运行独立实网验收：

```bash
python tools/smoke_deepseek.py
```

该脚本真实执行题目生成、质量审查、主持回答、提示和完整结论判定，但不会输出汤底或
完整提示词。

## 私人题库与管理员认证

先生成专用管理员密码的 Argon2id verifier：

```bash
python tools/admin_credentials.py hash
```

将输出写入 `server/.env` 的 `ADMIN_PASSWORD_HASH`。登录过程：

1. `GET /api/v1/admin/challenge` 获取一次性挑战和 Argon2id 参数。
2. 客户端以专用密码派生 verifier，并对 `challengeId + "\n" + nonce + "\n" + issuedAt`
   计算 HMAC-SHA256。
3. `POST /api/v1/admin/login` 提交挑战 ID、时间戳和十六进制 HMAC。
4. 使用返回的 15 分钟 Bearer 令牌调用题库接口。

命令行可以根据保存的挑战响应生成登录请求体：

```bash
python tools/admin_credentials.py respond --challenge-file challenge.json
```

题库接口：

- `GET /api/v1/admin/puzzles`
- `POST /api/v1/admin/puzzles`
- `PUT /api/v1/admin/puzzles/{puzzleId}`
- `DELETE /api/v1/admin/puzzles/{puzzleId}`
- `POST /api/v1/admin/puzzles/import`
- `GET /api/v1/admin/puzzles/export`

挑战响应避免直接传输可复用密码，但并不能替代 HTTPS；未启用 TLS 时仍可能遭受中间人
攻击或 verifier 重放。正式公网部署必须启用 TLS。

## 持久化与清理边界

- `puzzles` 保存题面、汤底、关键事实和启用状态。
- `puzzle_selections` 只保存题目 ID 和抽取时间，用于排除最近若干题目。
- 房间、昵称、讨论、问答、汤底揭晓和结算不写入 SQLite。
- 房主关闭、结算事件发送宽限结束、或全员离线超过 `ROOM_IDLE_SECONDS` 后，房间、邀请
  码、会话、事件缓存和后台任务一并清除。

## 部署侧后续工作

- 通过部署环境的密钥管理注入 `DEEPSEEK_API_KEY`，不得复用或提交开发验收凭据。
- 配置 HTTPS 反向代理、systemd、日志采集和密钥管理。
- Windows 客户端管理员题库页面尚未接入服务端接口。
- 客户端运行中断线后的自动退避重连仍待实现。

`requirements.lock` 固定完整解析后的依赖树；修改依赖时，应在干净虚拟环境中重新
生成并运行全部检查。
