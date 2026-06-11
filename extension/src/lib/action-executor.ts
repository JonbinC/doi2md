import type {
  ActionContext,
  ActionResult,
  ActionType,
  AcquisitionCandidate,
  ClientHandoffCandidate,
  PublisherCapabilities,
} from "@mdtero/shared";
import { fetchXmlArtifact } from "./page-capture";
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
      // For arXiv, this is a marker action - HTML capture already handled it
      return { success: true };

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

async function executeFallbackPdfParse(
  context: ActionContext,
  routePlan: {
    user_message?: string;
    client_handoff_candidates?: ClientHandoffCandidate[];
    publisher_capabilities?: PublisherCapabilities;
  }
): Promise<ActionResult> {
  const candidate = pickPdfHandoffCandidate(routePlan.client_handoff_candidates || []);
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
      return {
        success: false,
        requiresUpload: true,
        error: "OA source is PDF. Please download and upload manually.",
        nextCommand: buildCliParseCommand(context.input),
      };
    }

    // Try to fetch as HTML
    const response = await fetch(oaUrl, { credentials: "include" });
    if (!response.ok) {
      return { success: false, error: `OA fetch failed: ${response.status}` };
    }

    const html = await response.text();
    const finalUrl = response.url;

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

function base64ToBytes(payloadBase64: string): Uint8Array {
  const decoded = globalThis.atob(payloadBase64);
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) {
    bytes[index] = decoded.charCodeAt(index);
  }
  return bytes;
}

export { executeAction as default };
