<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero 公开安装入口

  *面向论文转 Markdown 工作流的 Python/uv CLI、TUI、浏览器扩展和 agent skill bundle。*
</div>

Mdtero 把论文转换成可复用的 Markdown 研究包，供人类、本地 agent 和后续 RAG 工作流继续使用。

**语言：** [English](./README.md) | 简体中文

这个仓库是当前公开上线入口的源头：

- Python runtime CLI/TUI 包 `mdtero`，alpha 阶段使用 `uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git` 安装。
- 浏览器扩展用于 OAuth 登录、DOI/当前页解析、PDF/EPUB 上传、翻译、轮询和下载。
- agent skill bundle 由 Python CLI 的 `mdtero agent install` 安装。

旧 npm installer runtime 已从本仓库退役。Skill 安装由 Python CLI 负责。

## 快速开始

```bash
uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero doctor --json
```

alpha 阶段，GitHub 安装命令是已验证的公开安装路径。旧 PyPI `mdtero` 包目前指向已退役的后端 bundle；只有等公开客户端重新发布到 PyPI 后，才使用 `uv tool install mdtero`。

如果机器没有 `uv`，使用安装脚本：

```bash
curl -Ls https://mdtero.com/install.sh | sh
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

脚本会优先使用 `uv`，失败后退到 `pipx install --force git+https://github.com/JonbinC/doi2md.git`，再退到 `python3 -m pip install --user --force-reinstall git+https://github.com/JonbinC/doi2md.git`。传入 `--agent <target>` 可以同时安装 agent skill。

`mdtero setup` 会在交互流程里处理登录、可选学术 key 配置和本地 agent 工作区检测。它会检测本地 Codex/Claude/Gemini/Hermes/OpenCode 工作区，并可在 onboarding 时安装选中的 agent skill。无头 setup 使用 `mdtero setup --api-key --json` 或 `MDTERO_API_KEY`，会跳过 agent 检测；之后在 agent 所在工作站上运行 `mdtero agent install --interactive`。不要把 API key 值直接写进 shell history。

## 人类工作流

直接从终端或本地工作站使用时，常用路径如下：

```bash
mdtero discover "thermochemical energy storage" --limit 5 --interactive
mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json
mdtero parse --file paper.pdf --trace --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero tui
```

当内容依赖浏览器登录、校园网/登录态、出版社 challenge 页或当前页 capture 时，使用浏览器扩展。扩展可以把 DOI、URL、PDF、EPUB、HTML 或 XML artifact 交还给 CLI，让 route planning、raw upload、任务轮询、下载和结构化失败字段保持可见。

## 项目工作流

处理一组论文时，使用本地 Mdtero project：

```bash
mdtero project init --name literature-review
mdtero project add 10.48550/arXiv.1706.03762 --json
mdtero project status --json
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero project refresh --wait --timeout 300 --json
mdtero project download --output-dir ./mdtero-output --json
```

Zotero 导入和同步是保守设计：

```bash
mdtero config zotero
mdtero zotero import --json
mdtero zotero sync --json
```

`mdtero zotero sync` 只为已成功解析且来源为 Zotero、带 Zotero item key 的任务创建 Mdtero 结果 note/tag；不会改写 Zotero 文献元数据。

## Agent 工作流

当本地 agent 需要继续工作，并且不应该解析终端表格时，使用 JSON 和 MCP 入口：

```bash
mdtero setup --json
mdtero doctor --json
mdtero mcp briefing --json
mdtero mcp serve
```

Agent 规则：

