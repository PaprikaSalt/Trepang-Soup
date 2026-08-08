<p align="center">
  <img src="assets/trepang-mouse.png" width="360" alt="Trepang Soup 海参鼠">
</p>

<h1 align="center">Trepang Soup</h1>

<p align="center"><strong>海龟汤 · 多人在线 AI 主持人桌面游戏</strong></p>

<p align="center">
  无需注册，叫上朋友、输入邀请码，就能开始一场由 DeepSeek 主持的海龟汤。
</p>

Trepang Soup 面向少量好友，提供 Windows 原生桌面客户端、实时多人房间、AI 或私人
题库，以及从提问到结算、续局的完整流程。本文件是仓库唯一维护文档；历史版本变化以
Git 历史及 [GitHub Releases](https://github.com/PaprikaSalt/Trepang-Soup/releases) 为准。

## 当前基线

- 客户端：`1.4.0`，Windows 10/11 x64，Tauri 2 + Vue 3 + TypeScript。
- 服务端：`1.4.0`，Ubuntu 24.04 x86-64，FastAPI + WebSocket + SQLite。
- 通信协议：`1`。
- 公网入口由部署环境配置；HTTPS 与 WSS 使用同一 API 域名。
- 规模边界：好友房间，最多 20 人；服务端必须保持单 worker。

## 产品与规则

- 无需注册。玩家填写昵称，创建房间并分享邀请码；其他玩家凭昵称和邀请码加入。
- 游戏开始后仍可加入，新玩家会收到当前房间快照和完整正式问答。
- 题目来自 DeepSeek 实时生成，或管理员维护的私人题库；私人题库会随机抽取并排除近期
  重复题目。
- AI 题目可分别选择难度和风格，私人题库不选择档位。
- 聊天室全房间可见；正式问题按提交时间串行处理，进入 AI 处理前可撤回。
- “我没招了”会请求公共提示，每次使用都会降低本局评分。
- 主持回答固定为“是／否／不相关／部分正确／不能透露”，DeepSeek 只能选择类型，不能
  自由生成解释。“是否重要／是否有关联”等单点方向问题可回答；开放式索取情节、过量问题、
  指代不清或无法可靠判断时回答“不能透露”。
- 猜中核心冲突即可结案。每遗漏一项细节扣 6 分，最多扣 30 分；遗漏两项及以上时先二次
  确认。确认提交不会再次调用 AI。
- 结算包含评分、总结、MVP 玩家、最佳带偏奖和最有价值问题。
- 全体在线成员同意后，可以不退出房间直接开始下一局。
- 房主可以关闭房间并强制结束当前游戏。

## 数据与安全边界

- 房间、成员、聊天室、问答、提示、结算和会话只保存在服务端内存中，不落库。
- SQLite 只保存私人题库和近期抽题记录。
- 客户端只在本机 WebView `localStorage` 保存作答记录，不提供导出。
- DeepSeek Key、管理员密码校验值、会话签名密钥、汤底和关键事实不得进入客户端、日志
  或 Git。
- `server/.API_KEY_DEV`、所有 `.env`、构建目录、安装包和本地数据库均已被 Git 忽略。
- 正式问答不会携带此前问答历史，避免多人连续追问后由模型自动拼接汤底。
- 公共提示、结案拒绝和细节确认均经过服务端校验或使用固定文案。

## 仓库结构

```text
client/                    Windows 桌面客户端
  src/                     Vue 页面、状态、协议与传输
  src-tauri/               Tauri/Rust 配置及 Windows 打包
  tools/                   客户端回归冒烟脚本
server/                    FastAPI 服务端
  app/api/                 HTTP 与 WebSocket 入口
  app/ai/                  DeepSeek 适配、提示词及安全映射
  app/rooms/               房间状态机
  app/library/             SQLite 私人题库
  tests/                   单元与集成测试
  tools/                   凭据、传输和真实 DeepSeek 冒烟脚本
tools/create_updater_manifest.ps1
                           生成 GitHub 在线更新清单
```

## 本地开发

### 服务端

Ubuntu/WSL：

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
```

Windows PowerShell：

```powershell
cd server
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
Copy-Item .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
```

未配置 `DEEPSEEK_API_KEY` 时使用确定性演示主持人。真实 AI 只在 `server/.env` 中配置：

```dotenv
DEEPSEEK_API_KEY=<server-only-key>
DEEPSEEK_MODEL=deepseek-v4-flash
```

生产环境还必须配置：

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://api.example.com
DATABASE_URL=sqlite+aiosqlite:///./data/trepang.db
ADMIN_PASSWORD_HASH=<argon2id-verifier>
SESSION_SIGNING_KEY=<至少32字节的随机密钥>
```

管理员密码校验值通过 `python tools/admin_credentials.py hash` 生成。

### 客户端

```powershell
cd client
Copy-Item .env.example .env
pnpm install
pnpm tauri dev
```

客户端环境变量：

```dotenv
VITE_TRANSPORT_MODE=server
VITE_SERVER_URL=http://127.0.0.1:8787
```

正式构建的服务地址由构建环境配置。仅查看界面时可将 `VITE_TRANSPORT_MODE` 改为
`mock`。

## 接口与协议速查

除 `/health` 外，HTTP 请求需携带 `X-Protocol-Version: 1`。

主要入口：

- `GET /health`
- `POST /api/v1/rooms`
- `POST /api/v1/rooms/join`
- `POST /api/v1/sessions/resume`
- `WS /api/v1/rooms/{roomId}/ws`
- `/api/v1/admin/*`：管理员挑战登录、题库 CRUD、导入与导出

WebSocket 命令统一包含 `protocolVersion`、`commandId`、`type`、`roomId`、
`sessionToken`、`clientTime` 和 `payload`。关键命令包括开始/关闭房间、讨论、问题提交与
撤回、提示、结案、放弃和续局投票。服务端事件使用递增 `eventId`；客户端发现事件缺口时
重新获取完整快照。

新增协议字段或枚举时应保持向后兼容；不兼容变更必须提升 `PROTOCOL_VERSION`。客户端与
后端是否需要同步部署，应在对应 GitHub Release 中明确说明。

## 私人题库批量导入

客户端“题库管理”支持合并导入和替换整个题库。固定 JSON 格式：

```json
{
  "schemaVersion": 1,
  "puzzles": [
    {
      "id": "puzzle_example_dormitory_light",
      "title": "门缝里的灯光",
      "surface": "凌晨，她回到宿舍后看见门缝里有规律地闪着灯光，却故意说自己弄丢了钥匙，然后躲到楼梯间报警。为什么？",
      "truth": "室友遇到危险时无法直接呼救，只能按照两人提前约定的节奏闪灯。她认出求救信号后，故意让屋内的人相信自己无法进门，再离开视线范围报警求助。",
      "keyFacts": [
        "门缝里的灯光是室友发出的求救信号",
        "她声称钥匙丢失是在欺骗屋内的威胁者",
        "她躲到楼梯间是为了安全报警"
      ],
      "active": true
    }
  ]
}
```

约束：

- `schemaVersion` 固定为 `1`，`puzzles` 包含 1 至 1000 道题。
- `id` 以 `puzzle_` 开头，只能使用字母、数字、下划线和连字符，文件内不可重复。
- `title` 1–80 字符；`surface` 20–800 字符；`truth` 40–2000 字符。
- `keyFacts` 为 2–8 条非空且不重复的字符串。
- `active` 为布尔值；可选 `createdAt`、`updatedAt` 为非负毫秒时间戳。
- 任一题目校验失败时整批拒绝，不产生部分写入。

## 验证

服务端：

```bash
cd server
ruff format --check app tests tools
ruff check app tests tools
mypy app
pytest -q
python tools/smoke_transport.py --base-url http://127.0.0.1:8787
python tools/smoke_deepseek.py
```

最后一项会调用真实 DeepSeek，必须先配置密钥。客户端：

```powershell
cd client
pnpm smoke:updater
pnpm build
cargo fmt --manifest-path src-tauri\Cargo.toml --check
```

## 公网部署

- Ubuntu 24.04 上由 Uvicorn 监听 `127.0.0.1:8787`，Caddy 提供公网 HTTPS/WSS。
- 活跃房间位于进程内，必须使用单 worker；不要使用多 worker 或负载均衡到多个独立进程。
- 更新代码后重启 Uvicorn/systemd，并检查：

```bash
curl --fail http://127.0.0.1:8787/health
curl --fail https://api.example.com/health
```

- 返回的 `version` 应与当前服务端版本一致，`protocolVersion` 当前为 `1`。
- 部署前备份 `server/data/trepang.db` 和生产 `.env`；密钥不得进入备份公开目录。
- 反向代理必须支持 WebSocket Upgrade，并保留长连接。

## Windows 发布与在线更新

所有客户端变更都必须形成新的语义化版本、GitHub Release 和发布说明。历史更新日志只保留
在 GitHub Releases；本 README 只记录当前基线。

构建签名安装包：

```powershell
cd client
$env:TAURI_SIGNING_PRIVATE_KEY = "C:\安全位置\trepang-soup-updater.key"
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = "<私钥密码>"
pnpm tauri build
```

输出位于 `client/src-tauri/target/release/bundle/nsis/`。复制安装包及 `.sig` 后生成
`latest.json`：

```powershell
.\tools\create_updater_manifest.ps1 `
  -Version "1.4.0" `
  -InstallerPath "release\Trepang Soup 1.4.0 x64 Setup.exe" `
  -Notes "本次更新摘要" `
  -OutputPath "release\latest.json"
```

上面每行末尾的反引号是 PowerShell 续行符。Release 必须上传安装包、同名 `.sig` 和
`latest.json`。发布后从 GitHub 重新下载三项资产并比对 SHA-256，同时确认
`https://github.com/PaprikaSalt/Trepang-Soup/releases/latest/download/latest.json` 返回当前版本。
签名私钥和密码只保存在仓库外，不得提交。

## 当前已知约束

- 面向好友使用，未设计横向扩展；进程重启会清除活跃房间。
- 本地记录依赖 WebView `localStorage`。
- 管理员令牌仅保存在客户端内存中，重启程序后需要重新登录。
- 安装包具备 Tauri 更新签名，但没有商业代码签名，Windows 可能显示 SmartScreen 提示。
