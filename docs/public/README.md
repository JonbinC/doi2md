# Public Docs

This directory keeps stable public-facing notes for the Mdtero launch surfaces.

The current public product shape is:

- Python/uv CLI and TUI from `JonbinC/doi2md`.
- Repeatable deploy smoke through `mdtero smoke --json`; it should stay non-interactive, secret-safe, and broad enough to cover discovery, DOI parse, artifact download, server-side RAG build/status/query, and MCP briefing tool availability.
- Browser extension for login, DOI/current-page parse, PDF/EPUB upload, polling, translation, and download.
- Extension-to-CLI handoff is a public contract: when browser capture is blocked by a publisher challenge, campus-network/session-bound access, or a user-saved file workflow, continue with the full CLI recovery bundle: `mdtero doctor --json`, `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json`, `mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json`, `mdtero status <task-id> --wait --timeout 300 --json`, `mdtero download <task-id> paper_md --output-dir ./mdtero-output --json`, `mdtero rag query "What are the strongest findings?" --build-if-needed --json`, `mdtero mcp briefing --json`, and `mdtero mcp serve` so route diagnostics, raw upload state, `reason_code`, `action_hint`, `download_artifacts`, `next_commands`, and the FastMCP stdio server contract remain visible to local agents.
- Dashboard task history can copy `dashboard_handoff_json`; agents must treat it as a starting state, validate it with `task_status`, preserve task ids, route diagnostics, parse diagnostics, download artifacts, and next commands, then continue through `download_artifact`, `request_translation`, `server_rag_status`, or `rag_query`.
- Agent skill installation through `mdtero agent install`; the npm runtime path is retired.
- Backend-owned auth, quota, task state, document parsing, discovery fallback, translation, and RAG with structured `source_nodes` / `evidence_pack` / `citation_contract` output for agents.
- Agent-facing CLI JSON and MCP payloads must keep `reason_code`, `action_hint`, `next_commands`, and evidence fields visible while sanitizing signed artifact URLs, bearer/API-key headers, Mdtero API keys, and common token query parameters.
- MCP briefing payloads must expose `mcp_tool_plan`: a structured agent playbook with `step`, `tool`, `when`, `arguments`, `success_signal`, and `failure_fields` so local agents choose `project_init`, `project_add`, `submit_parse`, `task_status`, `download_artifact`, `request_translation`, `server_rag_status`, `server_rag_build`, or `rag_query` without guessing from prose.
- Zotero reverse sync is limited to Mdtero result notes/tags for succeeded Zotero-origin tasks; it must not be described as bibliographic metadata rewriting.

Do not present parser engine selection as a public user option. Do not describe RAG as requiring manual project ids; the public CLI flow is `mdtero rag query "What are the strongest findings?" --build-if-needed --json`, with `rag build`, `project create-server`, and `project ingest` available only as explicit recovery/debug commands. RAG query docs should mention `answer`, `citations`, `matches`, `source_nodes`, `evidence_pack.context_markdown`, and `citation_contract.required_for_final_answer` so local agents use grounded evidence instead of scraping prose, and so final answers preserve `citations` plus `source_nodes`.

## 中文版

这里保存 Mdtero 对外发布时需要稳定的公开文档。

当前公开产品形态：

- `JonbinC/doi2md` 提供 Python/uv CLI 和 TUI。
- 上线复测使用 `mdtero smoke --json`，保持非交互、脱敏，并覆盖 discovery、DOI 解析、artifact 下载、服务端 RAG build/status/query 和 MCP briefing tool 可用性。
- 浏览器扩展负责登录、当前页/DOI 解析、PDF/EPUB 上传、轮询、翻译和下载。
- 扩展到 CLI 的交接是公开 contract：当浏览器抓取被 publisher challenge、校园网/登录态或用户保存文件流程阻断时，继续使用完整 CLI 恢复链路：`mdtero doctor --json`、`mdtero parse <doi-or-url> --trace --wait --timeout 300 --json`、`mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json`、`mdtero status <task-id> --wait --timeout 300 --json`、`mdtero download <task-id> paper_md --output-dir ./mdtero-output --json`、`mdtero rag query "What are the strongest findings?" --build-if-needed --json`、`mdtero mcp briefing --json` 和 `mdtero mcp serve`，让路由诊断、raw upload 状态、`reason_code`、`action_hint`、`download_artifacts`、`next_commands` 和 FastMCP stdio server contract 继续对本地 agent 可见。
- Dashboard 任务历史可以复制 `dashboard_handoff_json`；agent 应把它当作起始状态，先用 `task_status` 校验，再保留任务 id、路由诊断、解析诊断、download artifacts 与 next commands，然后继续调用 `download_artifact`、`request_translation`、`server_rag_status` 或 `rag_query`。
- agent skill 通过 `mdtero agent install` 安装，不依赖 npm。
- 后端负责鉴权、额度、任务状态、文档解析、discovery fallback、翻译和 RAG，并给 agent 返回结构化 `source_nodes` / `evidence_pack` / `citation_contract`。
- 面向 agent 的 CLI JSON 和 MCP payload 必须保留 `reason_code`、`action_hint`、`next_commands` 与证据字段，同时清理 signed artifact URL、Bearer/API-key header、Mdtero API key 和常见 token query 参数。
- MCP briefing payload 必须暴露 `mcp_tool_plan`：用 `step`、`tool`、`when`、`arguments`、`success_signal` 和 `failure_fields` 给本地 agent 一条结构化执行路线，让 agent 按状态选择 `project_init`、`project_add`、`submit_parse`、`task_status`、`download_artifact`、`request_translation`、`server_rag_status`、`server_rag_build` 或 `rag_query`，而不是解析自然语言猜下一步。
- Zotero 反向同步仅限 Mdtero 解析结果 note/tag 写回成功解析的 Zotero 来源任务，不要写成改写 Zotero 题录元数据。

公开文档不要把 parser engine selection 写成用户可选择的公开选项；RAG 不要写成只能手动传 server project id，公开 CLI 主流程是 `mdtero rag query "What are the strongest findings?" --build-if-needed --json`，`rag build`、`project create-server` 和 `project ingest` 只作为显式恢复/调试命令。RAG query 文档要说明 `answer`、`citations`、`matches`、`source_nodes`、`evidence_pack.context_markdown` 和 `citation_contract.required_for_final_answer`，让本地 agent 使用结构化证据而不是解析自然语言输出，并在最终回答中保留 `citations` 与 `source_nodes`。
