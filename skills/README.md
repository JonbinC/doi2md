# Skills

This directory keeps the public Mdtero agent skill source.

The maintained skill is `mdtero/SKILL.md`. It is mirrored into
`src/mdtero/skills/mdtero/SKILL.md` and installed into Codex, Claude Code,
Gemini CLI, Hermes, and OpenCode by the Python command:

```bash
mdtero agent install --target <target>
```

Per-agent `INSTALL.md` copies are retired. Agent-specific behavior belongs in
`src/mdtero/agent.py`; user-facing setup belongs in `README.md`,
`install/README.md`, and the packaged `SKILL.md`.
