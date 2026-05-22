const DOI_PATTERN = /(10\.\d{4,9}\/[-._;()/:A-Z0-9]+)/i;
const DOI_URL_PATTERN = /^https?:\/\/(?:dx\.)?doi\.org\/(10\.\d{4,9}\/.+)$/i;
const SPRINGER_HOST_PATTERN = /(link\.springer\.com|springer\.com|springernature\.com)/i;

export function normalizeSpringerInput(input: string, pageUrl?: string): string | null {
  const trimmed = String(input || "").trim();
  const doiUrlMatch = trimmed.match(DOI_URL_PATTERN);
  if (doiUrlMatch) {
    return doiUrlMatch[1];
  }

  if (SPRINGER_HOST_PATTERN.test(trimmed)) {
    const doiMatch = trimmed.match(DOI_PATTERN);
    if (doiMatch) {
      return doiMatch[1];
    }
  }

  if (/^10\.1007\//i.test(trimmed)) {
    return trimmed;
  }

  if (SPRINGER_HOST_PATTERN.test(String(pageUrl || ""))) {
    const doiMatch = trimmed.match(DOI_PATTERN);
    if (doiMatch) {
      return doiMatch[1];
    }
  }

  return null;
}
