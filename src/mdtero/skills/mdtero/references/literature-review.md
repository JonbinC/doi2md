# Literature review

For a research-question → cited review workflow, follow the cookbook skill at `https://api.mdtero.com/skills/mdtero-literature-review.md`:

1. `mdtero discover "<question>" --limit 20 --json` and add selected DOIs to a project
2. `mdtero project parse --wait --timeout 600 --json` (prefer `source_format_family` in `xml`/`html`/`epub`; reject `abstract_only`/`partial_fulltext` as full-text evidence)
3. `mdtero rag query "<question>" --build-if-needed --json`
4. Expand high-scoring citations with `mdtero content mdtero-doc-<id>@<offset> --json` (or the documents content API)
5. Write the review citing every claim as `[doc_id@offset]`; do not invent references outside `citations` / content slices

Preserve `literature_review_playbook` and `citation_contract.locator_fields` from RAG responses when handing off to another agent.

## Output rule

- Prefer full-text Markdown first; treat PDF as input, not as the normal output
- Inspect `quality_label` / `.low_quality.md` before citing
- Use fallback bundles only when the workflow truly needs image or asset files
- Keep task ids, `reason_code`, `action_hint`, `preferred_artifact`, RAG `answer` / `citations` / `source_nodes` / `evidence_pack` / `citation_contract`, `next_commands`, and download artifact names visible in handoffs
