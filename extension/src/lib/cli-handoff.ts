export function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_/:.=?&%+@,;#~-]+$/.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}

export function normalizeCliHandoffCommand(command?: string | null): string {
  const trimmed = String(command || "").trim();
  if (!trimmed || !/^mdtero\s+parse\b/.test(trimmed)) {
    return trimmed;
  }
  const isFileParse = /^mdtero\s+parse\s+--file\b/.test(trimmed);
  const timeout = isFileParse ? 600 : 300;
  const withoutTraceOnly = trimmed.replace(/\s+--trace(?!\S)/g, "");
  const withoutJson = withoutTraceOnly.replace(/\s+--json(?!\S)/g, "");
  const withoutTimeout = withoutJson.replace(/\s+--timeout\s+\S+/g, "").replace(/\s+--interval\s+\S+/g, "");
  const withoutWait = withoutTimeout.replace(/\s+--wait(?!\S)/g, "");
  return `${withoutWait} --trace --wait --timeout ${timeout} --json`;
}

export function buildCliParseCommand(input?: string | null): string {
  const normalized = String(input || "").trim();
  if (!normalized) {
    return "";
  }
  if (!/^https?:\/\//i.test(normalized) && !/^10\.\S+/i.test(normalized)) {
    return "";
  }
  return `mdtero parse ${shellQuote(normalized)} --trace --wait --timeout 300 --json`;
}

export function buildCliFileParseCommand(
  filename?: string | null,
  artifactKind?: "pdf" | "epub" | "html" | "xml" | null
): string {
  const normalized = String(filename || "").trim();
  const extension = inferFileExtension(normalized, artifactKind);
  const path = normalized || `paper.${extension}`;
  return `mdtero parse --file ${shellQuote(path)} --trace --wait --timeout 600 --json`;
}

function inferFileExtension(
  filename?: string | null,
  artifactKind?: "pdf" | "epub" | "html" | "xml" | null
): "pdf" | "epub" | "html" | "xml" {
  const normalized = String(filename || "").trim().toLowerCase();
  if (normalized.endsWith(".epub") || artifactKind === "epub") {
    return "epub";
  }
  if (normalized.endsWith(".html") || normalized.endsWith(".htm") || artifactKind === "html") {
    return "html";
  }
  if (normalized.endsWith(".xml") || artifactKind === "xml") {
    return "xml";
  }
  return "pdf";
}
