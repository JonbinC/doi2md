const encoder = new TextEncoder();

type ArtifactKind = "html" | "structured_xml" | "jats_xml" | "elsevier_xml" | "epub" | "pdf";
type AccessKind = "open" | "licensed" | "unknown";

interface BuildHelperBundleBlobOptions {
  connector: string;
  artifactKind: ArtifactKind;
  payload: string | Uint8Array | ArrayBuffer;
  payloadName: string;
  extraFiles?: Record<string, string | Uint8Array | ArrayBuffer>;
  sourceDoi?: string;
  sourceUrl?: string;
  sourceId?: string;
  sourceType?: string;
  access?: AccessKind;
  licenseName?: string;
  acquisitionMode?: string;
  userPrivateRetention?: boolean;
}

interface ZipEntry {
  name: string;
  bytes: Uint8Array;
}

const CONNECTOR_PRESETS: Record<string, { access: AccessKind; sourceName: string; userPrivateRetention?: boolean }> = {
  local_file_upload: {
    access: "unknown",
    sourceName: "local_file_upload",
    userPrivateRetention: true
  },
  elsevier_article_retrieval_api: {
    access: "licensed",
    sourceName: "elsevier_article_retrieval_api",
    userPrivateRetention: true
  },
  wiley_tdm: {
    access: "licensed",
    sourceName: "wiley_tdm",
    userPrivateRetention: true
  },
  springer_subscription_connector: {
    access: "licensed",
    sourceName: "springer_subscription_connector",
    userPrivateRetention: true
  },
  taylor_francis_tdm: {
    access: "licensed",
    sourceName: "taylor_francis_tdm",
    userPrivateRetention: true
  },
  taylor_francis_oa_epub: {
    access: "open",
    sourceName: "taylor_francis_oa_epub"
  },
  arxiv_native: {
    access: "open",
    sourceName: "arxiv_native"
  }
};

export function buildHelperBundleBlob(options: BuildHelperBundleBlobOptions): Blob {
  const payloadBytes = toUint8Array(options.payload);
  const extraFiles = Object.entries(options.extraFiles || {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, payload]) => ({
      name,
      bytes: toUint8Array(payload)
    }));
  const manifest = {
    connector: options.connector,
    artifact_kind: options.artifactKind,
    acquisition_mode: options.acquisitionMode || "browser_extension",
    source_name: CONNECTOR_PRESETS[options.connector]?.sourceName || options.connector,
    source_type: options.sourceType || defaultSourceType(options.artifactKind),
    source_id: options.sourceId || null,
    source_url: options.sourceUrl || null,
    source_doi: options.sourceDoi || null,
    license_name: options.licenseName || null,
    rights_confidence: "high",
    access: options.access || CONNECTOR_PRESETS[options.connector]?.access || "unknown",
    explicit_open_license: false,
    user_private_retention: Boolean(
      options.userPrivateRetention ?? CONNECTOR_PRESETS[options.connector]?.userPrivateRetention ?? false
    ),
    payload_name: options.payloadName,
    extra_files: extraFiles.map((entry) => entry.name)
  };

  const archive = buildStoredZip([
    {
      name: "manifest.json",
      bytes: encoder.encode(JSON.stringify(manifest))
    },
    {
      name: options.payloadName,
      bytes: payloadBytes
    },
    ...extraFiles
  ]);

  return new Blob([archive], { type: "application/zip" });
}

export function inferBrowserHelperBundleConnector(input: string, pageUrl?: string): string {
  const haystack = `${String(input || "").toLowerCase()} ${String(pageUrl || "").toLowerCase()}`;
  if (haystack.includes("arxiv.org") || haystack.includes("arxiv:")) {
    return "arxiv_native";
  }
  if (haystack.includes("link.springer.com") || haystack.includes("springernature.com") || haystack.includes("springer.com")) {
    return "springer_subscription_connector";
  }
  if (haystack.includes("onlinelibrary.wiley.com") || haystack.includes("10.1002/")) {
    return "wiley_tdm";
  }
  if (haystack.includes("tandfonline.com") || haystack.includes("10.1080/")) {
    return "taylor_francis_tdm";
  }
  if (haystack.includes("sciencedirect.com") || haystack.includes("elsevier.com") || haystack.includes("10.1016/")) {
    return "elsevier_article_retrieval_api";
  }
  return "browser_extension_html_capture";
}

