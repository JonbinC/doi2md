import { readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { basename, resolve } from "node:path";

const ZIP_PATH = resolve("releases/mdtero-extension-webstore.zip");
const CHROME_UPLOAD_URL = "https://www.googleapis.com/upload/chromewebstore/v1.1/items";
const CHROME_TOKEN_URL = "https://oauth2.googleapis.com/token";
const EDGE_BASE_URL = "https://api.addons.microsoftedge.microsoft.com/v1/products";

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = {};
  if (text.trim()) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text.slice(0, 1000) };
    }
  }
  if (!response.ok) {
    const message = typeof payload === "object" ? JSON.stringify(payload) : String(payload);
    throw new Error(`HTTP ${response.status} for ${url}: ${message}`);
  }
  return { response, payload };
}

async function refreshChromeAccessToken() {
  const tokenPath = process.env.CHROME_WEBSTORE_TOKEN_FILE;
  const token = process.env.CHROME_WEBSTORE_REFRESH_TOKEN
    ? { refresh_token: process.env.CHROME_WEBSTORE_REFRESH_TOKEN }
    : await readJson(requiredEnv("CHROME_WEBSTORE_TOKEN_FILE"));
  const body = new URLSearchParams({
    client_id: requiredEnv("CHROME_WEBSTORE_CLIENT_ID"),
    client_secret: requiredEnv("CHROME_WEBSTORE_CLIENT_SECRET"),
    refresh_token: token.refresh_token,
    grant_type: "refresh_token"
  });
  const { payload } = await requestJson(CHROME_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
  const updated = { ...token, ...payload };
  if (tokenPath) {
    await writeFile(tokenPath, JSON.stringify(updated, null, 2) + "\n", { mode: 0o600 });
  }
  return updated.access_token;
}

async function uploadChromeDraft() {
  const extensionId = requiredEnv("CHROME_WEBSTORE_EXTENSION_ID");
  const accessToken = await refreshChromeAccessToken();
  const zipBytes = await readFile(ZIP_PATH);
  const { payload } = await requestJson(`${CHROME_UPLOAD_URL}/${extensionId}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/zip"
    },
    body: zipBytes
  });
  console.log(JSON.stringify({ store: "chrome", action: "draft-upload", ...payload }));
}

async function uploadEdgeDraft() {
  const productId = requiredEnv("EDGE_PRODUCT_ID");
  const clientId = requiredEnv("EDGE_CLIENT_ID");
  const apiKey = requiredEnv("EDGE_API_KEY");
  const zipBytes = await readFile(ZIP_PATH);
  const { response } = await requestJson(`${EDGE_BASE_URL}/${productId}/submissions/draft/package`, {
    method: "POST",
    headers: {
      Authorization: `ApiKey ${apiKey}`,
      "X-ClientID": clientId,
      "Content-Type": "application/zip"
    },
    body: zipBytes
  });
  const operationId = response.headers.get("location") || response.headers.get("Location");
  if (!operationId) {
    throw new Error("Edge upload succeeded but did not return an operation id");
  }
  console.log(JSON.stringify({ store: "edge", action: "draft-upload", operationId }));
  for (let attempt = 1; attempt <= 24; attempt += 1) {
    await new Promise((resolveTimer) => setTimeout(resolveTimer, 5000));
    const { payload } = await requestJson(
      `${EDGE_BASE_URL}/${productId}/submissions/draft/package/operations/${operationId}`,
      { headers: { Authorization: `ApiKey ${apiKey}`, "X-ClientID": clientId } }
    );
    console.log(JSON.stringify({ store: "edge", action: "poll", attempt, status: payload.status, message: payload.message || "" }));
    if (payload.status === "Succeeded") {
      return;
    }
    if (payload.status === "Failed") {
      throw new Error(`Edge draft package failed: ${JSON.stringify(payload)}`);
    }
  }
  throw new Error("Timed out waiting for Edge draft package operation");
}

function usage() {
  const name = basename(process.argv[1]);
  console.error(`Usage: node scripts/${name} <chrome-draft|edge-draft|draft-all>`);
}

if (!existsSync(ZIP_PATH)) {
  throw new Error(`Missing ${ZIP_PATH}; run npm run package:webstore first`);
}

const command = process.argv[2];
if (command === "chrome-draft") {
  await uploadChromeDraft();
} else if (command === "edge-draft") {
  await uploadEdgeDraft();
} else if (command === "draft-all") {
  await uploadChromeDraft();
  await uploadEdgeDraft();
} else {
  usage();
  process.exit(64);
}
