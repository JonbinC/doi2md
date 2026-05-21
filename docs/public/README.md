# Public Docs

This directory keeps stable public-facing notes for the Mdtero launch surfaces.

The current public product shape is:

- Python/uv CLI and TUI from `JonbinC/doi2md`.
- Browser extension for login, DOI/current-page parse, PDF/EPUB upload, polling, translation, and download.
- Agent skill installation through `mdtero agent install`; npm is legacy compatibility only.
- Backend-owned auth, quota, task state, MinerU PDF parsing, OpenAlex fallback discovery, LLM translation, and Voyage RAG.

Do not present GROBID as a public user-selectable parser. Do not claim Zotero reverse sync is complete until that workflow is implemented and tested.

## 中文版

这里保存 Mdtero 对外发布时需要稳定的公开文档。

当前公开产品形态：

- `JonbinC/doi2md` 提供 Python/uv CLI 和 TUI。
- 浏览器扩展负责登录、当前页/DOI 解析、PDF/EPUB 上传、轮询、翻译和下载。
- agent skill 通过 `mdtero agent install` 安装；npm 只保留旧兼容。
- 后端负责鉴权、额度、任务状态、MinerU PDF 解析、OpenAlex fallback discovery、LLM 翻译和 Voyage RAG。

公开文档不要把 GROBID 写成用户可选择的公开解析引擎；Zotero 反向同步在完成和测试前也不要写成已上线能力。
