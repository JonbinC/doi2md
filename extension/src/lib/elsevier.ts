const LOCAL_XML_DOI_PREFIXES = ["10.1016/"];
const DOI_URL_PATTERN = /^https?:\/\/(?:dx\.)?doi\.org\/(10\.\d{4,9}\/.+)$/i;
const PII_PATTERN = /^S[0-9A-Z]{16,}$/i;
const SCIENCEDIRECT_PII_PATTERN = /sciencedirect\.com\/science\/article\/pii\/(S[0-9A-Z]{16,})/i;

export type ElsevierIdentifier =
  | { kind: "doi"; value: string }
  | { kind: "pii"; value: string };

function usesLocalXmlAcquire(doi: string): boolean {
  const lowered = doi.toLowerCase();
  return LOCAL_XML_DOI_PREFIXES.some((prefix) => lowered.startsWith(prefix));
}

export function normalizeElsevierInput(input: string): ElsevierIdentifier | null {
  const trimmed = input.trim();
  const doiUrlMatch = trimmed.match(DOI_URL_PATTERN);
  if (doiUrlMatch && usesLocalXmlAcquire(doiUrlMatch[1])) {
    return { kind: "doi", value: doiUrlMatch[1] };
  }
  if (usesLocalXmlAcquire(trimmed)) {
    return { kind: "doi", value: trimmed };
  }
  const piiUrlMatch = trimmed.match(SCIENCEDIRECT_PII_PATTERN);
  if (piiUrlMatch) {
    return { kind: "pii", value: piiUrlMatch[1] };
  }
  if (PII_PATTERN.test(trimmed)) {
    return { kind: "pii", value: trimmed };
  }
  return null;
}

export function requiresElsevierLocalAcquire(input: string): boolean {
  return normalizeElsevierInput(input) !== null;
}

export function buildElsevierLocalAcquireGuidance(): string {
  return [
    "This Elsevier or ScienceDirect paper needs local acquisition in your browser first.",
    "Add your Elsevier API key in Mdtero extension settings, then retry.",
    "If Elsevier only returns the abstract, check whether this machine is on a campus or institutional network IP."
  ].join(" ");
}

export async function fetchElsevierXml(input: string, apiKey: string) {
  const identifier = normalizeElsevierInput(input);
  if (!identifier) {
    throw new Error("Input is not recognized as an Elsevier DOI or ScienceDirect article.");
  }

  const endpointBase =
    identifier.kind === "doi"
      ? `https://api.elsevier.com/content/article/doi/${identifier.value}`
      : `https://api.elsevier.com/content/article/pii/${identifier.value}`;

  const response = await fetch(
    `${endpointBase}?APIKey=${encodeURIComponent(apiKey)}&httpAccept=text/xml`
  );

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error("Elsevier API request failed. Please verify your Elsevier API key and network entitlement.");
    }
    throw new Error(`Elsevier XML fetch failed: ${response.status}`);
  }

  const xmlBytes = new Uint8Array(await response.arrayBuffer());
  const xmlText = new TextDecoder().decode(xmlBytes);

  return {
    xmlBlob: new Blob([xmlBytes], { type: "application/xml" }),
    sourceDoi: identifier.kind === "doi" ? identifier.value : undefined,
    sourceInput: input,
    filename: "paper.xml",
    bundleExtraFiles: await collectElsevierImageAssetFiles(xmlText)
  };
}