export function inferBrowserHelperBundleAccess(connector: string): AccessKind {
  return CONNECTOR_PRESETS[connector]?.access || "unknown";
}

function defaultSourceType(artifactKind: ArtifactKind): string {
  if (artifactKind === "html") {
    return "browser_extension_html";
  }
  if (artifactKind === "epub") {
    return "browser_extension_epub";
  }
  if (artifactKind === "pdf") {
    return "browser_extension_pdf";
  }
  if (artifactKind === "jats_xml") {
    return "browser_extension_jats";
  }
  return "browser_extension_xml";
}

function toUint8Array(payload: string | Uint8Array | ArrayBuffer): Uint8Array {
  if (typeof payload === "string") {
    return encoder.encode(payload);
  }
  if (payload instanceof Uint8Array) {
    return payload;
  }
  return new Uint8Array(payload);
}

function buildStoredZip(entries: ZipEntry[]): Uint8Array {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  for (const entry of entries) {
    const nameBytes = encoder.encode(entry.name);
    const crc = crc32(entry.bytes);
    const localHeader = new Uint8Array(30 + nameBytes.length);
    const localView = new DataView(localHeader.buffer);
    localView.setUint32(0, 0x04034b50, true);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0, true);
    localView.setUint16(8, 0, true);
    localView.setUint16(10, 0, true);
    localView.setUint16(12, 0, true);
    localView.setUint32(14, crc, true);
    localView.setUint32(18, entry.bytes.length, true);
    localView.setUint32(22, entry.bytes.length, true);
    localView.setUint16(26, nameBytes.length, true);
    localView.setUint16(28, 0, true);
    localHeader.set(nameBytes, 30);
    localParts.push(localHeader, entry.bytes);

    const centralHeader = new Uint8Array(46 + nameBytes.length);
    const centralView = new DataView(centralHeader.buffer);
    centralView.setUint32(0, 0x02014b50, true);
    centralView.setUint16(4, 20, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0, true);
    centralView.setUint16(10, 0, true);
    centralView.setUint16(12, 0, true);
    centralView.setUint16(14, 0, true);
    centralView.setUint32(16, crc, true);
    centralView.setUint32(20, entry.bytes.length, true);
    centralView.setUint32(24, entry.bytes.length, true);
    centralView.setUint16(28, nameBytes.length, true);
    centralView.setUint16(30, 0, true);
    centralView.setUint16(32, 0, true);
    centralView.setUint16(34, 0, true);
    centralView.setUint16(36, 0, true);
    centralView.setUint32(38, 0, true);
    centralView.setUint32(42, offset, true);
    centralHeader.set(nameBytes, 46);
    centralParts.push(centralHeader);

    offset += localHeader.length + entry.bytes.length;
  }

  const centralDirectoryOffset = offset;
  let centralDirectorySize = 0;
  for (const part of centralParts) {
    centralDirectorySize += part.length;
  }

  const endRecord = new Uint8Array(22);
  const endView = new DataView(endRecord.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(4, 0, true);
  endView.setUint16(6, 0, true);
  endView.setUint16(8, entries.length, true);
  endView.setUint16(10, entries.length, true);
  endView.setUint32(12, centralDirectorySize, true);
  endView.setUint32(16, centralDirectoryOffset, true);
  endView.setUint16(20, 0, true);

  const totalLength =
    localParts.reduce((sum, part) => sum + part.length, 0) +
    centralDirectorySize +
    endRecord.length;
  const archive = new Uint8Array(totalLength);
  let cursor = 0;
  for (const part of localParts) {
    archive.set(part, cursor);
    cursor += part.length;
  }
  for (const part of centralParts) {
    archive.set(part, cursor);
    cursor += part.length;
  }
  archive.set(endRecord, cursor);
  return archive;
}

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) === 1 ? (0xedb88320 ^ (value >>> 1)) >>> 0 : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let value = 0xffffffff;
  for (const item of bytes) {
    value = CRC32_TABLE[(value ^ item) & 0xff] ^ (value >>> 8);
  }
  return (value ^ 0xffffffff) >>> 0;
}