- 在 parse、project、RAG 或 MCP 工作前先运行 `mdtero doctor --json`；它会返回安全的认证/依赖/学术 key/Zotero/project/RAG 摘要和 safe `next_commands`，且不会回显 secret。
- 跟随 setup、doctor、parse、status、project refresh、RAG status 和 MCP tools 返回的 `next_commands`。
- 保留任务 id、路由诊断、质量标签、首选 artifact、下载 artifact、reason code、action hint、translation attempts、citation contract、citations 和 source nodes。
- 把 copied task handoff JSON 和 `dashboard_handoff_json` 当作起始状态，然后先用 `task_status` 或 `server_rag_status` 校验，再继续执行。
- 当 dashboard 创建的 key 或本地 config 已可用时，不要让用户把长期 secret 粘贴到 prompt 里。
- 不要把 API key、signed URL、bearer token、对象存储 token 或服务凭据写进 prompt 和日志。

首选 MCP 入口是 `agent_briefing`。它会返回账户状态、项目健康、可下载成果、失败项、RAG 状态、扩展/CLI 交接、推荐下一步命令，以及结构化 `mcp_tool_plan` playbook。这个 playbook 带 `step`、`tool`、`when`、`arguments`、`success_signal` 和 `failure_fields`，让本地 agent 按状态选择 `project_init`、`project_add`、`submit_parse`、`task_status`、`download_artifact`、`request_translation`、`server_rag_status`、`server_rag_build` 或 `rag_query`。

## 常用命令

```bash
mdtero doctor
mdtero doctor --json
mdtero login
mdtero setup --api-key --json
mdtero config academic
mdtero config academic --semantic-scholar-key <key> --json
mdtero project init --json
mdtero project status --json
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero project refresh --wait --timeout 300 --json
mdtero project download --output-dir ./mdtero-output --json
mdtero config zotero
mdtero zotero import --json
mdtero zotero sync --json
mdtero discover "thermochemical energy storage" --limit 5 --json
mdtero discover Thermochemical Energy storage Vermiculite --limit 5 --json
mdtero discover "thermochemical energy storage" --limit 5 --interactive
mdtero discover "thermochemical energy storage" --limit 5 --add --select 1,3 --json
mdtero discover "<query>" --limit 5 --add --select 1,3 --json
mdtero parse 10.48550/arXiv.1706.03762 --json
mdtero parse '10.1016/S0260-8774(02)00304-7' --trace --wait --timeout 300 --json
mdtero parse https://example.org/open-paper --trace --wait --timeout 300 --json
mdtero parse --file paper.pdf --trace --wait --timeout 600 --json
mdtero parse --batch ./papers --wait --timeout 300 --json
mdtero parse-batch dois.txt --wait --download paper_md --output-dir ./mdtero-output --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero download <task-id> paper_md --filename-template "{author}_{year}_{shorttitle}" --output-dir ./mdtero-output --json
mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json
mdtero translate paper.md --to zh-CN --wait --timeout 600 --json
mdtero rag status --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero rag build --wait --json
mdtero smoke --json --timeout 600 --interval 2
mdtero smoke --skip-translate --json
mdtero mcp briefing --json
mdtero mcp serve
mdtero agent detect --json
mdtero agent install --interactive
mdtero agent install --target codex
mdtero agent install --all
mdtero tui
```

## Agent Targets

```bash
mdtero agent install --target claude_code
mdtero agent install --target codex
mdtero agent install --target gemini_cli
mdtero agent install --target hermes
mdtero agent install --target opencode
mdtero agent detect --json
mdtero agent install --interactive
mdtero agent install --all
mdtero agent uninstall --target codex
```

当 agent 或脚本需要机器可读的检测结果、安装状态和精确安装命令时，先运行 `mdtero agent detect --json`。人类 setup 流程可用 `mdtero agent install --interactive` 查看检测到的工作区，并按编号或 target name 多选；直接回车会安装已检测但尚未安装的目标。不传 `--target` 时，Mdtero 会检测已有 `~/.codex`、`~/.claude`、`~/.gemini`、`~/.hermes` 和 `~/.opencode` 目录并安装到对应工作区。

OpenClaw 保持独立路径：

```bash
clawhub install mdtero
```

## RAG 和证据契约

服务端 RAG 的主路径是：

```bash
mdtero rag query "What are the strongest findings?" --build-if-needed --json
```

