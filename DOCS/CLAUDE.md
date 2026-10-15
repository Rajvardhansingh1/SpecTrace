# CLAUDE.md — SpecTrace

This file is the mandatory project entry point for Claude Code and any compatible coding agent that honors project instructions.

This file should be read everytime, an instruction is passed to the Agent.

## Project
SpecTrace: Version-aware technical documentation retrieval and change-impact analysis.

Read `Prompt.md` for the complete product and implementation brief, name the breif `Project_breif.md` and Store it in `DOCS/ProjectBreif.md`. 

## Mandatory file protocol
1. At the start of every non-trivial task, read this file, `Project_breif.md`, `State.md`, `Decision.md`, `Explain.md`, and relevant sections of `Design_graph.md`.
2. Read `AgenticSkillsDiscovery.md` for every non-trivial task and follow its task-aware discovery and orchestration procedure. Do not search every skill directory repeatedly when the current verified skill graph remains valid.
3. Read `Testing.md` as the testing contract when relevant. **Never write to or modify `Testing.md` unless the user explicitly authorizes editing that exact file.** This prohibition includes automatic updates, formatting, append-only changes, and regeneration.
4. Update `State.md` whenever meaningful project state changes: code built, milestone reached, decision implemented, test run, failure found, blocker changed, or deployment verified.
5. Update `Decision.md` for significant decisions. Explain what was chosen, why, how it was implemented, alternatives, trade-offs, and validation evidence.
6. Update `Explain.md` when architecture, component responsibilities, data contracts, or core flows change.
7. Update `Design_graph.md` when component relationships, runtime flow, state transitions, persistence, or trust boundaries change.
8. Update the docs in the same work session as the implementation; do not leave known material changes undocumented.
9. Do not claim a feature, skill, test, or deployment is complete without verifying it. Mark unverified work as planned or unverified.

## Skill discovery and skill graph
- On first run, identify the current coding agent and follow `AgenticSkillsDiscovery.md` to discover skills actually accessible in this environment.
- Inspect metadata/descriptions first; read full instructions only for selected skills. Do not install skills or alter global configuration without user authorization.
- Build/refresh a **skill graph** in `State.md`. Nodes represent verified available skills and relevant capabilities; edges represent how they support project tasks (for example planning -> implementation -> testing -> security review -> deployment).
- Record each skill's name, source/location, purpose, and status only when verified: `available`, `selected`, `loaded`, or `applied`. Distinguish capability categories from verified installed skill names.
- Record why each selected skill matters to this project and which project tasks it supports.
- Reuse the graph across routine tasks while the agent and environment remain unchanged. Do not re-scan the entire skills directory for every task.
- Reassess after every three non-trivial updates to `State.md`, or before a major architecture, security, model, data, or deployment change—whichever happens first. Re-discover only what is needed to validate changed availability and relevance.
- Follow the security, token-efficiency, validation, and reporting requirements in `AgenticSkillsDiscovery.md`.
- At the end of each non-trivial task, report skills actually applied and validation results accurately.

## Engineering rules
- Make small, scoped changes. Avoid speculative abstractions and unnecessary dependencies.
- Prefer typed interfaces, deterministic validation, explicit error handling, and reproducible scripts.
- Keep credentials server-side and use environment variables. Never commit secrets.
- Use synthetic/sample data for demos; respect source data licenses and privacy.
- For external model calls, define timeouts, bounded retries, request limits, and clear failure behavior.
- Store durable state in persistent storage, not an ephemeral local filesystem.
- Use mock adapters for deterministic tests and cost-controlled demos.
- Update graphs and explanations from actual implementation, not imagined architecture.
- Keep a clear separation between planned, implemented, tested, and deployed.
- Do not perform destructive actions, deploy costly resources, or use real-world write integrations without appropriate authorization.

## Project-specific constraints
['Inferred dependency links can be wrong; mark them as inferred and preserve evidence.', 'Large repositories require incremental ingestion and limits.', 'Do not fetch private repositories without explicit authorization.', 'Do not present speculative downstream impact as a confirmed breaking change.']

## Expected delivery
- Working vertical slice before broad feature expansion.
- Unit/integration tests and reproducible benchmark as applicable.
- Deployment instructions for Vercel frontend and Render backend.
- Updated State/Decision/Explain/Design_graph after material changes.
- `Testing.md` unchanged unless the user explicitly authorizes an edit.
