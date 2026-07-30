# Trepang Soup

多人在线、AI担任主持人的好友海龟汤桌面平台。

## 当前交付

- `docs/Trepang Soup 项目规划.docx`：产品与实施规划
- `docs/后端实施指南.md`：Ubuntu 24.04 / WSL 后端实施说明
- `docs/通信协议-v1.md`：HTTP 与 WebSocket 首版契约
- `client/`：Tauri 2 + Vue 3 + TypeScript Windows 客户端
- `release/`：本地构建的 Windows x64 安装包目录（不提交到 Git）

## 当前开发阶段

Windows 客户端已经实现完整模拟流程，后端尚未编写。客户端目前不会调用 DeepSeek，也不会在本地保存 API Key。

## 快速运行

```powershell
cd client
pnpm install
pnpm tauri dev
```

## 构建安装包

```powershell
cd client
pnpm tauri build
```

详细说明见 `client/README.md`。
