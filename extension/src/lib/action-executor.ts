import type {
  ActionContext,
  ActionResult,
  ActionType,
  AcquisitionCandidate,
  ClientHandoffCandidate,
  PublisherCapabilities,
} from "@mdtero/shared";
import { fetchXmlArtifact, isLikelyChallengeOrLoginShell, isLikelyHtmlDocument } from "./page-capture";
import { buildCliParseCommand } from "./cli-handoff";
import { sendTabMessageWithInjection } from "./tab-messaging";

type RouteAction = ActionType | string;

/**
 * Execute a single action from the sequence
 */
export async function executeAction(
  action: RouteAction,
  context: ActionContext,
  routePlan: {
    top_connector?: string;
    fail_closed?: boolean;
    user_message?: string;
    best_oa_url?: string;
    acquisition_candidates?: AcquisitionCandidate[];
    client_handoff_candidates?: ClientHandoffCandidate[];
    publisher_capabilities?: PublisherCapabilities;
  }
): Promise<ActionResult> {
  switch (action) {
    case "capture_current_tab_html":
      return executeCaptureCurrentTabHtml(context);

    case "native_arxiv_parse":
      return executeNativeArxivParse(context);

    case "fetch_elsevier_xml":
      return executeFetchElsevierXml(context);

    case "fetch_structured_xml":
      return executeFetchStructuredXml(context, routePlan);

    case "fetch_remote_html":
      return executeFetchBrowserSource(context, routePlan);

    case "fetch_epub_asset":
      return executeFetchEpubAsset(context, routePlan);

    case "fetch_oa_repository":
      return executeFetchOaRepository(context, routePlan);

    case "fetch_browser_source":
      return executeFetchBrowserSource(context, routePlan);

    case "fallback_pdf_parse":
      return executeFallbackPdfParse(context, routePlan);

    default:
      return { success: false, error: `Unknown action: ${action}` };
  }
}

async function executeFetchElsevierXml(context: ActionContext): Promise<ActionResult> {
  const apiKey = String(context.elsevierApiKey || "").trim();
  if (!apiKey) {
    return {
      success: false,
      error: "Elsevier API key is not configured in the extension.",
      nextCommand: buildCliParseCommand(context.input),
    };
  }

  const identifier = inferElsevierIdentifier(context.input);
  if (!identifier) {
    return {
      success: false,
      error: "Elsevier extension XML fetch requires a DOI, PII, or ScienceDirect article URL.",
      nextCommand: buildCliParseCommand(context.input),
    };
  }

  const requestUrl = buildElsevierArticleRetrievalUrl(identifier.kind, identifier.value);
  try {
    const response = await fetch(requestUrl, {
      headers: {
        "Accept": "text/xml",
        "X-ELS-APIKey": apiKey,
      },
    });
    if (!response.ok) {
      return {
        success: false,
        error: `Elsevier Article Retrieval API returned ${response.status}.`,
        nextCommand: buildCliParseCommand(context.input),
      };
    }
    const xml = (await response.text()).trim();
    if (!xml || !xml.startsWith("<") || isLikelyHtmlDocument(xml) || isLikelyChallengeOrLoginShell(xml)) {
      return {
        success: false,
        error: "Elsevier Article Retrieval API did not return structured XML.",
        nextCommand: buildCliParseCommand(context.input),
      };
    }
    return {
      success: true,
      rawArtifact: new Blob([xml], { type: "application/xml" }),
      filename: "paper.xml",
      artifactKind: "xml",
      sourceDoi: identifier.kind === "doi" ? identifier.value : undefined,
    };
  } catch (error) {
    return { success: false, error: String(error), nextCommand: buildCliParseCommand(context.input) };
  }
}

async function executeNativeArxivParse(context: ActionContext): Promise<ActionResult> {
  const arxivId = inferArxivId(context.input);
  if (!arxivId) {
    return { success: false, error: "No arXiv identifier found.", nextCommand: buildCliParseCommand(context.input) };
  }
  return downloadPdfFromUrl(buildArxivPdfUrl(arxivId), context, "arxiv.pdf");
}

