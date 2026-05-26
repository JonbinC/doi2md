# Public Docs

This directory keeps stable public-facing notes for the Mdtero launch surfaces.

The current public product shape is:

- Python/uv CLI and TUI from `JonbinC/doi2md`.
- Repeatable deploy smoke through `mdtero smoke --json`; it should stay non-interactive, secret-safe, and broad enough to cover discovery, DOI parse, artifact download, and server-side Voyage RAG build/status/query.
- Browser extension for login, DOI/current-page parse, PDF/EPUB upload, polling, translation, and download.
- Extension-to-CLI handoff is a public contract: when browser capture is blocked by a publisher challenge, campus-network/session-bound access, or a user-saved file workflow, continue with `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json` or `mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json` so `client_acquisition`, raw upload, `reason_code`, `action_hint`, and `next_commands` remain visible to local agents.
- Agent skill installation through `mdtero agent install`; the npm runtime path is retired.
- Backend-owned auth, quota, task state, MinerU PDF parsing, OpenAlex fallback discovery, LLM translation, and Voyage RAG with structured `source_nodes` / `evidence_pack` output for agents.
- Agent-facing CLI JSON and MCP payloads must keep `reason_code`, `action_hint`, `next_commands`, and evidence fields visible while sanitizing signed MinerU/OSS URLs, bearer/API-key headers, Mdtero API keys, and common token query parameters.
- MCP briefing payloads must expose `mcp_tool_plan`: a structured agent playbook with `step`, `tool`, `when`, `arguments`, `success_signal`, and `failure_fields` so local agents choose `submit_parse`, `task_status`, `download_artifact`, `request_translation`, `server_rag_status`, or `rag_query` without guessing from prose.
- Zotero reverse sync is limited to Mdtero result notes/tags for succeeded Zotero-origin tasks; it must not be described as bibliographic metadata rewriting.

Do not present GROBID as a public user-selectable parser. Do not describe RAG as requiring manual project ids; the public CLI flow is `rag build`, then `rag query`, with `project create-server` and `project ingest` available only as explicit recovery/debug commands. RAG query docs should mention `answer`, `citations`, `matches`, `source_nodes`, and `evidence_pack.context_markdown` so local agents use grounded evidence instead of scraping prose.

## 中文版

这里保存 Mdtero 对外发布时需要稳定的公开文档。

当前公开产品形态：

- `JonbinC/doi2md` 提供 Python/uv CLI 和 TUI。
- 上线复测使用 `mdtero smoke --json`，保持非交互、脱敏，并覆盖 discovery、DOI 解析、artifact 下载和服务端 Voyage RAG build/status/query。
- 浏览器扩展负责登录、当前页/DOI 解析、PDF/EPUB 上传、轮询、翻译和下载。
- 扩展到 CLI 的交接是公开 contract：当浏览器抓取被 publisher challenge、校园网/登录态或用户保存文件流程阻断时，继续使用 `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json` 或 `mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json`，让 `client_acquisition`、raw upload、`reason_code`、`action_hint` 和 `next_commands` 继续对本地 agent 可见。
- agent skill 通过 `mdtero agent install` 安装，不依赖 npm。
- 后端负责鉴权、额度、任务状态、MinerU PDF 解析、OpenAlex fallback discovery、LLM 翻译和 Voyage RAG，并给 agent 返回结构化 `source_nodes` / `evidence_pack`。
- 面向 agent 的 CLI JSON 和 MCP payload 必须保留 `reason_code`、`action_hint`、`next_commands` 与证据字段，同时清理 signed MinerU/OSS URL、Bearer/API-key header、Mdtero API key 和常见 token query 参数。
- MCP briefing payload 必须暴露 `mcp_tool_plan`：用 `step`、`tool`、`when`、`arguments`、`success_signal` 和 `failure_fields` 给本地 agent 一条结构化执行路线，让 agent 按状态选择 `submit_parse`、`task_status`、`download_artifact`、`request_translation`、`server_rag_status` 或 `rag_query`，而不是解析自然语言猜下一步。
- Zotero 反向同步仅限 Mdtero 解析结果 note/tag 写回成功解析的 Zotero 来源任务，不要写成改写 Zotero 题录元数据。

公开文档不要把 GROBID 写成用户可选择的公开解析引擎；RAG 不要写成只能手动传 server project id，公开 CLI 主流程是 `rag build`、再 `rag query`，`project create-server` 和 `project ingest` 只作为显式恢复/调试命令。RAG query 文档要说明 `answer`、`citations`、`matches`、`source_nodes` 和 `evidence_pack.context_markdown`，让本地 agent 使用结构化证据而不是解析自然语言输出。
