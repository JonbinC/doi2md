# Skills

This directory keeps the public Mdtero agent skill source.

The maintained skill is `mdtero/` (`SKILL.md` + `references/`). It is mirrored into
`src/mdtero/skills/mdtero/`, published on the website as
`https://mdtero.com/agent-skills`, and installed into Codex, Claude Code,
Cursor, Gemini CLI, Hermes, OpenCode, Trae, and WorkBuddy by:

```bash
npx skills add JonbinC/doi2md
mdtero agent install --target <target>
```

Discovery index: `https://mdtero.com/.well-known/agent-skills/index.json`

After editing the skill package, run `scripts/sync-agent-skill.sh` from the
website repository (Nextmdtero) to refresh the packaged copy and website assets.
