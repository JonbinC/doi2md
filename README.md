<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Browser Extension

  *Parse supported paper pages into research-ready Markdown bundles with optional translation.*
</div>

Mdtero is a browser-first academic workflow built around clean Markdown outputs.

This public repository contains:

- the browser extension source in [`extension`](./extension)
- the sideloadable ZIP used for direct download installs
- public integration guides for agent and API workflows

## Repo Map

- [`extension`](./extension): extension source, tests, build output, and manifest
- [`shared`](./shared): local public TypeScript contract used by the extension client
- [`openclaw`](./openclaw): OpenClaw-facing install guide
- [`codex`](./codex): Codex-facing install guide
- [`mcp`](./mcp): public MCP bridge material for agent integrations
- `mdtero-extension-beta.zip`: current sideload ZIP for direct installs

The Edge Add-ons listing is already live. Each store update still needs a fresh reviewed submission, so this repository keeps the release package and the unpacked source aligned.

## English

### What it does

- detects supported ScienceDirect and arXiv pages
- submits parse and translation jobs directly to `https://api.mdtero.com`
- stores its own API URL, sign-in token, email, and optional Elsevier key in browser storage
- lets you download ZIP bundles, `paper.md`, translated Markdown, and image assets from task history

### Install

1. Download `mdtero-extension-beta.zip` from [mdtero.com/guide](https://mdtero.com/guide), or build the package from this repository.
2. Unzip it into a stable local folder.
3. Open `edge://extensions` or `chrome://extensions`.
4. Turn on `Developer mode`.
5. Click `Load unpacked` and choose the unzipped folder.
6. Open Mdtero settings, sign in with your email verification code, and keep the default API URL unless you are testing locally.
7. Add your Elsevier API key only when you need publisher retrieval on supported Elsevier pages.

### Local development

```bash
npm install
npm test
npm run build
```

Build output lives in [`extension/dist`](./extension/dist).

### Architecture and privacy

- the extension and the website are decoupled clients; both default to `https://api.mdtero.com`
- the extension does not need the website UI to stay open in order to parse papers
- this repository contains public browser-side code; the production backend remains private
- the content script only reads supported pages when you actively use the Mdtero workflow
- publisher-side acquisition that needs local handling should stay on the user machine through the extension or helper flow

### Release notes for maintainers

- keep the unpacked `extension/dist` build and `mdtero-extension-beta.zip` in sync before release
- keep store packages separate from the direct sideload ZIP so Edge and Chrome review cycles do not block installs
- avoid documenting internal backend-only behavior here; keep this repository public-safe

### Developer links

- [OpenClaw guide](./openclaw/INSTALL.md)
- [Codex guide](./codex/INSTALL.md)
- [Public API docs](https://mdtero.com/api)

## 中文

### 这个插件现在做什么

- 识别 ScienceDirect、arXiv 等已支持页面
- 直接把解析和翻译任务提交到 `https://api.mdtero.com`
- 在浏览器本地保存自己的 API 地址、登录 token、邮箱和可选 Elsevier key
- 从历史任务里下载 ZIP、`paper.md`、译文 Markdown 和图片资源

### 安装方式

1. 从 [mdtero.com/guide](https://mdtero.com/guide) 下载 `mdtero-extension-beta.zip`，或直接在本仓库构建。
2. 解压到一个长期保留的本地目录。
3. 打开 `edge://extensions` 或 `chrome://extensions`。
4. 开启“开发者模式”。
5. 点击“加载已解压的扩展程序”，选择刚才解压出来的目录。
6. 打开 Mdtero 设置页，用邮箱验证码登录；如果不是本地联调，保留默认 API 地址即可。
7. 只有在需要 Elsevier 正文抓取时，再额外填写自己的 Elsevier API Key。

### 架构与隐私

- 网站和插件现在是解耦的两个客户端，默认都直接访问 `https://api.mdtero.com`
- 不需要同时打开网站，插件也能独立完成解析流程
- 本仓库公开的是浏览器端代码，生产后端仍然保持私有
- 插件只会在你主动使用时读取受支持页面的必要信息
- 需要本地处理的出版社获取链路，仍然应保留在用户自己的浏览器或本地 helper 一侧
