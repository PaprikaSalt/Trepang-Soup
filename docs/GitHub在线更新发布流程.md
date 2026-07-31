# GitHub 在线更新发布流程

Trepang Soup 1.2.0 起使用 GitHub Releases 承担更新文件分发，无需占用游戏服务器流量。客户端
启动时读取最新版 Release 的 `latest.json`，发现更高版本后由玩家确认下载、安装并重启。

## 一次性密钥

更新包必须签名。当前公钥已经写入 `client/src-tauri/tauri.conf.json`，私钥不能提交到仓库。
请把本机生成的私钥和密码备份到安全位置；私钥丢失后，已安装客户端无法验证用新密钥签出的
后续版本。

## 构建签名安装包

在 PowerShell 中设置私钥路径，再构建：

```powershell
cd client
$env:TAURI_SIGNING_PRIVATE_KEY = "C:\安全位置\trepang-soup-updater.key"
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = "私钥密码；无密码时留空"
pnpm tauri build
```

构建完成后，`client/src-tauri/target/release/bundle/nsis/` 中应同时出现安装器和同名 `.sig`
签名文件。

## 生成 latest.json

从项目根目录执行：

```powershell
.\tools\create_updater_manifest.ps1 `
  -Version "1.2.0" `
  -InstallerPath ".\client\src-tauri\target\release\bundle\nsis\Trepang Soup_1.2.0_x64-setup.exe" `
  -Notes "本次更新说明" `
  -OutputPath ".\release\latest.json"
```

脚本会读取安装器的 `.sig`，并生成指向 `v1.2.0` Release 资产的 Windows x64 更新清单。

## 发布

1. 提交版本号、功能改动和 `CHANGELOG.md`，推送 GitHub。
2. 创建与客户端版本一致的非预发布 Release，例如 `v1.2.0`。
3. 上传安装器、同名 `.sig` 和 `latest.json`。
4. 确认 `https://github.com/PaprikaSalt/Trepang-Soup/releases/latest/download/latest.json`
   可以访问，再用旧版客户端检查更新。

1.1.0 及更旧版本不包含更新模块，因此必须手动安装一次 1.2.0；从 1.2.0 升级到后续版本时
才会显示应用内更新提示。