export async function collectElsevierImageAssetFiles(xmlText: string): Promise<Record<string, Uint8Array>> {
  const pii = extractElsevierPii(xmlText);
  if (!pii) {
    return {};
  }

  const eid = `1-s2.0-${pii}`;
  const objectMap = extractElsevierObjectMap(xmlText);
  const figureRefs = extractElsevierFigureRefs(xmlText);
  const assetFiles: Record<string, Uint8Array> = {};

  for (const grRef of figureRefs) {
    const assetUrl = normalizeElsevierFigureAssetUrl(objectMap.get(grRef), eid, grRef);
    if (!assetUrl) {
      continue;
    }
    try {
      const assetResponse = await fetch(assetUrl);
      if (!assetResponse.ok) {
        continue;
      }
      const contentType = String(assetResponse.headers.get("content-type") || "").toLowerCase();
      if (!contentType.startsWith("image/")) {
        continue;
      }
      const assetBytes = new Uint8Array(await assetResponse.arrayBuffer());
      if (assetBytes.length === 0) {
        continue;
      }
      const filename = assetUrl.split("/").pop()?.split("?")[0]?.trim();
      if (!filename) {
        continue;
      }
      assetFiles[`paper_files/${filename}`] = assetBytes;
    } catch {
      continue;
    }
  }

  return assetFiles;
}

function extractElsevierPii(xmlText: string): string | null {
  const pii =
    xmlText.match(/<[^>]*pii[^>]*>\s*([^<\s]+)\s*<\/[^>]*pii[^>]*>/i)?.[1] ||
    xmlText.match(/<[^>]*identifier[^>]*>\s*PII:([^<\s]+)\s*<\/[^>]*identifier[^>]*>/i)?.[1] ||
    xmlText.match(/\bPII:([A-Z0-9]+)\b/i)?.[1];

  const cleaned = String(pii || "").trim().replace(/[^0-9A-Z]/gi, "");
  return cleaned || null;
}

function extractElsevierObjectMap(xmlText: string): Map<string, string> {
  const objectMap = new Map<string, string>();
  const pattern = /<[^>]*object\b[^>]*\bref="([^"]+)"[^>]*>([\s\S]*?)<\/[^>]*object>/gi;
  for (const match of xmlText.matchAll(pattern)) {
    const ref = String(match[1] || "").trim();
    const rawUrl = String(match[2] || "").trim();
    if (ref && rawUrl && !objectMap.has(ref)) {
      objectMap.set(ref, rawUrl);
    }
  }
  return objectMap;
}

function extractElsevierFigureRefs(xmlText: string): string[] {
  const refs: string[] = [];
  const seen = new Set<string>();
  const locatorPattern = /<[^>]*link\b[^>]*\blocator="([^"]+)"[^>]*\/?>/gi;
  for (const match of xmlText.matchAll(locatorPattern)) {
    const ref = String(match[1] || "").trim();
    if (ref && !seen.has(ref)) {
      seen.add(ref);
      refs.push(ref);
    }
  }

  const hrefPattern = /<[^>]*link\b[^>]*\bhref="([^"]+\/((?:gr|graphic)\d+))"[^>]*\/?>/gi;
  for (const match of xmlText.matchAll(hrefPattern)) {
    const ref = String(match[2] || "").trim();
    if (ref && !seen.has(ref)) {
      seen.add(ref);
      refs.push(ref);
    }
  }

  return refs;
}

function normalizeElsevierFigureAssetUrl(rawUrl: string | undefined, eid: string, grRef: string): string | null {
  const clean = String(rawUrl || "").trim();
  if (clean) {
    if (clean.includes("api.elsevier.com/content/article/") && clean.includes("/ref/")) {
      const assetName = clean.split("/ref/").pop()?.split("?")[0]?.trim();
      if (assetName) {
        const suffix = assetName.includes(".") ? assetName : `${assetName}.jpg`;
        return `https://ars.els-cdn.com/content/image/${eid}-${suffix}`;
      }
    }
    if (clean.includes("api.elsevier.com/content/object/eid/")) {
      const assetName = clean.split("/eid/").pop()?.split("?")[0]?.trim();
      if (assetName) {
        return `https://ars.els-cdn.com/content/image/${assetName}`;
      }
    }
    if (clean.includes("ars.els-cdn.com/content/image/")) {
      return clean;
    }
  }
  if (!eid || !grRef) {
    return null;
  }
  return `https://ars.els-cdn.com/content/image/${eid}-${grRef}.jpg`;
}
