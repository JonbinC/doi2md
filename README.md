# Mdtero Extension 📄✨

**Mdtero** is a powerful Chrome Extension and API toolkit designed to seamlessly convert dense academic research papers into clean, beautifully structured Markdown and authentic translated formats without losing scientific rigor.

This repository hosts the **public open-source extension code** and the **developer API integration guides**, demonstrating our commitment to transparency and empowering the developer community to build custom AI workflows on top of our parsing engine.

---

## 🚀 Features

- **One-Click Parsing**: Detects DOIs natively from academic publishers (e.g., ScienceDirect) and extracts the full paper payload.
- **True Scientific Accuracy**: Preserves LaTeX equations, distinct data tables, and authentic figure references that regular scraping tools destroy.
- **AI-Powered Translations**: Offers fully integrated English-to-Chinese academic translations using optimized LLM prompts without losing markup structure.
- **Customizable Exports**: Download your parsed research as Markdown (`.md`), PDF, XML, or a complete ZIP bundle containing local images.
- **Agent Integrations**: Built-in support for Claude Code, OpenClaw, and other Model Context Protocol (MCP) clients.

---

## 🛠️ Installation (Chrome Extension)

While the extension is currently pending official review on the Google Chrome Web Store, you can install the open-source version directly:

1. Download the latest `mdtero-extension-beta.zip` from our official website or build it from this repository.
2. Unzip the file into a folder.
3. Open Google Chrome and navigate to `chrome://extensions`.
4. Enable **Developer mode** in the top-right corner.
5. Click **Load unpacked** and select the folder where you extracted the extension.
6. Click the Mdtero icon in your toolbar, enter your API Key, and start parsing!

---

## 💻 Developer API & Agent Integrations

Mdtero is built for developers. You can bypass the extension entirely and use our REST API or AI Agents to parse papers natively within your IDE.

### 1. OpenClaw / MCP Integration (Recommended)
You can give your local AI Assistant (like OpenClaw or Cursor) the ability to read papers natively.
Check the [OpenClaw Integration Guide](./openclaw/INSTALL.md) for configuration instructions.

### 2. Claude Code Integration
Check the [Claude Code Integration Guide](./codex/INSTALL.md) for configuration via the official Anthropic CLI.

### 3. Direct REST API
You can easily parse documents directly using `cURL` or Python.
Generate an API key from your [Mdtero Account Dashboard](https://mdtero.pages.dev/account), then refer to our [API Documentation](https://mdtero.pages.dev/api) for endpoint specifications.

*(Example: Initiating a parse task)*
```bash
curl -X POST https://api.mdtero.com/tasks/parse \
  -H "Authorization: Bearer mdt_live_your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{"paper_input": "10.1016/j.enconman.2026.121230"}'
```

---

## 🔒 Privacy & Architecture

This repository contains the **client-side extension code**. We believe in transparency for browser plugins, which is why the extension is open-source. The extension only activates when you explicitly request a parse, and it only reads the requested academic content to obtain the DOI/Source.

Our heavy lifting—the proprietary chunking, LLM translation pipelines, Stripe billing, and LaTeX reconstruction engine—is securely hosted on our closed-source API backend (`api.mdtero.com`).

---

## 📬 Support & Contact

If you encounter any issues or have feature requests, please drop us an email at **support@mdtero.com** or open an Issue in this repository.

*Mdtero is a research workflow tool. We empower researchers to interact with science natively.*
