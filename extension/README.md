# Mdtero Extension

Mdtero Extension lets you sign in, parse the paper in your current tab or a DOI, upload a PDF or EPUB, monitor a task, translate Markdown, and download the result.

## Use

1. Open the popup and sign in with your Mdtero account.
2. Parse the active paper page, paste a DOI, or choose a local PDF/EPUB.
3. Wait for the task to finish, then download Markdown, a bundle, or a translation.

The extension only uses an active scholarly tab when you explicitly start a parse. Files are uploaded only after you select them. Mdtero selects the appropriate processing path on the service side; the extension does not expose or require a processing provider or parser setting.

Authentication is completed on Mdtero's website. Paper pages cannot issue account tokens to the extension.

You may add an access key issued to you by an authorized source. It remains in this browser and is used only when you enable that access. Mdtero never supplies shared source credentials through the extension.

When a paper cannot be completed in the browser, the popup can hand the request to the Mdtero CLI. Use the CLI for local files, projects, batch work, citations, and agent workflows.

## Build

```bash
npm install
npm run build:dev
```

For a store package:

```bash
npm test
npm run build:store
npm run package:webstore
```

## CLI

```bash
uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git
mdtero setup
```

## 中文

Mdtero 浏览器扩展支持登录、解析当前论文页或 DOI、上传 PDF/EPUB、查看任务进度、翻译和下载结果。

1. 在弹窗中登录 Mdtero 账户。
2. 解析当前论文页、粘贴 DOI，或选择本地 PDF/EPUB。
3. 任务完成后下载 Markdown、压缩包或译文。

扩展只会在你主动开始解析时读取当前论文页；本地文件也只会在你选择后上传。处理路径由服务端决定，扩展不会显示或要求选择底层服务商、连接器或解析器。

你可以配置自己从授权来源获得的访问密钥。密钥仅保存在当前浏览器，并且只在你启用该访问方式时使用；扩展不会提供共享的来源凭据。

浏览器中无法完成的任务可以交给 Mdtero CLI，适用于本地文件、项目、批处理、引用和 agent 工作流。
