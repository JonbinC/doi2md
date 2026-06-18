const DOI_PATTERN = /10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i;
const ARXIV_PATTERN = /arxiv\.org\/(abs|pdf|html)\/([a-z\-]+\/\d{7}|[0-9]{4}\.[0-9]{4,5})(?:\.pdf)?/i;

function matchMetaContent(html: string, metaNames: string[]): string | null {
  for (const metaName of metaNames) {
    const escaped = metaName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const patterns = [
      new RegExp(`<meta[^>]+name=["']${escaped}["'][^>]+content=["']([^"']+)["']`, "i"),
      new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+name=["']${escaped}["']`, "i"),
      new RegExp(`<meta[^>]+property=["']${escaped}["'][^>]+content=["']([^"']+)["']`, "i"),
      new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+property=["']${escaped}["']`, "i")
    ];
    for (const pattern of patterns) {
      const match = html.match(pattern);
      if (match?.[1]) {
        return match[1];
      }
    }
  }
  return null;
}

export type DetectedPaperInput =
  | { kind: "doi"; value: string }
  | { kind: "sciencedirect"; value: string }
  | { kind: "arxiv"; value: string }
  | { kind: "ieee"; value: string }
  | { kind: "cnki"; value: string };

export function detectPaperInput(input: {
  url: string;
  html: string;
}): DetectedPaperInput | null {
  const arxivMatch = input.url.match(ARXIV_PATTERN);
  if (arxivMatch) {
    return { kind: "arxiv", value: input.url };
  }

  const urlMatch = input.url.match(DOI_PATTERN);
  if (urlMatch) {
    return { kind: "doi", value: urlMatch[0] };
  }

  const metaDoi = matchMetaContent(input.html, ["citation_doi", "prism.doi", "dc.identifier"]);
  if (metaDoi && DOI_PATTERN.test(metaDoi)) {
    const match = metaDoi.match(DOI_PATTERN);
    if (match) {
      return { kind: "doi", value: match[0] };
    }
  }

  if (input.url.includes("sciencedirect.com/science/article/pii/")) {
    return { kind: "sciencedirect", value: input.url };
  }

  if (isIeeeArticlePage(input.url)) {
    return { kind: "ieee", value: input.url };
  }

  if (isCnkiArticlePage(input.url)) {
    return { kind: "cnki", value: input.url };
  }

  const htmlMatch = input.html.match(DOI_PATTERN);
  if (htmlMatch) {
    return { kind: "doi", value: htmlMatch[0] };
  }

  return null;
}

function isCnkiArticlePage(url: string): boolean {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.hostname.endsWith("cnki.net") && /\/kcms2\/article\/(?:abstract|detail)/i.test(parsed.pathname);
  } catch {
    return false;
  }
}

function isIeeeArticlePage(url: string): boolean {
  try {
    const parsed = new URL(String(url || ""));
    return parsed.hostname.endsWith("ieeexplore.ieee.org") && /\/(?:abstract\/)?document\/\d+|\/stamp\/(?:stamp\.jsp)|\/stampPDF\/getPDF\.jsp/i.test(parsed.pathname);
  } catch {
    return false;
  }
}
