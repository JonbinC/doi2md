"""Run zotero/translators inside the user's Playwright page.

Licensing: zotero/translators is AGPL-3.0. doi2md is MIT, so translator
sources are *not* vendored. They are downloaded on first use from a pinned
commit into the user's cache dir (``~/.cache/mdtero/zotero-translators``) and
executed unmodified inside the page by our own MIT shim (``shim.js``).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Optional

PINNED_COMMIT = "8fdb26b68c732b5810ffb037304c99e68aadd62b"
RAW = "https://raw.githubusercontent.com/zotero/translators/{commit}/{name}"

EMBEDDED_METADATA = "951c027d-74ac-47d4-a107-9c3069ab7b48"
RIS = "32d59d2d-b65a-4da4-b0a3-bdd3cfb979e7"
BIBTEX = "9cb70025-a888-4a29-a210-93ec52da40d4"
DEPENDENCIES = {EMBEDDED_METADATA: "Embedded Metadata.js", RIS: "RIS.js", BIBTEX: "BibTeX.js"}

# publisher key -> translator file (the site translator Zotero itself selects)
PUBLISHER_TRANSLATORS = {
    "acs": "Atypon Journals.js",
    "wiley": "Wiley Online Library.js",
    "tandf": "Taylor and Francis+NEJM.js",
    "aip": "Silverchair.js",
    "oup": "Silverchair.js",
    "ieee": "IEEE Xplore.js",
    "rsc": "RSC Publishing.js",
    "elsevier": "ScienceDirect.js",
}

SHIM_PATH = Path(__file__).with_name("shim.js")
PARAMS = "Zotero,Z,ZU,attr,attrs,text,innerText,request,requestText,requestJSON,requestDocument"


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "mdtero" / "zotero-translators" / PINNED_COMMIT


def load_source(name: str, *, fetch: bool = True, directory: Optional[Path] = None) -> str:
    d = directory or cache_dir()
    path = d / name
    if not path.exists():
        if not fetch:
            raise FileNotFoundError(path)
        url = RAW.format(commit=PINNED_COMMIT, name=urllib.request.quote(name))
        req = urllib.request.Request(url, headers={"User-Agent": "mdtero-connect"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed GitHub host
            data = r.read().decode("utf-8")
        d.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def split_translator(source: str) -> tuple[dict[str, Any], str]:
    """Split a translator file into (JSON header, code)."""
    src = source.lstrip("\ufeff").lstrip()
    header, idx = json.JSONDecoder().raw_decode(src)
    code = re.split(r"/\*\* BEGIN TEST CASES \*\*/", src[idx:])[0]
    return header, code


def factory_js(code: str) -> str:
    names = ["detectWeb", "doWeb", "doImport", "detectImport"]
    exports = "".join(
        f"if(typeof {n}==='function'&&!__s.{n})__s.{n}={n};" for n in names
    )
    return (
        f"(function({PARAMS}){{\n{code}\n;var __s=(typeof exports==='object'&&exports)?exports:{{}};"
        f"{exports}return __s;}})"
    )


def build_program(main_name: str, *, timeout_ms: int = 20000, directory: Optional[Path] = None,
                  fetch: bool = True) -> tuple[str, str]:
    """Return (javascript expression, main translatorID).

    The expression evaluates to ``shim(spec)``; translator code is embedded as
    function literals so no eval/new Function is needed (works under page CSP).
    """
    sources = {}
    header, code = split_translator(load_source(main_name, fetch=fetch, directory=directory))
    main_id = header["translatorID"]
    sources[main_id] = code
    for tid, name in DEPENDENCIES.items():
        sources[tid] = split_translator(load_source(name, fetch=fetch, directory=directory))[1]
    factories = ",\n".join(f"{json.dumps(tid)}: {factory_js(c)}" for tid, c in sources.items())
    shim = SHIM_PATH.read_text(encoding="utf-8").strip()
    program = (
        f"(() => {{ const __shim = {shim};\n"
        f"return __shim({{main: {json.dumps(main_id)}, timeoutMs: {int(timeout_ms)}, factories: {{\n{factories}\n}}}}); }})()"
    )
    return program, main_id


def target_matches(main_name: str, url: str, directory: Optional[Path] = None, fetch: bool = True) -> bool:
    header, _ = split_translator(load_source(main_name, fetch=fetch, directory=directory))
    target = header.get("target") or ""
    return not target or re.search(target, url) is not None


def run_translator(page, publisher_key: str, *, timeout_ms: int = 20000,
                   directory: Optional[Path] = None, fetch: bool = True) -> dict[str, Any]:
    """Run the publisher's translator in ``page``. Never raises."""
    name = PUBLISHER_TRANSLATORS.get(publisher_key)
    if not name:
        return {"items": [], "error": "no translator"}
    try:
        if not target_matches(name, page.url, directory, fetch):
            return {"items": [], "error": f"{name} target does not match {page.url}"}
        program, _ = build_program(name, timeout_ms=timeout_ms, directory=directory, fetch=fetch)
        result = page.evaluate(program)
    except Exception as exc:  # noqa: BLE001
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"[:500]}
    result["translator"] = name
    return result


def pdf_urls(result: dict[str, Any]) -> list[str]:
    out = []
    for item in result.get("items") or []:
        for a in item.get("attachments") or []:
            title = (a.get("title") or "").lower()
            if (a.get("mimeType") == "application/pdf" or "pdf" in title) and "supplement" not in title:
                out.append(a["url"])
    return out
