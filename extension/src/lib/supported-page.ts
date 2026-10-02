const SUPPORTED_PAPER_URL_PATTERNS = [
  "arxiv.org",
  "cnki.net",
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
  "tandfonline.com",
  "iopscience.iop.org",
  "academic.oup.com",
  "science.org",
  "cell.com",
  "pnas.org",
  "frontiersin.org",
  "journals.plos.org",
  "journals.sagepub.com",
  "cambridge.org",
  "pubs.aip.org",
  "journals.aps.org",
  "biorxiv.org",
  "medrxiv.org",
  "chemrxiv.org",
  "pmc.ncbi.nlm.nih.gov"
];

export function isSupportedPaperPage(url: string) {
  const normalized = String(url || "").trim().toLowerCase();
  return SUPPORTED_PAPER_URL_PATTERNS.some((pattern) => normalized.includes(pattern));
}
