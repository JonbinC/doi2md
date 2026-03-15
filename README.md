<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero Logo" width="120"/>

  # Mdtero: Academic Markdown & Translation Engine
  
  *Transform dense academic PDFs and webpages into fully structured, strictly accurate Markdown.*

  [![Website Status](https://img.shields.io/website?url=https%3A%2F%2Fmdtero.com&label=website)](https://mdtero.com)
  [![API Status](https://img.shields.io/badge/API-Live-success?style=flat&logo=serverless)](https://api.mdtero.com)
  [![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
  
  <br/>
  
  [🌎 Visit Our Official Dashboard](https://mdtero.com) • [📖 API Documentation](https://mdtero.com/api)

  <br/>
  
  [**English Installation Guide**](#english) &nbsp;|&nbsp; [**中文安装说明**](#chinese)
</div>

---

<br/>

<a name="english"></a>
## 🇬🇧 English: Mdtero Extension & Open API

**Mdtero** is a powerful web platform, Chrome Extension, and API toolkit designed to comprehensively render academic journal articles, saving researchers hours of manual extraction and translation time. 

This repository hosts our **public open-source Chrome extension** and our **developer API integration guides**, establishing total transparency regarding what runs in your browser, and empowering the developer community to build custom MCP Agent workflows.

### ✨ Key Capabilities

| Feature | Description |
| :--- | :--- |
| **🌍 Unified Web Dashboard** | Manage parsed papers, account credits, and view authentic demos natively on our [official website](https://mdtero.com). |
| **🖱️ One-Click Extraction** | Detects DOIs from science publishers (e.g., ScienceDirect) and extracts the full paper payload directly in-browser. |
| **🔬 True Scientific Rigor** | Perfectly preserves LaTeX equations, multi-cell data tables, and authentic figure references—elements regular LLMs destroy. |
| **🤖 Native AI Translations** | Deeply integrated English-to-Chinese academic translations using optimized LLM prompts *(Without losing Markdown markup)*. |
| **🔌 MCP Agent Integrations** | Built-in API compatibility for Claude Code, OpenClaw, Cursor, and other Model Context Protocol agents. |

---

### 📦 Quick Start (Chrome Extension)

1. Download the latest `mdtero-extension-beta.zip` from our [Homepage](https://mdtero.com/demo) or clone this repo.
2. Unzip the archive to a permanent folder.
3. Open Google Chrome and enter `chrome://extensions` in your URL bar.
4. Toggle **Developer mode** ON (top-right corner).
5. Click **Load unpacked** and select the unzipped folder.
6. Click the newly added **Mdtero icon** in your extensions toolbar. 
7. Enter your highly secure API Key (generated via your [Account Dashboard](https://mdtero.com/account)), and you're ready to parse!

<br/>

### 💻 Developer API & Agent Workflows

Mdtero is engineered for researchers who code. After generating your API key at [mdtero.com/account](https://mdtero.com/account), you can bypass the extension entirely:

- 🧠 **OpenClaw / MCP Integration**: Grant your local AI Assistant (like Cursor) the ability to parse and read full papers natively. 👉 [View OpenClaw Guide](./openclaw/INSTALL.md).
- 🤖 **Claude Code Integration**: Pass papers directly into Anthropic's CLI. 👉 [View Claude Code Guide](./codex/INSTALL.md).
- ⚡ **Direct REST API**: Use standard `cURL` or Python to trigger remote parsing jobs against `api.mdtero.com`. See our full [API Documentation](https://mdtero.com/api).

---

<br/><br/>

<a name="chinese"></a>
## 🇨🇳 中文：Mdtero 浏览器插件与开放 API

<div align="center">
  *"让顶刊文献的解析、排版与翻译成为一键式享受"*
</div>

**Mdtero** 是一款专为科研工作者打造的全栈学术处理平台、Chrome 浏览器插件与开放 API 工具箱。它被精心设计用于将密集的学术论文无缝转换为结构清晰、排版极其精美的 Markdown 格式，同时绝对保证科研数据的严谨性。

本仓库托管了我们 **开源的 Chrome 浏览器客户端代码** 以及 **开发者 API 接入指南**。我们致力于保障学术记录的隐私安全，并支持开发者在我们的核心解析引擎之上，使用大语言模型构建属于自己的自动化科研工作流。

### ✨ 核心功能亮点

| 功能模块 | 详细说明 |
| :--- | :--- |
| **🌍 网页端控制台** | 在我们的 [官方主页](https://mdtero.com) 统一管理您的解析历史、账户余额，并深度体验无损渲染。 |
| **🖱️ 一键极速解析** | 自动检测学术出版商（如 ScienceDirect）页面上的 DOI，并在浏览器内一键触发长文本全文获取。 |
| **🔬 真正的科研级精度** | 完美保留原本会被普通 LLM 或爬虫彻底破坏的 **LaTeX 数学公式**、复杂数据表格以及真实的图表文献引用体系。 |
| **🤖 深度学术翻译** | 原生集成极高标准的英文至中文大模型翻译，应用前沿的 Prompt 矩阵，保证 Markdown 排版结构 100% 不丢失。 |
| **🔌 前沿 Agent 接入** | 内置对 Claude Code, OpenClaw 以及各种 Model Context Protocol (MCP) 智能助手的 API 原生读取支持。 |

---

### 📦 插件安装说明 (面向普通用户)

1. 从我们的 [主页 Demo](https://mdtero.com/demo) 下载最新的 `mdtero-extension-beta.zip`，或直接使用本仓库源码编译。
2. 将 ZIP 文件解压到一个您不会删除的固定目录。
3. 打开 Google Chrome 浏览器并跳转至 `chrome://extensions`。
4. 打开页面右上角的 **“开发者模式 (Developer mode)”** 开关。
5. 点击左上角的 **“加载已解压的扩展程序 (Load unpacked)”**，并选中您刚才解压的文件夹。
6. 点击浏览器地址栏右侧的 **Mdtero 图标**。
7. 粘贴您在 [账户后台](https://mdtero.com/account) 安全生成的 API 密钥，即可立即开启学术解析之旅！

<br/>

### 💻 开发者 API 与 Agent 接入指南 (面向极客)

Mdtero 生来拥抱开发者生态。在您的 [个人 Dashboard](https://mdtero.com/account) 中生成 API 密钥后，即可参阅 [API 官方文档](https://mdtero.com/api) 获取所有后台能力接口：

- 🧠 **OpenClaw / MCP 协议接入**: 赋予您本地的 AI 编程助手（如 Cursor）原生阅读顶级学术论文的能力。 👉 [点此查看 OpenClaw 配置说明](./openclaw/INSTALL.md)。
- 🤖 **Claude Code 接入**: 将解析能力注入 Anthropic 官方控制台。 👉 [点此查看 Claude Code 说明](./codex/INSTALL.md)。
- ⚡ **原生 REST API**: 您完全可以通过终端 `cURL` 或是 Python 脚本直接向云端 `api.mdtero.com` 提交高并发解析及翻译任务。

---

<br/>

### 🔒 隐私与系统架构设计 (Privacy Architecture)

本仓库公开的仅为**前端客户端与插件的开源源码**，目的是供学术机构和用户进行极高标准的安全与隐私审计。

我们需要明确说明：您设备上的插件绝对不会监控您的日常浏览。它仅仅包含一个按钮，只有当您主动要求解析时，才会短暂读取当前页面的 DOI 元素。

真正极其繁重的计算密集型任务——**专有 Markdown 结构化防断版算法、多路并发 LLM 翻译流水线、Stripe 安全计费扣款系统、以及核心的 LaTeX 解析与重建智能引擎**——均受到最高级别的商业保护，稳定运行在我们完全闭源的云端专属服务器上。
