# Trepang Soup 客户端

Trepang Soup（海龟汤）的 Windows 桌面客户端。当前版本已经接入真实 HTTP/WebSocket
多人服务，可完成创建房间、加入、等候大厅、讨论、问题队列、公共提示、结案、赛后总结
和本地记录。

## 技术栈

- Tauri 2
- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- Rust stable / MSVC

## 当前状态

- 客户端：可运行、可构建、可打包
- 多人后端：主游戏传输链路已接入
- DeepSeek：由服务端接入，客户端不保存 API Key
- 数据源：默认连接真实后端，可通过环境变量切换本地模拟模式
- 管理员演示密码：`soup`，仅用于展示界面，不代表真实认证设计

## 开发运行

在 `client` 目录运行：

```powershell
Copy-Item .env.example .env
pnpm install
pnpm dev
```

`.env` 示例：

```dotenv
VITE_TRANSPORT_MODE=server
VITE_SERVER_URL=http://127.0.0.1:8787
```

连接公网服务端时，将 `VITE_SERVER_URL` 改为服务器地址后重新构建客户端。需要离线查看
界面时，可设置 `VITE_TRANSPORT_MODE=mock`。

浏览器预览地址：

```text
http://127.0.0.1:1420/
```

运行桌面窗口：

```powershell
pnpm tauri dev
```

## 构建

只构建 Vue 前端：

```powershell
pnpm build
```

构建 Windows NSIS 安装包：

```powershell
pnpm tauri build
```

安装包位于：

```text
src-tauri/target/release/bundle/nsis/
```

## 主要目录

```text
src/
├─ components/       通用组件与创建/加入弹窗
├─ persistence/      本机会话令牌与客户端实例标识
├─ protocol/         HTTP/WebSocket 协议类型
├─ router/           页面路由与路由后滚动恢复
├─ stores/           房间事件归并、模拟后备和本地历史
├─ styles/           深夜寝室主题与响应式布局
├─ transport/        真实后端传输实现
├─ types/            游戏领域类型
└─ views/            首页、大厅、房间、结算、历史、题库
```

## 后端接入原则

DeepSeek Key 和结算前的汤底都不能进入客户端。服务端通过 HTTP 完成创建、加入和会话
恢复，通过 WebSocket 广播房间状态和游戏事件。实现说明见项目根目录
`docs/客户端对接指南.md`，完整接口契约见 `docs/通信协议-v1.md`。

## 已验证流程

1. 创建 AI 生成房间。
2. 第二个客户端通过邀请码加入，双方实时看到成员变化。
3. 房主开始游戏，两个客户端同步进入游戏页。
4. 在聊天室发送消息并验证跨客户端同步。
5. 提交正式问题并观察串行队列。
6. 等待主持人结构化回答。
7. 请求公共提示。
8. 提交完整推理并同步结案。
9. 查看汤底、评分和趣味奖项。
10. 在本地历史中重新打开对局。

## 已知限制

- 应用重新打开时会恢复最近一次有效会话；连接中途断开后的自动退避重连仍待实现。
- 本地历史使用 WebView 的 `localStorage`，符合仅在本机保留作答记录的首版约束。
- 题库界面只维护前端内存中的演示数据。
- 管理员题库页面仍是客户端演示实现；服务端管理接口已经可用，尚待客户端接入。
- 安装包尚未进行商业代码签名，Windows 可能显示 SmartScreen 提示。