它可以用一条 agent-safe 命令完成 create、bind、import、build 和 query。Query JSON 会返回抽取式 `answer`、稳定 `citations`、原始 `matches`、类 LlamaIndex 的 `source_nodes`、`evidence_pack.context_markdown`、`citation_contract.required_for_final_answer`、`reason_code` 和 `next_commands`。最终回答必须 preserve `citations` plus `source_nodes`。

当一条命令路径不够时，仍可使用显式恢复/调试命令：

```bash
mdtero project ingest --json
mdtero project create-server --json
mdtero project link --server-project-id <id> --json
mdtero rag status --json
mdtero rag build --wait --json
```

## 扩展到 CLI 的交接

扩展到 CLI 的交接是 publisher challenge、校园网/登录态和浏览器保存文件场景的公开恢复 contract：

```bash
mdtero doctor --json
mdtero parse <doi-or-url> --trace --wait --timeout 300 --json
mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero project ingest --json
mdtero rag query "<question>" --build-if-needed --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero mcp briefing --json
mdtero mcp serve
```

这条路径会保留 `client_acquisition`、raw upload、状态轮询、`reason_code`、`action_hint`、`download_artifacts` 和 `next_commands`，而不是把失败隐藏在浏览器扩展里。

## 当前 Alpha 范围

当前 alpha 已验证：

- API-key login、`mdtero doctor`、`mdtero doctor --json` 和本地配置；JSON 诊断包含安全的 auth/dependency/academic/Zotero/project/RAG 摘要和 `next_commands`，不会回显 secret。
- `mdtero smoke --json` 部署 smoke；它创建隔离项目，跑 discovery、arXiv/DOI parse、task polling、artifact download、服务端 RAG build/status/query，验证 `mdtero mcp briefing --json` 暴露 `agent_briefing`、`server_rag_status`、`server_rag_build` 和 `rag_query`，失败时返回 step 级 `reason_code`、`action_hint`、task ids、paths、server project id，以及顶层 `primary_failure`、`failed_steps` 和恢复 `next_commands`。
- 可选学术 key setup，既支持交互式 `mdtero config academic`，也支持 `--semantic-scholar-key <key> --json` 等无头 flags；JSON 输出只报告 configured/missing，不回显 secret。
- DOI/arXiv parse、状态轮询、Markdown/bundle 下载。
- DOI/URL 批量解析：`mdtero parse-batch dois.txt --wait --download paper_md --output-dir ./mdtero-output --json`，写出 `manifest.csv` 和 `failed.csv`。
- PDF 上传走后端文档解析路径，解析成功时返回 Markdown 和 zip artifacts。
- 本地 project init/add/remove/list/status、BibTeX 导入去重、project parse/refresh/download，以及 agent-readable JSON。
- Zotero 元数据导入本地 Mdtero project，并把成功解析任务的 note/tag 保守同步回 Zotero。
- Discovery 配置 Semantic Scholar 时走本地 Semantic Scholar，否则走后端 OpenAlex fallback。Semantic Scholar 不可用时，`--json` 返回 `local_semantic_scholar_failure` 和 `discovery_fallback`，agent 可保留 reason code 后继续走 OpenAlex。
- `status`、waited parse results 和 downloads 暴露 `quality_label` / `quality_warning`，用于 `metadata_only`、`abstract_only`、`section_only_fulltext`、`low_confidence_parse` 等低内容产物；Markdown 下载默认 `author_year_shorttitle.md`，低置信全文会追加 `.low_quality.md`，并更新 `manifest.csv`。
- 本地 route acquisition 使用 `curl_cffi` 获取后端规划的 HTML/XML/EPUB/PDF 来源，并有 `httpx` fallback 和可见 `client_acquisition` trace 输出。
- 从 parse task id 或本地 Markdown 发起服务端翻译。
- 本地 FastMCP project context server，包括 `agent_briefing` tool，用于一次返回账户状态、项目健康、可下载成果、失败项、RAG 状态、agent skill 检测/安装/待安装状态、推荐命令和 `mcp_tool_plan`。
- TUI dashboard command palette，提供可复制的 setup、discovery、parse、Zotero、RAG、MCP 和 agent-install 命令，并高亮当前下一步。
- 面向 agent 的 CLI JSON 和 MCP payload 会在返回本地 agent 前清洗 signed artifact URLs、bearer/API-key headers、Mdtero API keys 和常见 token query parameters，同时保留 `reason_code`、`action_hint`、`next_commands` 和证据字段。
- Codex、Claude Code、Gemini CLI、Hermes 和 OpenCode 的 agent skill 安装。

