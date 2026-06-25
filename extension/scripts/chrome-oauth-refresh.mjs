import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";

const REDIRECT_URI = process.env.CHROME_OAUTH_REDIRECT_URI ?? "http://localhost:8765";
const PORT = Number(new URL(REDIRECT_URI).port || 80);
const HOST = new URL(REDIRECT_URI).hostname;
const SCOPE = "https://www.googleapis.com/auth/chromewebstore";
const TOKEN_URL = "https://oauth2.googleapis.com/token";

async function loadStoreEnv() {
  if (process.env.CHROME_WEBSTORE_CLIENT_ID && process.env.CHROME_WEBSTORE_CLIENT_SECRET) {
    return {
      clientId: process.env.CHROME_WEBSTORE_CLIENT_ID,
      clientSecret: process.env.CHROME_WEBSTORE_CLIENT_SECRET
    };
  }

  const tokenFile = process.env.INFISICAL_TOKEN_FILE ?? "/home/ubuntu/infisical/.admin_jwt";
  const adminToken = process.env.INFISICAL_TOKEN ?? (await readFile(tokenFile, "utf8")).trim();
  const projectId = process.env.MDTERO_EXTENSION_STORE_INFISICAL_PROJECT_ID ?? "df34fed4-1403-4a12-bcde-dbc59caf6d1b";
  const result = spawnSync(
    "sudo",
    [
      "docker",
      "exec",
      "-e",
      `INFISICAL_TOKEN=${adminToken}`,
      "infisical",
      "bash",
      "-lc",
      `tmp=$(mktemp); infisical export --token="$INFISICAL_TOKEN" --domain=http://127.0.0.1:8080 --projectId=${projectId} --env=prod --path=/extension-store --format=dotenv --silent --output-file="$tmp" >/dev/null; cat "$tmp"`
    ],
    { encoding: "utf8" }
  );
  if (result.status !== 0) {
    throw new Error(result.stderr || "Infisical export failed");
  }

  const env = {};
  for (const line of result.stdout.split("\n")) {
    const match = line.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/);
    if (!match) continue;
    env[match[1]] = match[2].replace(/^['"]|['"]$/g, "");
  }
  return {
    clientId: env.CHROME_WEBSTORE_CLIENT_ID || (() => { throw new Error("CHROME_WEBSTORE_CLIENT_ID missing"); })(),
    clientSecret: env.CHROME_WEBSTORE_CLIENT_SECRET || (() => { throw new Error("CHROME_WEBSTORE_CLIENT_SECRET missing"); })()
  };
}

function buildAuthUrl(clientId) {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: REDIRECT_URI,
    scope: SCOPE,
    access_type: "offline",
    prompt: "consent"
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
}

async function exchangeCode(clientId, clientSecret, code) {
  const body = new URLSearchParams({
    client_id: clientId,
    client_secret: clientSecret,
    code,
    grant_type: "authorization_code",
    redirect_uri: REDIRECT_URI
  });
  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Token exchange failed: ${JSON.stringify(payload)}`);
  }
  if (!payload.refresh_token) {
    throw new Error(`No refresh_token in response: ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function persistRefreshToken(refreshToken) {
  const tokenPath = process.env.CHROME_WEBSTORE_TOKEN_FILE ?? "/home/ubuntu/.config/mdtero/chrome-webstore-token.json";
  const existing = JSON.parse(await readFile(tokenPath, "utf8").catch(() => "{}"));
  const updated = { ...existing, refresh_token: refreshToken };
  await writeFile(tokenPath, `${JSON.stringify(updated, null, 2)}\n`, { mode: 0o600 });

  const adminToken = process.env.INFISICAL_TOKEN ?? (await readFile(process.env.INFISICAL_TOKEN_FILE ?? "/home/ubuntu/infisical/.admin_jwt", "utf8")).trim();
  const projectId = process.env.MDTERO_EXTENSION_STORE_INFISICAL_PROJECT_ID ?? "df34fed4-1403-4a12-bcde-dbc59caf6d1b";
  const patch = spawnSync(
    "sudo",
    [
      "docker",
      "exec",
      "-e",
      `INFISICAL_TOKEN=${adminToken}`,
      "infisical",
      "bash",
      "-lc",
      `infisical secrets set CHROME_WEBSTORE_REFRESH_TOKEN='${refreshToken.replace(/'/g, `'\"'\"'`)}' --token=\"$INFISICAL_TOKEN\" --domain=http://127.0.0.1:8080 --projectId=${projectId} --env=prod --path=/extension-store --silent`
    ],
    { encoding: "utf8" }
  );
  if (patch.status !== 0) {
    console.warn("Saved local token file, but Infisical patch failed:", patch.stderr || patch.stdout);
  }
}

async function waitForCode() {
  if (process.argv[2]) {
    return process.argv[2];
  }

  return await new Promise((resolvePromise, reject) => {
    const server = createServer((req, res) => {
      const url = new URL(req.url ?? "/", REDIRECT_URI);
      const code = url.searchParams.get("code");
      const error = url.searchParams.get("error");
      if (error) {
        res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
        res.end(`OAuth error: ${error}`);
        server.close();
        reject(new Error(error));
        return;
      }
      if (!code) {
        res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("Missing code");
        return;
      }
      res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Chrome Web Store OAuth complete. You can close this tab.");
      server.close();
      resolvePromise(code);
    });

    server.listen(PORT, HOST, () => {
      console.log(`Listening on ${REDIRECT_URI}`);
    });
    server.on("error", reject);
  });
}

const { clientId, clientSecret } = await loadStoreEnv();
const authUrl = buildAuthUrl(clientId);

console.log("Open this URL in your browser and sign in with the Chrome Web Store publisher account:");
console.log(authUrl);
console.log("");
console.log("If you are not on this machine, run first:");
console.log(`  ssh -L ${PORT}:localhost:${PORT} jumbo-sg-arm`);
console.log("");
console.log("After approving, the browser should return here automatically.");
console.log("If the page cannot load, copy the `code` query param from the address bar and run:");
console.log("  node scripts/chrome-oauth-refresh.mjs <code>");

const code = await waitForCode();
const tokenPayload = await exchangeCode(clientId, clientSecret, code);
await persistRefreshToken(tokenPayload.refresh_token);
console.log(JSON.stringify({ status: "ok", saved: true, has_refresh_token: true }));
