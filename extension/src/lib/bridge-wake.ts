interface RuntimeMessengerLike {
  sendMessage(message: unknown): Promise<unknown>;
}

const BRIDGE_SUPPORTED_URL_PATTERNS = [
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

export function isBridgeSupportedPage(url: string) {
  const normalized = String(url || "").trim().toLowerCase();
  return BRIDGE_SUPPORTED_URL_PATTERNS.some((pattern) => normalized.includes(pattern));
}

export function announceBridgePageReady(
  runtime: RuntimeMessengerLike | undefined,
  url: string
) {
  if (!runtime?.sendMessage || !url || !isBridgeSupportedPage(url)) {
    return;
  }

  void runtime.sendMessage({
    type: "mdtero.bridge.page_ready",
    url
  }).catch(() => {
  });
}
