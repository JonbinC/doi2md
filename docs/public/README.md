# Public Docs

This directory keeps stable public-facing notes for the Mdtero launch surfaces.

The current public product shape is:

- Python/uv CLI and TUI from `JonbinC/doi2md`.
- Browser extension for login, DOI/current-page parse, PDF/EPUB upload, polling, translation, and download.
- Agent skill installation through `mdtero agent install`; npm is legacy compatibility only.
- Backend-owned auth, quota, task state, MinerU PDF parsing, OpenAlex fallback discovery, LLM translation, and Voyage RAG with structured `source_nodes` / `evidence_pack` output for agents.
- Zotero reverse sync is limited to Mdtero result notes/tags for succeeded Zotero-origin tasks; it must not be described as bibliographic metadata rewriting.

Do not present GROBID as a public user-selectable parser. Do not describe RAG as requiring manual project ids; the public CLI flow is `rag build`, then `rag query`, with `project create-server` and `project ingest` available only as explicit recovery/debug commands. RAG query docs should mention `answer`, `citations`, `matches`, `source_nodes`, and `evidence_pack.context_markdown` so local agents use grounded evidence instead of scraping prose.

## 中文版

这里保存 Mdtero 对外发布时需要稳定的公开文档。

当前公开产品形态：

- `JonbinC/doi2md` 提供 Python/uv CLI 和 TUI。
- 浏览器扩展负责登录、当前页/DOI 解析、PDF/EPUB 上传、轮询、翻译和下载。
- agent skill 通过 `mdtero agent install` 安装，不依赖 npm。
- 后端负责鉴权、额度、任务状态、MinerU PDF 解析、OpenAlex fallback discovery、LLM 翻译和 Voyage RAG，并给 agent 返回结构化 `source_nodes` / `evidence_pack`。
- Zotero 反向同步仅限 Mdtero 解析结果 note/tag 写回成功解析的 Zotero 来源任务，不要写成改写 Zotero 题录元数据。

公开文档不要把 GROBID 写成用户可选择的公开解析引擎；RAG 不要写成只能手动传 server project id，公开 CLI 主流程是 `rag build`、再 `rag query`，`project create-server` 和 `project ingest` 只作为显式恢复/调试命令。RAG query 文档要说明 `answer`、`citations`、`matches`、`source_nodes` 和 `evidence_pack.context_markdown`，让本地 agent 使用结构化证据而不是解析自然语言输出。
