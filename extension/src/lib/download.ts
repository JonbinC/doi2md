export interface BlobDownloadDeps {
  createObjectURL(blob: Blob): string;
  revokeObjectURL(url: string): void;
  createAnchor(): {
    href: string;
    download: string;
    click(): void;
    remove?: () => void;
  };
}

const defaultDeps: BlobDownloadDeps = {
  createObjectURL(blob) {
    return URL.createObjectURL(blob);
  },
  revokeObjectURL(url) {
    URL.revokeObjectURL(url);
  },
  createAnchor() {
    return document.createElement("a");
  }
};

export function triggerBlobDownload(
  blob: Blob,
  filename: string,
  deps: BlobDownloadDeps = defaultDeps
) {
  const objectUrl = deps.createObjectURL(blob);
  try {
    const anchor = deps.createAnchor();
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
    anchor.remove?.();
  } finally {
    deps.revokeObjectURL(objectUrl);
  }
}
