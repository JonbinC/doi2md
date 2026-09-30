# Trae setup

1. Install the skill (preferred):

```bash
npx skills add JonbinC/doi2md
# Trae Agent Skills directory:
mdtero agent install --target trae
```

2. Optional project MCP: copy `mcp.json` to `.trae/mcp.json` inside the workspace, then run `mdtero project init` and `mdtero mcp serve` when the agent needs project context.
