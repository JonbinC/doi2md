export function createParseMessage(input: string, elsevierApiKey?: string) {
  return {
    type: "mdtero.parse.request" as const,
    input,
    elsevierApiKey
  };
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
