# Trepang Soup 客户端

Trepang Soup（海龟汤）的 Windows 桌面客户端。当前版本以本地模拟服务运行，已经可以完整演示创建房间、加入、等候大厅、讨论、问题队列、公共提示、结案、赛后总结和本地记录。

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
- 多人后端：传输基线已实现，客户端尚未接入
- DeepSeek：尚未接入，客户端不保存 API Key
- 数据源：当前使用 `src/stores/game.ts` 中的模拟房间和模拟主持逻辑
- 管理员演示密码：`soup`，仅用于展示界面，不代表真实认证设计

## 开发运行

在 `client` 目录运行：

```powershell
pnpm install
pnpm dev
```

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
├─ router/           页面路由与路由后滚动恢复
├─ stores/           模拟房间、队列、提示和本地历史
├─ styles/           深夜寝室主题与响应式布局
├─ types/            游戏领域类型
└─ views/            首页、大厅、房间、结算、历史、题库
```

## 后端接入原则

真实后端接入时，不应把 DeepSeek Key 或汤底放入客户端。服务端通过 HTTP 完成创建/加入与管理操作，通过 WebSocket 广播房间状态和游戏事件。当前对接步骤见项目根目录 `docs/客户端对接指南.md`，完整接口契约见 `docs/通信协议-v1.md`。

## 已验证流程

1. 创建 AI 生成房间。
2. 进入模拟大厅并开始游戏。
3. 在讨论区发送消息。
4. 提交正式问题并观察串行队列。
5. 等待主持人结构化回答。
6. 请求公共提示。
7. 提交完整推理并成功结案。
8. 查看汤底、评分和三个趣味奖项。
9. 在本地历史中重新打开对局。

## 已知限制

- 当前重新加载页面会重建模拟房间，真实重连将在后端接入阶段完成。
- 本地历史当前使用浏览器 `localStorage` 模拟；桌面正式版接入后将迁移到 SQLite。
- 题库界面只维护前端内存中的演示数据。
- 安装包尚未进行商业代码签名，Windows 可能显示 SmartScreen 提示。
