const SUPPORTED_PAPER_URL_PATTERNS = [
  "arxiv.org",
  "dl.acm.org",
  "ieeexplore.ieee.org",
  "nature.com",
  "pubs.acs.org",
  "pubs.rsc.org",
  "sciencedirect.com/science/article/pii/",
  "techrxiv.org",
  "link.springer.com",
  "mdpi.com",
  "springer.com",
  "springernature.com",
  "onlinelibrary.wiley.com",
  "tandfonline.com"
];

export function isSupportedPaperPage(url: string) {
  const normalized = String(url || "").trim().toLowerCase();
  return SUPPORTED_PAPER_URL_PATTERNS.some((pattern) => normalized.includes(pattern));
}
