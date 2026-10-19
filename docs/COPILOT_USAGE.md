# GitHub Copilot and Azure MCP in this repository

- `AGENTS.md` and `.github/copilot-instructions.md` carry the module map and rules every coding agent follows here (tests first, one LLM seam, no real names, deterministic simulator).
- `.vscode/mcp.json` registers the Azure MCP Server (`npx -y @azure/mcp@latest server start`) so VS Code agent mode and Copilot CLI can inspect the Container App, Cosmos DB and Foundry resources from the editor.
- Development was driven with an agentic coding assistant following the plan in `docs/superpowers/plans/2026-10-19-beyond-the-scoreline.md`: each task starts with a failing test, and every commit on `feat/mvp` is one plan task.
- Conventional Commits in English; CI runs lint, tests and the web build on every push.
