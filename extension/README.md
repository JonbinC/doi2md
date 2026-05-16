# Mdtero Extension

Mdtero Extension is the local browser product surface for turning papers into Markdown and translated Markdown. It uses Mdtero Account on the website for sign-in, asks the backend for the canonical route plan, and only uses this browser or the local helper when the selected route needs local access.

## Install

Build or install the packaged extension, then load the extension folder in a Chromium browser. The extension needs storage for your Mdtero token and connector keys, downloads for Markdown and translation artifacts, tabs for supported paper pages, native messaging for the optional local runtime, and host access for Mdtero plus supported scholarly sources.

```bash
npm install
npm run build
```

## Sign In

Open the popup or options page and choose **Open Mdtero Account**. Sign in at `https://mdtero.com/account`; the website can hand the extension a `{ type: "mdtero.auth.token", token, email }` message through the trusted auth bridge on Mdtero origins. The options page keeps email/password and email-code fields as a fallback only until the website exposes a single-use extension handoff code.

## Parse Papers

Start from a DOI, the current paper tab, or a local PDF/EPUB. The extension sends the input to the backend SSOT route endpoint, executes the returned route plan, creates the parse task, polls it, and shows the returned artifacts. Markdown is the primary download when `paper_md` is available; source PDF/XML and fallback bundles appear as separate artifact actions.

Supported paths work best for arXiv, PMC / Europe PMC, bioRxiv / medRxiv, PLOS, Springer Open Access, and publisher pages where your browser or connector keys already have access. Elsevier, Wiley, Springer, and similar publisher routes may need connector keys, institution access, or the local helper.

## Translate

After a parse task succeeds, the Translate button uses the parsed `paper_md.path` as `source_markdown_path` for `POST /tasks/translate`. The extension does not invent alternate source selection; it only submits the backend-supported Markdown path, polls the translation task, and exposes the returned `translated_md` artifact for download.

## Privacy And Local Files

Tokens, email, UI language, and optional publisher connector keys are stored in browser local storage. Local PDF/EPUB intake uploads the chosen file to create a parse task. Publisher page capture and native-helper acquisition stay on your machine unless the backend route plan asks the extension to submit the acquired helper bundle or artifact for parsing.