async function executeFallbackPdfParse(
  context: ActionContext,
  routePlan: {
    top_connector?: string;
    user_message?: string;
    acquisition_candidates?: AcquisitionCandidate[];
    client_handoff_candidates?: ClientHandoffCandidate[];
    publisher_capabilities?: PublisherCapabilities;
  }
): Promise<ActionResult> {
  const candidate = pickPdfHandoffCandidate(routePlan.client_handoff_candidates || []);
  const directPdfUrl = pickPdfCandidateUrls(routePlan).find(Boolean);
  if (directPdfUrl) {
    const directResult = await downloadPdfFromUrl(directPdfUrl, context, "paper.pdf");
    if (directResult.success) {
      return directResult;
    }
  }

  if (!candidate) {
    return {
      success: false,
      requiresUpload: true,
      error: routePlan.user_message || "PDF upload required. Please download and upload the PDF manually.",
      nextCommand: buildCliParseCommand(context.input),
    };
  }

  const requiresBrowser = Boolean(candidate.requires_user_rights) || candidate.transport === "browser_extension";
  if (context.tabId && candidate.artifact_url) {
    try {
      const response = await sendTabMessageWithInjection(context.tabId, {
        type: "mdtero.download_pdf.request",
        artifactUrl: candidate.artifact_url,
      });
      const download = response?.download;
      if (response?.ok && download?.ok && download.payloadBase64) {
        return {
          success: true,
          rawArtifact: new Blob([base64ToBytes(download.payloadBase64)], { type: "application/pdf" }),
          filename: download.payloadName || "paper.pdf",
          artifactKind: "pdf",
          sourceDoi: inferSourceDoi(context.input),
        };
      }
    } catch {
      // Fall through to explicit browser guidance below.
    }
  }

  const sourceLabel = candidate.source || candidate.connector || "publisher PDF candidate";
  const artifactUrl = candidate.artifact_url ? ` Candidate: ${candidate.artifact_url}` : "";
  const reason = candidate.reason || routePlan.user_message || "This PDF candidate should be acquired from the user's browser session.";
  const capability = routePlan.publisher_capabilities?.access_mode
    ? ` Access: ${routePlan.publisher_capabilities.access_mode}.`
    : "";

  return {
    success: false,
    requiresBrowserCapture: requiresBrowser,
    requiresUpload: !requiresBrowser,
    error: `${reason} Source: ${sourceLabel}.${capability}${artifactUrl}`,
    nextCommand: buildCliParseCommand(context.input),
  };
}

async function downloadPdfFromUrl(url: string, context: ActionContext, filename: string): Promise<ActionResult> {
  try {
    const response = await fetch(url, {
      credentials: "include",
      headers: { Accept: "application/pdf" },
    });
    if (!response.ok) {
      return { success: false, error: `PDF fetch failed: ${response.status}`, nextCommand: buildCliParseCommand(context.input) };
    }
    const buffer = await response.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    if (!looksLikePdfBytes(bytes)) {
      return {
        success: false,
        error: "PDF fetch returned a non-PDF response.",
        nextCommand: buildCliParseCommand(context.input),
      };
    }
    return {
      success: true,
      rawArtifact: new Blob([bytes], { type: "application/pdf" }),
      filename,
      artifactKind: "pdf",
      sourceDoi: inferSourceDoi(context.input),
    };
  } catch (error) {
    return { success: false, error: String(error), nextCommand: buildCliParseCommand(context.input) };
  }
}

/**
 * Capture HTML from current tab (extension content script)
 */
