import type { LocalFileArtifactKind } from "./runtime";

interface ParseClientLike {
  createUploadedParseTask(payload: {
    paperFile: Blob;
    filename?: string;
    sourceInput?: string;
    artifactKind?: LocalFileArtifactKind;
  }): Promise<unknown>;
}

interface BrowserFileMessage {
  file: Blob;
  filename?: string;
  artifactKind?: LocalFileArtifactKind;
}

export async function runBrowserFileParseRequest(
  client: ParseClientLike,
  message: BrowserFileMessage,
): Promise<unknown> {
  const filename = String(message.filename || "").trim() || "paper.bin";
  return client.createUploadedParseTask({
    paperFile: message.file,
    filename,
    sourceInput: filename,
    artifactKind: message.artifactKind,
  });
}
