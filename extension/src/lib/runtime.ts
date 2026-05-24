export interface ParsePageContext {
  tabId: number;
  tabUrl?: string;
}

export type LocalFileArtifactKind = "pdf" | "epub";

export function createSsotParseMessage(input: string, pageContext?: ParsePageContext) {
  const message: {
    type: "mdtero.parse.ssot.request";
    input: string;
    pageContext?: ParsePageContext;
  } = {
    type: "mdtero.parse.ssot.request" as const,
    input
  };
  if (pageContext) {
    message.pageContext = pageContext;
  }
  return message;
}

export function createFileParseMessage(
  file: File,
  artifactKind: LocalFileArtifactKind
) {
  const message: {
    type: "mdtero.parse.file.request";
    file: File;
    filename: string;
    mediaType: string;
    artifactKind: LocalFileArtifactKind;
  } = {
    type: "mdtero.parse.file.request" as const,
    file,
    filename: file.name,
    mediaType: file.type,
    artifactKind
  };

  return message;
}

export function createTranslateMessage(
  sourceMarkdownPath: string,
  targetLanguage: string,
  mode: string
) {
  return {
    type: "mdtero.translate.request" as const,
    sourceMarkdownPath,
    targetLanguage,
    mode
  };
}

export function createDetectMessage() {
  return {
    type: "mdtero.detect.request" as const
  };
}
