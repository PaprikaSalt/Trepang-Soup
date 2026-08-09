import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const clientDir = path.resolve(toolsDir, "..");
const repositoryDir = path.resolve(clientDir, "..");
const distDir = path.join(clientDir, "dist");
const integrationPath = path.join(distDir, "integration.json");
const forbiddenFilePattern = /(^|\/)(\.env(?:\.|$)|.*\.(?:db|sqlite|log|key|pem))$/i;

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function readPublicEnvironment() {
  const contents = await readFile(path.join(clientDir, ".env.web.production"), "utf8");
  return Object.fromEntries(
    contents
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"))
      .map((line) => {
        const separator = line.indexOf("=");
        return [line.slice(0, separator), line.slice(separator + 1)];
      }),
  );
}

async function listFiles(directory, relative = "") {
  const entries = await readdir(path.join(directory, relative), { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const nextRelative = path.posix.join(relative.replaceAll("\\", "/"), entry.name);
    if (entry.isDirectory()) files.push(...(await listFiles(directory, nextRelative)));
    else if (entry.isFile()) files.push(nextRelative);
  }
  return files.sort();
}

async function sha256(filePath) {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

function readSourceCommit() {
  const githubSha = process.env.GITHUB_SHA?.trim();
  const commit = githubSha || execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: repositoryDir,
    encoding: "utf8",
  }).trim();
  if (!/^[0-9a-f]{40}$/i.test(commit)) throw new Error("sourceCommit 必须是完整的 40 位 Git SHA");
  return commit.toLowerCase();
}

async function loadBuildContract() {
  const packageJson = await readJson(path.join(clientDir, "package.json"));
  const compatibility = await readJson(path.join(repositoryDir, "release-compatibility.json"));
  const tauriConfig = await readJson(path.join(clientDir, "src-tauri", "tauri.conf.json"));
  const serverProject = await readFile(path.join(repositoryDir, "server", "pyproject.toml"), "utf8");
  const serverInit = await readFile(path.join(repositoryDir, "server", "app", "__init__.py"), "utf8");
  const serverProtocol = await readFile(
    path.join(repositoryDir, "server", "app", "protocol", "constants.py"),
    "utf8",
  );
  const clientProtocol = await readFile(path.join(clientDir, "src", "protocol", "types.ts"), "utf8");
  const cargoManifest = await readFile(path.join(clientDir, "src-tauri", "Cargo.toml"), "utf8");
  const serverVersion = serverProject.match(/^version = "([^"]+)"/m)?.[1];
  const declaredVersions = {
    compatibility: compatibility.clientVersion,
    server: serverVersion,
    serverRuntime: serverInit.match(/APP_VERSION = "([^"]+)"/)?.[1],
    tauri: tauriConfig.version,
    cargo: cargoManifest.match(/^version = "([^"]+)"/m)?.[1],
    clientRuntime: clientProtocol.match(/CLIENT_VERSION = "([^"]+)"/)?.[1],
  };
  for (const [source, version] of Object.entries(declaredVersions)) {
    if (version !== packageJson.version) {
      throw new Error(`${source} 版本 ${version ?? "缺失"} 与客户端版本 ${packageJson.version} 不一致`);
    }
  }

  const declaredProtocols = {
    server: Number(serverProtocol.match(/PROTOCOL_VERSION[^=]*= (\d+)/)?.[1]),
    client: Number(clientProtocol.match(/PROTOCOL_VERSION = (\d+)/)?.[1]),
  };
  for (const [source, protocol] of Object.entries(declaredProtocols)) {
    if (protocol !== compatibility.protocolVersion) {
      throw new Error(`${source} 协议版本与兼容契约不一致`);
    }
  }

  const releaseTag = process.env.RELEASE_TAG || process.env.GITHUB_REF_NAME || "";
  if (/^v\d+\.\d+\.\d+$/.test(releaseTag) && releaseTag !== `v${packageJson.version}`) {
    throw new Error(`发布标签 ${releaseTag} 与客户端版本 ${packageJson.version} 不一致`);
  }
  return { packageJson, compatibility };
}

