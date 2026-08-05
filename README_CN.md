<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero

  *面向研究工作流的结构化 Markdown。*
</div>

Mdtero 把论文转换为可复用的 Markdown 研究包，用于阅读、翻译、项目研究和本地 agent。

**语言：** [English](./README.md) | 简体中文

## 安装

```bash
uv tool install --upgrade mdtero
mdtero setup
mdtero doctor --json
```

安装包已发布到 PyPI，默认安装不依赖 GitHub。中国大陆用户使用安装脚本时会自动先尝试清华/阿里 PyPI 镜像，再回退官方源；没有 `uv` 时直接使用安装脚本：

```bash
curl -Ls https://mdtero.com/install.sh | sh
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

安装脚本支持 `uv`、`pipx` 和 Python 回退。`--agent <target>` 会安装本地 agent skill。

## 使用 Mdtero

```bash
mdtero discover "thermal energy storage" --limit 5 --interactive
mdtero parse <doi-or-url> --wait --timeout 300 --json
mdtero parse --file paper.pdf --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero translate <task-id> --to zh-CN --wait --timeout 600 --json
```

`mdtero doctor --json` 会返回脱敏的 auth/dependency/academic/Zotero/project/RAG 摘要，不会回显凭据。

CLI 是默认路径。桌面安装会自动准备本地访问能力，用于校园网络和需要浏览器的资源。浏览器扩展只作为当前页面捕获或必须使用既有浏览器登录态时的轻量备用方案；它仍可把 DOI、URL、PDF、EPUB、HTML 或 XML 资源交回 CLI。

### 按环境选择产品

| 环境 | 推荐入口 | 能解决 | 边界 |
| --- | --- | --- | --- |
| 校园网中的 Win/Mac 完整桌面 | CLI + 自动准备的本地访问能力 | OA、校园 IP 路由、浏览器登录/挑战、用户已有权限的闭源文献 | 已有普通浏览器会话仍可用扩展兜底。 |
| 只有服务器上的 CLI/Agent | CLI/API | OA、结构化 API、普通 HTTP、VPN/IP 授权资源和上传 | 没有浏览器会话；仅 WAF/登录态的闭源文献需要文件或另一台桌面。 |
| 服务器 Agent + 另一台校园桌面 | 服务器 CLI/API + 校园电脑上的 Relay；扩展作为手动兜底 | 校园电脑完成授权浏览器采集，服务器负责云端解析 | 扩展本身需要用户点击；若要让服务器主动请求文章，应使用 Relay。 |
| 服务器连接校园 VPN、但没有浏览器 | CLI/API 直接走 VPN 或代理 | 按 IP 放行的机器可读 PDF/XML/HTML | VPN 只提供网络出口，不提供浏览器 Cookie 或挑战完成。 |

简言之：浏览器绑定的权限必须有浏览器；校园 IP/VPN 只有在出版社提供机器可读通道时才足够。Mdtero 不绕过付费墙，也不导出浏览器会话材料。

## 项目工作流

处理一组论文时，使用本地 Mdtero project：

```bash
mdtero project init --name literature-review
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
```

Zotero 支持采用保守方式：`mdtero zotero sync` 会为对应的成功项目添加 Mdtero 结果 note 和 tag，不会改写 Zotero 文献元数据。

## 浏览器与 Agent

浏览器扩展是轻量备用入口，适用于浏览器中已打开论文、内容依赖你自己的登录态，或需要上传文件的情况。扩展与 CLI 共用任务历史、下载和翻译。

安装本地 agent skill：

```bash
mdtero agent install --interactive
mdtero mcp briefing --json
```

briefing 会提供安全的任务状态、可下载成果、引文和建议的下一步。不要把 API key 或其他 secret 放入 prompt、日志或仓库。可信无头机器应仅在 `mdtero setup --api-key --json` 的安全提示中输入新 key。

## 访问边界

Mdtero 用于处理你有权访问的内容。出版社订阅、机构访问和来源专用凭据仍由用户自行负责。来源需要你的浏览器登录态或本地副本时，请使用扩展或上传已保存文件。

解析和来源选择实现属于服务内部，不是用户配置项。稳定流程是提交、查看状态、下载、翻译，再在项目中使用生成的 Markdown。

## 产品边界

Mdtero Account 是 Mdtero API key、额度、计费、历史和安装提示词的控制面。Academic source keys 保存在本地 `mdtero config academic` 配置中；OpenAlex 检索还有服务端托管回落，因此用户无需配置 OpenAlex key 才能检索。CLI 管理的本地访问能力和浏览器扩展与来源凭据保持分离。

所有输入入口共用同一组 `/api/v1` 服务端契约：`/api/v1/route`、`/api/v1/extension/route`、`/api/v1/tasks/parse`、`/api/v1/tasks/upload`、`/api/v1/tasks/{task_id}`、`/api/v1/tasks/{task_id}/download/{artifact}`、`/api/v1/discovery/search`、`/api/v1/tasks/translate`、`/api/v1/projects`、`/api/v1/projects/{project_id}/tasks/{task_id}/import`、`/api/v1/projects/{project_id}/rag/status`、`/api/v1/projects/{project_id}/rag/build` 和 `/api/v1/projects/{project_id}/rag/query`。CLI、扩展、dashboard 和 MCP briefing 都会暴露这组 contract。

## 文档

- [Mdtero 网站](https://mdtero.com)
- [文档](https://mdtero.com/docs/)
- [安装指南](https://mdtero.com/docs/install.html)

## 开发

```bash
uv run --with pytest --with rich --with textual --with httpx --with requests --with curl_cffi --with pyzotero --with fastmcp pytest tests_py -q
npm --prefix extension test
npm --prefix extension run build
```
