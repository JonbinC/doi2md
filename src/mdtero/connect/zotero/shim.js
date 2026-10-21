// mdtero Connect minimal Zotero translator runtime (MIT, part of doi2md).
// Runs unmodified zotero/translators (AGPL, fetched at runtime, not vendored)
// inside the user's own page. Returns metadata + attachment URLs only.
// It never interacts with challenges and never modifies page/browser state.
async (spec) => {
  const logs = [];
  const results = [];
  const pending = new Set();
  const track = (p) => { pending.add(p); p.finally(() => pending.delete(p)); return p; };
  const baseURL = location.href;
  const asyncErrors = [];
  const onRejection = (ev) => asyncErrors.push(String((ev.reason && ev.reason.stack) || ev.reason).slice(0, 800));
  window.addEventListener("unhandledrejection", onRejection);
  const parser = new DOMParser();
  const toDoc = (html, url) => {
    const d = parser.parseFromString(html, "text/html");
    try { const b = d.createElement("base"); b.href = url; d.head && d.head.prepend(b); } catch (e) {}
    try { Object.defineProperty(d, "location", { value: new URL(url) }); } catch (e) {}
    return d;
  };
  const absolute = (u, base) => { try { return new URL(u, base || baseURL).href; } catch (e) { return u; } };
  const q = (root, sel, i) => {
    if (typeof root === "string") { i = sel; sel = root; root = document; }
    if (!root || !root.querySelectorAll) return null;
    return i === undefined ? root.querySelector(sel) : root.querySelectorAll(sel)[i] || null;
  };
  const shift = (args) => (typeof args[0] === "string" ? [document, ...args] : args);
  const attr = (...a) => { const [r, s, n, i] = shift(a); const e = q(r, s, i); return e ? (e.getAttribute(n) || "") : ""; };
  const text = (...a) => { const [r, s, i] = shift(a); const e = q(r, s, i); return e ? e.textContent : ""; };
  const innerText = (...a) => { const [r, s, i] = shift(a); const e = q(r, s, i); return e ? (e.innerText || e.textContent) : ""; };
  const attrs = (r, s, n) => Array.from((r || document).querySelectorAll(s)).map((e) => e.getAttribute(n));
  async function request(url, opts = {}) {
    const u = absolute(url);
    const init = { method: opts.method || (opts.body ? "POST" : "GET"), headers: opts.headers || {}, body: opts.body, credentials: "include" };
    if (init.body && !init.headers["Content-Type"]) init.headers["Content-Type"] = "application/x-www-form-urlencoded";
    const r = await track(fetch(u, init));
    const body = await r.text();
    logs.push(`request ${init.method} ${u.slice(0, 160)} -> ${r.status} (${body.length} chars)`);
    if (!r.ok && !(opts.successCodes || []).includes(r.status)) throw new Error(`HTTP ${r.status} for ${u}`);
    return { status: r.status, url: r.url, body, headers: r.headers };
  }
  const requestText = async (u, o) => (await request(u, o)).body;
  const requestJSON = async (u, o) => JSON.parse(await requestText(u, o));
  const requestDocument = async (u, o) => { const r = await request(u, o); return toDoc(r.body, r.url); };

  const nodes = (els) => (Array.isArray(els) ? els : els && els.length !== undefined && !els.nodeType ? Array.from(els) : [els]);
  const ZU = {
    xpath(els, xp, ns) {
      const out = [];
      for (const el of nodes(els)) {
        if (!el) continue;
        const d = el.ownerDocument || el;
        const res = d.evaluate(xp, el, ns ? (p) => ns[p] || null : null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
        let n; while ((n = res.iterateNext())) out.push(n);
      }
      return out;
    },
    xpathText(els, xp, ns, delim) {
      const r = ZU.xpath(els, xp, ns);
      return r.length ? r.map((n) => n.textContent).join(delim === undefined ? ", " : delim) : null;
    },
    trimInternal: (s) => String(s || "").replace(/\s+/g, " ").trim(),
    trim: (s) => String(s || "").trim(),
    cleanAuthor(name, type, useComma) {
      name = ZU.trimInternal(String(name || "").replace(/^[\s.,/\[\]:]+|[\s,/\[\]:]+$/g, ""));
      let first = "", last = name;
      if (useComma && name.includes(",")) { [last, first] = name.split(/\s*,\s*/, 2); }
      else if (!useComma) { const i = name.lastIndexOf(" "); if (i > 0) { first = name.slice(0, i); last = name.slice(i + 1); } }
      return { firstName: first, lastName: last, creatorType: type || "author" };
    },
    cleanDOI(s) { const m = String(s || "").match(/10\.\d{4,9}\/[^\s&"'<>]+/); return m ? m[0] : false; },
    cleanISSN(s) { const m = String(s || "").match(/\d{4}-?\d{3}[\dXx]/); return m ? m[0].replace(/^(\d{4})-?/, "$1-").toUpperCase() : false; },
    cleanISBN(s) { const m = String(s || "").replace(/-/g, "").match(/\d{9}[\dX]|\d{13}/); return m ? m[0] : false; },
    strToDate(s) {
      s = String(s || ""); const o = {};
      let m = s.match(/(\d{4})[-\/.](\d{1,2})(?:[-\/.](\d{1,2}))?/);
      if (m) { o.year = m[1]; o.month = +m[2] - 1; if (m[3]) o.day = +m[3]; return o; }
      const d = new Date(s); if (!isNaN(d)) { o.year = String(d.getUTCFullYear()); o.month = d.getUTCMonth(); o.day = d.getUTCDate(); return o; }
      m = s.match(/\b(\d{4})\b/); if (m) o.year = m[1];
      return o;
    },
    formatDate(o) { const p = (n) => String(n).padStart(2, "0"); return [o.year, o.month !== undefined ? p(o.month + 1) : null, o.day ? p(o.day) : null].filter(Boolean).join("-"); },
    strToISO(s) { const o = ZU.strToDate(s); return o.year ? ZU.formatDate(o) : false; },
    capitalizeTitle: (s) => s,
    unescapeHTML(s) { const d = parser.parseFromString(String(s || ""), "text/html"); return d.documentElement.textContent; },
    removeDiacritics: (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, ""),
    fieldIsValidForType: () => true,
    getCreatorsForType: () => ["author", "editor", "contributor"],
    getVersion: () => "mdtero-shim",
    deepCopy: (o) => JSON.parse(JSON.stringify(o)),
    resolveURL: (u) => absolute(u),
    text: (s) => s,
    doGet(urls, cb, done) { const p = (async () => { for (const u of [].concat(urls)) { const r = await request(u); cb && cb(r.body, r, r.url); } done && done(); })(); return track(p); },
    doPost(u, body, cb, headers) { return track((async () => { const r = await request(u, { method: "POST", body, headers }); cb && cb(r.body, r); })()); },
    processDocuments(urls, proc, done) { return track((async () => { for (const u of [].concat(urls)) { const d = await requestDocument(u); await proc(d, d.location ? d.location.href : u); } done && done(); })()); },
  };

  function makeTranslator(id, parent) {
    const handlers = { itemDone: [] };
    let input = "", pos = 0;
    const Zotero = {
      debug: (m) => logs.push(`[${id.slice(0, 8)}] ${typeof m === "string" ? m : JSON.stringify(m)}`.slice(0, 500)),
      done() {}, monitorDOMChanges() {}, selectItems(items, cb) { if (cb) cb(null); return Promise.resolve(null); },
      getHiddenPref: () => undefined, getOption: () => undefined, nextItem: () => false, write() {},
      parentTranslator: parent ? "parent" : false,
      Utilities: ZU,
      read(n) {
        if (pos >= input.length) return false;
        if (n) { const s = input.substr(pos, n); pos += n; return s; }
        let e = input.indexOf("\n", pos); if (e < 0) e = input.length;
        const line = input.slice(pos, e).replace(/\r$/, ""); pos = e + 1; return line;
      },
      loadTranslator(type) { return makeLoader(type, self); },
      Collection: class { complete() {} },
    };
    const self = {
      id, Zotero, handlers,
      setInput(s) { input = String(s || ""); pos = 0; },
      emit(item) {
        if (handlers.itemDone.length) {
          // A child's handler may call item.complete() again; that must go to the parent.
          item.complete = () => (parent ? parent.emit(item) : results.push(item));
          for (const h of handlers.itemDone) h(null, item);
        } else if (parent) parent.emit(item); else results.push(item);
      },
    };
    Zotero.Item = class { constructor(t) { this.itemType = t; this.creators = []; this.tags = []; this.notes = []; this.attachments = []; this.seeAlso = []; }
      complete() { self.emit(this); } };
    return self;
  }
  // Embedded Metadata loads the RDF importer only as a statement sink; this
  // stub lets EM fall back to its HighWire (citation_*) mapping.
  const rdfStub = (t) => ({ Zotero: { RDF: { addStatement() {} } }, getNodes: () => [], detectType: () => false, defaultUnknownType: false, doImport() {} });

  function instantiate(code, t) {
    const factory = spec.factories[code];
    if (!factory) throw new Error(`translator ${code} not loaded`);
    const Z = t.Zotero;
    const scope = factory(Z, Z, ZU, attr, attrs, text, innerText, request, requestText, requestJSON, requestDocument);
    return scope;
  }
  function makeLoader(type, parent) {
    let tid = null, doc = document, str = "";
    const child = makeTranslator("pending", parent);
    const api = {
      setTranslator(x) { tid = Array.isArray(x) ? x[0] : (x && x.translatorID) || x; child.id = String(tid); },
      setDocument(d) { doc = d; }, setString(s) { str = s; }, setSearch() {},
      setHandler(n, f) { if (n === "itemDone") child.handlers.itemDone.push(f); },
      getTranslators: async () => (tid ? [{ translatorID: tid }] : []),
      async getTranslatorObject(cb) {
        child.setInput(str);
        const obj = tid === "5e3ad958-ac79-463d-812b-a86a9235c28f" ? rdfStub(child) : instantiate(tid, child);
        if (cb) {
          try { await cb(obj); }
          catch (e) { const m = `child ${tid} failed: ${String((e && e.stack) || e).slice(0, 600)}`; logs.push(m); asyncErrors.push(m); throw e; }
        }
        return obj;
      },
      async translate() {
        try { return await this._translate(); }
        catch (e) { const m = `child ${tid} failed: ${String((e && e.stack) || e).slice(0, 600)}`; logs.push(m); asyncErrors.push(m); throw e; }
      },
      async _translate() {
        if (tid === "5e3ad958-ac79-463d-812b-a86a9235c28f") return [];
        const s = instantiate(tid, child);
        if (type === "import") { child.setInput(str); await s.doImport(); }
        else await s.doWeb(doc, doc.location ? doc.location.href : baseURL);
        return [];
      },
    };
    return api;
  }

  const root = makeTranslator(spec.main, null);
  let itemType = null, error = null;
  const deadline = Date.now() + (spec.timeoutMs || 20000);
  try {
    const s = instantiate(spec.main, root);
    logs.push("main translator loaded");
    itemType = s.detectWeb ? await s.detectWeb(document, baseURL) : null;
    if (itemType && itemType !== "multiple") {
      await s.doWeb(document, baseURL);
      logs.push("doWeb returned");
      // translators often finish via un-awaited callbacks; wait for quiescence.
      while ((pending.size || !results.length) && Date.now() < deadline) await new Promise((r) => setTimeout(r, 250));
    }
  } catch (e) { error = String((e && e.stack) || e).slice(0, 1000); }
  window.removeEventListener("unhandledrejection", onRejection);
  if (!error && !results.length && asyncErrors.length) error = asyncErrors.join(" | ");
  const clean = results.map((it) => ({
    itemType: it.itemType, title: it.title || null, DOI: it.DOI || null, date: it.date || null,
    publicationTitle: it.publicationTitle || null, volume: it.volume || null, issue: it.issue || null, pages: it.pages || null,
    url: it.url || null, abstractNote: it.abstractNote || null,
    creators: (it.creators || []).map((c) => ({ firstName: c.firstName, lastName: c.lastName, creatorType: c.creatorType })),
    attachments: (it.attachments || []).filter((a) => a && a.url).map((a) => ({ title: a.title || "", mimeType: a.mimeType || "", url: absolute(a.url) })),
  }));
  return { itemType, items: clean, error, logs: logs.slice(-40) };
}
