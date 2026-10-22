/* Same-origin Connect bridge client. Secrets never leave the Python bridge. */
(() => {
  "use strict";
  let csrf = "";
  const jsonHeaders = () => {
    const headers = { Accept: "application/json" };
    if (csrf) headers["X-Mdtero-CSRF"] = csrf;
    return headers;
  };

  async function readError(response) {
    let payload = null;
    try { payload = await response.json(); } catch { payload = null; }
    const hint = payload && (payload.action_hint || payload.message || payload.reason_code);
    const error = new Error(hint || ("HTTP " + response.status));
    error.payload = payload;
    error.status = response.status;
    throw error;
  }

  async function api(path, options = {}, rawResponse = false) {
    const response = await fetch(path, {
      ...options,
      headers: { ...jsonHeaders(), ...(options.headers || {}) },
      credentials: "same-origin",
    });
    if (!response.ok) await readError(response);
    if (rawResponse) return response;
    const type = response.headers.get("content-type") || "";
    if (type.includes("application/json")) return response.json();
    return response;
  }

  window.MdteroConnectApi = {
    async session() {
      const data = await api("/connect/v1/session");
      csrf = data.csrf || "";
      return data;
    },
    listDocuments() { return api("/connect/v1/library/documents"); },
    listTags() { return api("/connect/v1/library/tags"); },
    taggedDocuments(tags, match = "all") {
      const params = new URLSearchParams({ match });
      for (const tag of tags) params.append("tag", tag);
      return api("/connect/v1/library/tagged-documents?" + params.toString());
    },
    updateTags({ document_ids, add = [], remove = [], dry_run }) {
      return api("/connect/v1/library/tags/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...jsonHeaders() },
        body: JSON.stringify({ document_ids, add, remove, dry_run }),
      });
    },
    async exportSelection({ document_ids, format }) {
      const response = await api("/connect/v1/library/export", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...jsonHeaders() },
        body: JSON.stringify({ document_ids, format }),
      }, true);
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const match = /filename="?([^";]+)"?/i.exec(disposition);
      const filename = (match && match[1]) || "mdtero-export.bin";
      const exportLabel = response.headers.get("x-mdtero-export") || format;
      return { blob, filename, exportLabel };
    },
    relayDiagnostics() { return api("/connect/v1/relay/diagnostics"); },
    entitlementCheck(confirm_fulltext = false) {
      return api("/connect/v1/relay/entitlement-check", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...jsonHeaders() },
        body: JSON.stringify({ confirm_fulltext }),
      });
    },
    zoteroStatus() { return api("/connect/v1/zotero/status"); },
    zoteroCollections() { return api("/connect/v1/zotero/collections"); },
    zoteroItems(collectionKey) {
      return api("/connect/v1/zotero/collections/" + encodeURIComponent(collectionKey) + "/items");
    },
    zoteroImport({ collection_key, dry_run, request_id }) {
      return api("/connect/v1/zotero/import", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...jsonHeaders() },
        body: JSON.stringify({ collection_key, dry_run, request_id }),
      });
    },
    agentStatus() { return api("/connect/v1/agent/status"); },
  };
})();
