export interface ParsePageContext {
  tabId: number;
  tabUrl?: string;
}

export type LocalFileArtifactKind = "pdf" | "epub";

export function createParseMessage(input: string, elsevierApiKey?: string, pageContext?: ParsePageContext) {
  const message: {
    type: "mdtero.parse.request";
    input: string;
    elsevierApiKey?: string;
    pageContext?: ParsePageContext;
  } = {
    type: "mdtero.parse.request" as const,
    input
  };
  if (elsevierApiKey) {
    message.elsevierApiKey = elsevierApiKey;
  }
  if (pageContext) {
    message.pageContext = pageContext;
  }
  return message;
}

export function createFileParseMessage(
  file: File,
  artifactKind: LocalFileArtifactKind,
  pdfEngine?: "grobid" | "docling" | "mineru"
) {
  const message: {
    type: "mdtero.parse.file.request";
    file: File;
    filename: string;
    mediaType: string;
    artifactKind: LocalFileArtifactKind;
    pdfEngine?: "grobid" | "docling" | "mineru";
  } = {
    type: "mdtero.parse.file.request" as const,
    file,
    filename: file.name,
    mediaType: file.type,
    artifactKind
  };

  if (artifactKind === "pdf" && pdfEngine) {
    message.pdfEngine = pdfEngine;
  }

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
