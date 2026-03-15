const DOI_PATTERN = /10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i;

export type DetectedPaperInput =
  | { kind: "doi"; value: string }
  | { kind: "sciencedirect"; value: string };

export function detectPaperInput(input: {
  url: string;
  html: string;
}): DetectedPaperInput | null {
  const urlMatch = input.url.match(DOI_PATTERN);
  if (urlMatch) {
    return { kind: "doi", value: urlMatch[0] };
  }

  const metaDoiMatch = input.html.match(/citation_doi"\s+content="([^"]+)"/i);
  if (metaDoiMatch) {
    return { kind: "doi", value: metaDoiMatch[1] };
  }

  if (input.url.includes("sciencedirect.com/science/article/pii/")) {
    return { kind: "sciencedirect", value: input.url };
  }

  const htmlMatch = input.html.match(DOI_PATTERN);
  if (htmlMatch) {
    return { kind: "doi", value: htmlMatch[0] };
  }

  return null;
}