async function executeCaptureCurrentTabHtml(context: ActionContext): Promise<ActionResult> {
  if (!context.tabId) {
    return { success: false, error: "No tab ID for current tab capture" };
  }

  try {
    const response = await sendTabMessageWithInjection(context.tabId, {
      type: "mdtero.capture_current_tab.request",
    });

    // Check for XML response first (Springer OA, etc.)
    if (response?.xml?.ok && response.xml.payloadText) {
      return {
        success: true,
        rawArtifact: new Blob([response.xml.payloadText], { type: "application/xml" }),
        filename: response.xml.payloadName || "paper.xml",
        artifactKind: "xml",
        sourceDoi: inferSourceDoi(context.input),
      };
    }

    // Check for HTML capture
    const capture = response?.capture;
    if (!response?.ok) {
      return { success: false, error: "Content script unavailable. Reload the page and try again." };
    }

    if (!capture?.ok || !capture.html) {
      return {
        success: false,
        error: capture?.failureMessage || "Page capture failed",
        nextCommand: buildCliParseCommand(context.input),
      };
    }

    return {
      success: true,
      rawArtifact: new Blob([capture.html], { type: "text/html" }),
      filename: capture.payloadName || "paper.html",
      artifactKind: "html",
      sourceDoi: inferSourceDoi(context.input),
    };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Fetch structured XML from known sources (Europe PMC, Springer OA, etc.)
 */
async function executeFetchStructuredXml(
  context: ActionContext,
  routePlan: {
    top_connector?: string;
    acquisition_candidates?: AcquisitionCandidate[];
  }
): Promise<ActionResult> {
  const candidates = routePlan.acquisition_candidates || [];
  
  // Prioritize XML-capable connectors
  for (const candidate of candidates) {
    if (isStructuredXmlCandidate(candidate)) {
      const candidateUrl = candidate.url;
      if (candidateUrl) {
        try {
          const result = await fetchXmlArtifact([candidateUrl]);
          if (result.ok) {
            return {
              success: true,
              rawArtifact: new Blob([result.payloadText], { type: "application/xml" }),
              filename: result.payloadName,
              artifactKind: "xml",
              sourceDoi: inferSourceDoi(context.input),
            };
          }
        } catch {
          // Continue to next candidate
        }
      }
    }
  }

  return { success: false, error: "No structured XML source available" };
}

async function executeFetchEpubAsset(
  context: ActionContext,
  routePlan: {
    top_connector?: string;
    user_message?: string;
    acquisition_candidates?: AcquisitionCandidate[];
    client_handoff_candidates?: ClientHandoffCandidate[];
  }
): Promise<ActionResult> {
  if (!context.tabId) {
    return {
      success: false,
      error: routePlan.user_message || "Open the article page in the current tab and retry EPUB capture.",
      nextCommand: buildCliParseCommand(context.input),
    };
  }

  const candidate = pickEpubCandidate(routePlan);
  const epubUrl = candidate?.epub_url || pickArtifactHandoffUrl(routePlan.client_handoff_candidates || [], "epub");
  if (!epubUrl) {
    return { success: false, error: "No EPUB acquisition URL available for this route." };
  }

  try {
    const response = await sendTabMessageWithInjection(context.tabId, {
      type: "mdtero.download_epub.request",
      artifactUrl: epubUrl,
    });
    const download = response?.download;
    if (!response?.ok || !download?.ok || !download.payloadBase64) {
      return {
        success: false,
        error: download?.failureMessage || "Browser page context could not download the EPUB artifact.",
        nextCommand: buildCliParseCommand(context.input),
      };
    }

    return {
      success: true,
      rawArtifact: new Blob([base64ToBytes(download.payloadBase64)], { type: "application/epub+zip" }),
      filename: download.payloadName || "paper.epub",
      artifactKind: "epub",
      sourceDoi: inferSourceDoi(context.input),
    };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Fetch from OA repository (Unpaywall best OA URL)
 */
async function executeFetchOaRepository(
  context: ActionContext,
  routePlan: { top_connector?: string; best_oa_url?: string }
): Promise<ActionResult> {
  const oaUrl = routePlan.best_oa_url;
  
  if (!oaUrl) {
    return { success: false, error: "No OA repository URL available" };
  }

  try {
    // Determine content type from URL
    const isPdf = oaUrl.toLowerCase().includes(".pdf") || 
                  oaUrl.includes("/pdf") ||
                  oaUrl.includes("download");

    if (isPdf) {
      return downloadPdfFromUrl(oaUrl, context, "paper.pdf");
    }

    // Try to fetch as HTML
    const response = await fetch(oaUrl, { credentials: "include" });
    if (!response.ok) {
      return { success: false, error: `OA fetch failed: ${response.status}` };
    }

    const html = await response.text();
    return {
      success: true,
      rawArtifact: new Blob([html], { type: "text/html" }),
      filename: "paper.html",
      artifactKind: "html",
      sourceDoi: inferSourceDoi(context.input),
    };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Generic browser source fetch for licensed/subscription content.
 */
async function executeFetchBrowserSource(
  context: ActionContext,
  routePlan: {
    top_connector?: string;
    user_message?: string;
    acquisition_candidates?: AcquisitionCandidate[];
    client_handoff_candidates?: ClientHandoffCandidate[];
  }
): Promise<ActionResult> {
  // This action requires the extension to capture from current tab
  // The user must have the article open in their browser
  if (!context.tabId) {
    return {
      success: false,
      requiresUpload: true,
      error: "This source requires browser capture. Open the article page and retry.",
      nextCommand: buildCliParseCommand(context.input),
    };
  }

  const htmlCandidateUrls = pickHtmlCandidateUrls(routePlan);
  if (htmlCandidateUrls.length > 0) {
    try {
      const response = await sendTabMessageWithInjection(context.tabId, {
        type: "mdtero.fetch_html.request",
        candidateUrls: htmlCandidateUrls,
      });
      const html = response?.html;
      if (response?.ok && html?.ok && html.payloadText) {
        return {
          success: true,
          rawArtifact: new Blob([html.payloadText], { type: "text/html" }),
          filename: html.payloadName || "paper.html",
          artifactKind: "html",
          sourceDoi: inferSourceDoi(context.input),
        };
      }
    } catch {
      // Fall back to current-tab capture below.
    }
  }

  // Delegate to current tab capture
  return executeCaptureCurrentTabHtml(context);
}

function inferSourceDoi(input: string): string | undefined {
  const trimmed = String(input || "").trim();
  return /^10\.\S+/i.test(trimmed) ? trimmed : undefined;
}

function inferElsevierIdentifier(input: string): { kind: "doi" | "pii"; value: string } | undefined {
  const doi = inferSourceDoi(input);
  if (doi) {
    return { kind: "doi", value: doi };
  }
  const trimmed = String(input || "").trim();
  try {
    const parsed = new URL(trimmed);
    const piiMatch = parsed.pathname.match(/\/pii\/([^/?#]+)/i);
    if (piiMatch?.[1]) {
      return { kind: "pii", value: decodeURIComponent(piiMatch[1]) };
    }
  } catch {
    // Not a URL; try raw PII below.
  }
  if (/^S\d{14,}[A-Z0-9]*$/i.test(trimmed)) {
    return { kind: "pii", value: trimmed };
  }
  return undefined;
}

function buildElsevierArticleRetrievalUrl(kind: "doi" | "pii", value: string): string {
  const encodedValue = encodeURIComponent(value).replace(/%2F/gi, "/");
  const params = new URLSearchParams({
    httpAccept: "text/xml",
    view: "FULL",
  });
  return `https://api.elsevier.com/content/article/${kind}/${encodedValue}?${params.toString()}`;
}

function inferArxivId(input: string): string | undefined {
  const trimmed = String(input || "").trim();
  const doiMatch = trimmed.match(/^10\.48550\/arXiv\.([^\s?#]+)$/i);
  if (doiMatch?.[1]) return doiMatch[1];
  const prefixedMatch = trimmed.match(/^arXiv:([^\s?#]+)$/i);
  if (prefixedMatch?.[1]) return prefixedMatch[1];
  try {
    const parsed = new URL(trimmed);
    if (/arxiv\.org$/i.test(parsed.hostname)) {
      const match = parsed.pathname.match(/\/(?:abs|pdf|e-print)\/(.+?)(?:\.pdf)?$/i);
      if (match?.[1]) return decodeURIComponent(match[1]);
    }
  } catch {
    // Not a URL.
  }
  if (/^(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?\/\d{7}(?:v\d+)?)$/i.test(trimmed)) {
    return trimmed;
  }
  return undefined;
}

function buildArxivPdfUrl(arxivId: string): string {
  return `https://arxiv.org/pdf/${arxivId.replace(/\.pdf$/i, "")}.pdf`;
}

function looksLikePdfBytes(bytes: Uint8Array): boolean {
  return bytes.length >= 5 && bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46 && bytes[4] === 0x2d;
}

function isStructuredXmlCandidate(candidate: AcquisitionCandidate): boolean {
  const format = String(candidate.format || "").trim().toLowerCase();
  const handoff = String(candidate.handoff || "").trim().toLowerCase();
  const connector = String(candidate.connector || "").trim().toLowerCase();

  if (format === "xml" || format === "jats" || format === "jats_xml" || format === "structured_xml") {
    return true;
  }

  if (handoff.includes("xml_to_markdown") || handoff.includes("xml_upload_or_native_xml_parse")) {
    return true;
  }

  return [
    "europe_pmc_fulltext_xml",
    "plos_jats_xml",
    "biorxiv_jats_xml",
    "medrxiv_jats_xml",
    "springer_openaccess_api",
    "springer_full_text_tdm",
  ].includes(connector);
}

function pickEpubCandidate(routePlan: {
  top_connector?: string;
  acquisition_candidates?: AcquisitionCandidate[];
}): AcquisitionCandidate | undefined {
  const candidates = routePlan.acquisition_candidates || [];
  const topConnector = String(routePlan.top_connector || "").trim();
  return (
    candidates.find((candidate) => candidate.connector === topConnector && candidate.epub_url) ||
    candidates.find((candidate) => candidate.epub_url)
  );
}

function pickHtmlCandidateUrls(routePlan: {
  top_connector?: string;
  acquisition_candidates?: AcquisitionCandidate[];
  client_handoff_candidates?: ClientHandoffCandidate[];
}): string[] {
  const candidates = routePlan.acquisition_candidates || [];
  const topConnector = String(routePlan.top_connector || "").trim();
  const urls = [
    ...candidates
      .filter((candidate) => candidate.connector === topConnector)
      .flatMap((candidate) => [candidate.html_url, candidate.url]),
    ...candidates.flatMap((candidate) => [candidate.html_url, candidate.url]),
    ...(routePlan.client_handoff_candidates || [])
      .filter((candidate) => candidate.artifact_kind === "html")
      .map((candidate) => candidate.source_url),
  ];
  return Array.from(
    new Set(
      urls
        .map((url) => String(url || "").trim())
        .filter((url) => /^https?:\/\//i.test(url))
    )
  );
}

function pickPdfHandoffCandidate(candidates: ClientHandoffCandidate[]): ClientHandoffCandidate | undefined {
  return candidates.find((candidate) => candidate.artifact_kind === "pdf" && candidate.capture_mode === "download_artifact");
}

function pickArtifactHandoffUrl(candidates: ClientHandoffCandidate[], artifactKind: string): string | undefined {
  return candidates.find((candidate) => candidate.artifact_kind === artifactKind && candidate.artifact_url)?.artifact_url;
}

function pickPdfCandidateUrls(routePlan: {
  top_connector?: string;
  acquisition_candidates?: AcquisitionCandidate[];
  client_handoff_candidates?: ClientHandoffCandidate[];
}): string[] {
  const candidates = routePlan.acquisition_candidates || [];
  const topConnector = String(routePlan.top_connector || "").trim();
  const urls = [
    ...candidates
      .filter((candidate) => candidate.connector === topConnector)
      .flatMap((candidate) => [candidate.pdf_url, candidate.format === "pdf" ? candidate.url : undefined]),
    ...candidates.flatMap((candidate) => [candidate.pdf_url, candidate.format === "pdf" ? candidate.url : undefined]),
    ...(routePlan.client_handoff_candidates || [])
      .filter((candidate) => candidate.artifact_kind === "pdf" && !candidate.requires_user_rights)
      .map((candidate) => candidate.artifact_url),
  ];
  return Array.from(new Set(urls.map((url) => String(url || "").trim()).filter((url) => /^https?:\/\//i.test(url))));
}

function base64ToBytes(payloadBase64: string): Uint8Array {
  const decoded = globalThis.atob(payloadBase64);
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) {
    bytes[index] = decoded.charCodeAt(index);
  }
  return bytes;
}

export { executeAction as default };
