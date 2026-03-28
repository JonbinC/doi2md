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
  return {
    xmlBlob: new Blob([xmlBytes], { type: "application/xml" }),
    sourceDoi: identifier.kind === "doi" ? identifier.value : undefined,
    sourceInput: input,
    filename: "paper.xml",
    bundleExtraFiles: {}
  };
}
