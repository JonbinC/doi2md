import type { ParserV2ShadowDiagnostics } from "./api-contract";

export type ShadowStatusLanguage = "en" | "zh";

const CONNECTOR_LABELS: Record<string, { en: string; zh: string }> = {
  springer_subscription_connector: {
    en: "Springer subscription",
    zh: "Springer 订阅链路"
  },
  wiley_tdm: {
    en: "Wiley TDM",
    zh: "Wiley TDM"
  },
  taylor_francis_tdm: {
    en: "Taylor & Francis TDM",
    zh: "Taylor & Francis TDM"
  },
  springer_openaccess_api: {
    en: "Springer OA",
    zh: "Springer OA"
  },
  elsevier_article_retrieval_api: {
    en: "Elsevier API",
    zh: "Elsevier API"
  }
};

function connectorLabel(connector: string, language: ShadowStatusLanguage): string {
  return CONNECTOR_LABELS[connector]?.[language] ?? connector;
}

export function summarizeParserV2ShadowDiagnostics(
  diagnostics: ParserV2ShadowDiagnostics,
  language: ShadowStatusLanguage,
  maxVisible = 2
): string {
  const enabled = (diagnostics.connectors || []).filter((item) => item.enabled);
  if (enabled.length === 0) {
    return language === "zh"
      ? "当前还没有启用任何实验 connector shadow。"
      : "No experimental connector shadows are enabled yet.";
  }

  const visible = enabled.slice(0, maxVisible).map((item) => connectorLabel(item.connector, language));
  const remaining = enabled.length - visible.length;
  const visibleText = visible.join(language === "zh" ? "、" : ", ");

  if (language === "zh") {
    return remaining > 0
      ? `当前已启用 ${enabled.length} 条实验 shadow：${visibleText}，另有 ${remaining} 条。`
      : `当前已启用 ${enabled.length} 条实验 shadow：${visibleText}。`;
  }

  return remaining > 0
    ? `${enabled.length} experimental shadows enabled: ${visibleText}, plus ${remaining} more.`
    : `${enabled.length} experimental shadows enabled: ${visibleText}.`;
}
