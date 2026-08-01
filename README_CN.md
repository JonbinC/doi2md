<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero

  *面向研究工作流的结构化 Markdown。*
</div>

Mdtero 把论文转换为可复用的 Markdown 研究包，用于阅读、翻译、项目研究和本地 agent。

**语言：** [English](./README.md) | 简体中文

## 安装

```bash
uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero doctor --json
```

alpha 阶段请从本 GitHub 仓库安装。没有 `uv` 时使用安装脚本：

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

处理一组文献时，创建项目；文档处理完成后可提出带引文的问题：

```bash
mdtero project init --name literature-review
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
```

Zotero 支持采用保守方式：`mdtero zotero sync` 会为对应的成功项目添加 Mdtero 结果 note 和 tag，不会改写 Zotero 文献元数据。

## 浏览器与 Agent

浏览器中已打开论文、内容依赖你自己的登录态，或需要上传文件时，请使用浏览器扩展。扩展与 CLI 共用任务历史、下载和翻译。

安装本地 agent skill：

```bash
mdtero agent install --interactive
mdtero mcp briefing --json
```

briefing 会提供安全的任务状态、可下载成果、引文和建议的下一步。不要把 API key 或其他 secret 放入 prompt、日志或仓库。可信无头机器应仅在 `mdtero setup --api-key --json` 的安全提示中输入新 key。

## 访问边界

Mdtero 用于处理你有权访问的内容。出版社订阅、机构访问和来源专用凭据仍由用户自行负责。来源需要你的浏览器登录态或本地副本时，请使用扩展或上传已保存文件。

解析和来源选择实现属于服务内部，不是用户配置项。稳定流程是提交、查看状态、下载、翻译，再在项目中使用生成的 Markdown。

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