## Shared `/api/v1` 服务端契约

所有输入入口共用同一组 `/api/v1` 服务端契约：

| 用途 | 路由 |
| --- | --- |
| Route 规划 | `/api/v1/route` |
| 扩展 route 规划 | `/api/v1/extension/route` |
| DOI/URL 解析任务 | `/api/v1/tasks/parse` |
| PDF/EPUB/XML/HTML 上传 | `/api/v1/tasks/upload` |
| 任务状态 | `/api/v1/tasks/{task_id}` |
| 产物下载 | `/api/v1/tasks/{task_id}/download/{artifact}` |
| Discovery search | `/api/v1/discovery/search` |
| 翻译任务 | `/api/v1/tasks/translate` |
| 服务端项目 create/list/read | `/api/v1/projects` |
| 把解析 Markdown 导入服务端项目 | `/api/v1/projects/{project_id}/tasks/{task_id}/import` |
| RAG status | `/api/v1/projects/{project_id}/rag/status` |
| 构建后端 RAG | `/api/v1/projects/{project_id}/rag/build` |
| 查询后端 RAG | `/api/v1/projects/{project_id}/rag/query` |

CLI、扩展、dashboard 和 MCP briefing 都会暴露这组 contract，保证浏览器抓取、CLI 重试、raw upload、任务轮询、下载、项目导入和后端 RAG 交接保持一致。

## 产品边界

Mdtero Account 是 Mdtero API keys、quota、billing、history 和 install prompts 的 control plane。Academic source keys 留在本地 `mdtero config academic` 配置中。Python client 负责本地 project state、BibTeX/Zotero 导入、TUI、MCP context 和 agent skill installation。后端负责 parsing、discovery fallback、translation、task artifacts 和 server-side RAG。

浏览器扩展保持为浏览器入口。它不内置 `curl_cffi`、`pyzotero` 或 `fastmcp` 等 Python 依赖；只负责 browser-context capture 和用户选择的文件上传/下载。当 publisher challenge、校园网或浏览器登录态阻止自动采集时，把 DOI、URL 或已保存 PDF/EPUB/XML/HTML 文件交给 Python CLI。

已知边界：

- `mdtero zotero sync` 是保守同步，不改写 Zotero 文献元数据。
- `mdtero rag query --build-if-needed --json` 是服务端 RAG 主路径。`mdtero rag build`、`mdtero project create-server` 和 `mdtero project ingest` 只作为显式恢复/调试命令保留。
- Parser engine selection 不是公开产品选项。PDF 解析由后端处理，内部 fallback 行为由服务端负责。

## 仓库结构

- [`src/mdtero`](./src/mdtero)：Python CLI/TUI/client package
- [`extension`](./extension)：MV3 浏览器扩展源码、测试和 build output
- [`install`](./install)：网站安装 manifest 和安装指南
- [`skills`](./skills)：agent skill source，会镜像进 Python CLI installer
- [`README.md`](./README.md)：英文 README

## 本地开发

```bash
uv run --with pytest --with rich --with textual --with httpx --with requests --with curl_cffi --with pyzotero --with fastmcp pytest tests_py -q
uv run --with build python -m build --wheel
npm --prefix extension test
npm --prefix extension run build
```