async function validateRuntimeFiles(files, publicBase) {
  if (!files.includes("index.html") || !files.includes("app-icon.svg")) {
    throw new Error("Web 产物缺少 index.html 或 app-icon.svg");
  }
  const forbidden = files.find((file) => forbiddenFilePattern.test(file));
  if (forbidden) throw new Error(`Web 产物包含禁止发布的文件：${forbidden}`);

  const indexHtml = await readFile(path.join(distDir, "index.html"), "utf8");
  if (!indexHtml.includes(`${publicBase}assets/`) || /(?:src|href)=["']\/assets\//.test(indexHtml)) {
    throw new Error(`index.html 未正确使用公共路径 ${publicBase}`);
  }
  if (!indexHtml.includes(`${publicBase}app-icon.svg`)) {
    throw new Error("favicon 未使用 Web 公共路径");
  }

  const libraryChunk = files.find((file) => /LibraryView/i.test(file));
  if (libraryChunk) throw new Error(`公开 Web 包不应包含题库管理页面：${libraryChunk}`);

  const scripts = files.filter((file) => file.endsWith(".js"));
  for (const script of scripts) {
    const source = await readFile(path.join(distDir, script), "utf8");
    if (source.includes("LibraryView") || source.includes("题库管理") || source.includes('"/library"')) {
      throw new Error(`公开 Web 脚本仍包含管理员入口：${script}`);
    }
  }
}

async function prepare() {
  await stat(distDir);
  const { packageJson, compatibility } = await loadBuildContract();
  const publicEnvironment = await readPublicEnvironment();
  if (
    publicEnvironment.VITE_TRANSPORT_MODE !== "server" ||
    publicEnvironment.VITE_ENABLE_ADMIN !== "false" ||
    publicEnvironment.VITE_PUBLIC_BASE !== compatibility.web.publicBase ||
    !publicEnvironment.VITE_SERVER_URL?.startsWith("https://")
  ) {
    throw new Error(".env.web.production 不符合公开 Web 构建契约");
  }
  const runtimeFiles = (await listFiles(distDir)).filter((file) => file !== "integration.json");
  await validateRuntimeFiles(runtimeFiles, compatibility.web.publicBase);

  const files = {};
  for (const file of runtimeFiles) files[file] = await sha256(path.join(distDir, file));

  const integration = {
    name: "trepang-soup-web",
    version: packageJson.version,
    sourceCommit: readSourceCommit(),
    apiBase: publicEnvironment.VITE_SERVER_URL,
    protocolVersion: compatibility.protocolVersion,
    publicBase: compatibility.web.publicBase,
    buildMode: compatibility.web.buildMode,
    adminEnabled: compatibility.web.adminEnabled,
    files,
  };
  await writeFile(integrationPath, `${JSON.stringify(integration, null, 2)}\n`, "utf8");
  console.log(`prepared ${path.relative(repositoryDir, integrationPath)} (${runtimeFiles.length} runtime files)`);
}

async function verify() {
  const { packageJson, compatibility } = await loadBuildContract();
  const integration = await readJson(integrationPath);
  const actualFiles = (await listFiles(distDir)).filter((file) => file !== "integration.json");

  if (integration.version !== packageJson.version) throw new Error("清单版本与客户端版本不一致");
  if (integration.protocolVersion !== compatibility.protocolVersion) throw new Error("清单协议版本不一致");
  if (integration.publicBase !== compatibility.web.publicBase) throw new Error("清单公共路径不一致");
  if (integration.adminEnabled !== false) throw new Error("公开 Web 清单必须禁用管理员入口");
  await validateRuntimeFiles(actualFiles, integration.publicBase);

  const declaredFiles = Object.keys(integration.files).sort();
  if (JSON.stringify(declaredFiles) !== JSON.stringify(actualFiles)) {
    throw new Error("清单 files 未完整覆盖 Web 运行时文件");
  }
  for (const file of actualFiles) {
    const actualHash = await sha256(path.join(distDir, file));
    if (integration.files[file] !== actualHash) throw new Error(`文件校验失败：${file}`);
  }
  console.log(`verified Trepang Soup Web v${integration.version} (${actualFiles.length} runtime files)`);
}

const command = process.argv[2];
if (command === "prepare") await prepare();
else if (command === "verify") await verify();
else throw new Error("用法：node tools/web-release.mjs <prepare|verify>");
