/* Executable DESIGN contract. Not wired to Mdtero production APIs. */
(function (root) {
  'use strict';
  const QUOTA_BYTES = 5 * 1024 ** 3;
  const KNOWN_OUTCOMES = new Set(['full_text_ok', 'entitled', 'metadata_only', 'not_entitled', 'key_invalid', 'probe_failed']);
  function readiness(state = {}) {
    const signedIn = state.signedIn === true;
    const keyVerified = signedIn && state.keyStatus === 'verified';
    const keySkipped = signedIn && state.keyStatus === 'skipped';
    const online = signedIn && state.relayOnline === true;
    const browser = online && state.browserReady === true;
    const host = signedIn && state.hostVerified === true;
    const probe = state.probe || {};
    const recent = Number.isFinite(probe.ageSeconds) && probe.ageSeconds >= 0 && probe.ageSeconds <= 300;
    const fullText = signedIn && probe.outcome === 'full_text_ok' && probe.bodyVerified === true
      && recent && typeof probe.documentId === 'string' && probe.documentId.length > 0
      && typeof probe.scopeId === 'string' && probe.scopeId === state.accessScopeId;
    return {
      steps: [signedIn ? 'complete' : 'pending', keyVerified ? 'complete' : keySkipped ? 'skipped' : 'pending',
        online && host ? 'complete' : online || host ? 'partial' : 'pending'],
      canTryOpenPapers: signedIn,
      keyVerified, relayOnline: online, browserReady: browser, hostVerified: host,
      probeOutcome: signedIn && recent && probe.scopeId === state.accessScopeId && KNOWN_OUTCOMES.has(probe.outcome)
        ? probe.outcome : 'unknown',
      verifiedArticleId: fullText ? probe.documentId : null,
      allPublishersVerified: false,
      cloudReady: signedIn && state.cloudCommitted === true,
      canUseSavedLibrary: signedIn && state.cloudCommitted === true,
      nextStep: !signedIn ? 'register' : !keyVerified && !keySkipped ? 'credentials' : !online || !host ? 'connect' : 'first_evidence'
    };
  }
  function canReserve({usedBytes, reservedBytes, incomingBytes, quotaBytes = QUOTA_BYTES}) {
    for (const value of [usedBytes, reservedBytes, incomingBytes, quotaBytes]) {
      if (!Number.isSafeInteger(value) || value < 0) throw new TypeError('Non-negative safe byte counts required');
    }
    // Admission arithmetic only. Production MUST reserve in a database transaction.
    return incomingBytes <= quotaBytes && usedBytes <= quotaBytes - incomingBytes
      && reservedBytes <= quotaBytes - incomingBytes - usedBytes;
  }
  function syncPartition({accountId, transport, libraryType, libraryId, serverId}) {
    if (!accountId || !libraryId || !['web', 'local'].includes(transport)
        || !['user', 'group'].includes(libraryType)) throw new TypeError('Invalid source scope');
    if (transport === 'local' && !serverId) throw new TypeError('Local sync needs an instance partition');
    return JSON.stringify([String(accountId), transport, libraryType, String(libraryId), transport === 'local' ? String(serverId) : null]);
  }
  function checkpoint({priorVersion, responseVersions, allPagesSaved, deletionsProcessed, pendingErrors = []}) {
    if (!Number.isSafeInteger(priorVersion) || priorVersion < 0) throw new TypeError('Invalid prior version');
    if (!Array.isArray(responseVersions) || !responseVersions.length) return priorVersion;
    const v = responseVersions[0];
    if (!Number.isSafeInteger(v) || v < priorVersion || responseVersions.some(n => n !== v)) return priorVersion;
    return allPagesSaved === true && deletionsProcessed === true && Array.isArray(pendingErrors) && !pendingErrors.length ? v : priorVersion;
  }
  const api = {QUOTA_BYTES, readiness, canReserve, syncPartition, checkpoint};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.MdteroDesignPolicy = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
