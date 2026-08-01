<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero

  *Structured Markdown for research workflows.*
</div>

Mdtero turns papers into reusable Markdown packages for reading, translation, project research, and local agents.

**Languages:** English | [简体中文](./README_CN.md)

## Install

```bash
uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero doctor --json
```

During alpha, install from this GitHub repository. If `uv` is unavailable, use the installer:

```bash
curl -Ls https://mdtero.com/install.sh | sh
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

The installer supports `uv`, `pipx`, and Python fallbacks. `--agent <target>` installs a local agent skill.

## Use Mdtero

```bash
mdtero discover "thermal energy storage" --limit 5 --interactive
mdtero parse <doi-or-url> --wait --timeout 300 --json
mdtero parse --file paper.pdf --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero translate <task-id> --to zh-CN --wait --timeout 600 --json
```

For a literature set, create a project and ask cited questions after processing documents:

```bash
mdtero project init --name literature-review
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
```

Zotero support is conservative: `mdtero zotero sync` adds Mdtero result notes and tags for matching succeeded items without rewriting Zotero bibliographic metadata.

## Browser And Agents

Use the browser extension for a paper open in your browser, content accessed through your own session, or a file you want to upload. The extension and CLI share task history, downloads, and translation.

Install a local agent skill with:

```bash
mdtero agent install --interactive
mdtero mcp briefing --json
```

The briefing provides safe task state, available downloads, citations, and suggested next steps. Keep API keys and other secrets out of prompts, logs, and repositories. For a trusted headless machine, enter a fresh key only at the secure `mdtero setup --api-key --json` prompt.

## Access Boundaries

Mdtero helps process material you are permitted to access. Publisher subscriptions, institutional access, and source-specific credentials remain your responsibility. When a source needs your browser session or a local copy, use the extension or upload the saved file.

Parser and source-selection implementation are service internals, not user configuration. The stable workflow is submit, check status, download, translate, and use the resulting Markdown in a project.

## Documentation

- [Mdtero website](https://mdtero.com)
- [Documentation](https://mdtero.com/docs/)
- [Install guide](https://mdtero.com/docs/install.html)

## Development

```bash
uv run --with pytest --with rich --with textual --with httpx --with requests --with curl_cffi --with pyzotero --with fastmcp pytest tests_py -q
npm --prefix extension test
npm --prefix extension run build
```
