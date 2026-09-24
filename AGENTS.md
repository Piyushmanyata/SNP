# AGENTS.md

Operating rules for coding agents in this repo. Cheapest correct path wins.
Read this once. Do not re-read it. Do not summarise it back to the user.

## 0. Always on

| Setting | Value |
|---|---|
| Ponytail | `full` — run `/ponytail full` at session start, never lower it |
| Context reads | lean-ctx modes only (§2) |
| Dev servers, browsers, computer use | Forbidden (§7) |
| Code comments | None, except the one workaround case in §8 |
| Final answer | Blocked until §9 gate passes |

## 1. Token budget

Defaults. Override only if the user gives a number.

| Phase | Budget | Hard stop |
|---|---|---|
| Orientation before first edit | 15k | Stop reading, start a subagent instead |
| One subagent | 25k in / 300 words out | Return partial findings, say so |
| Review subagent | 15k / 200 words | Return top 3 findings only |
| Whole task | 120k | Report progress, ask before continuing |

Rules:

- Never read a file you are not going to edit or reason about.
- Never re-read a file you already read this session; use `ctx_session` recall.
- Never paste tool output into the response. Report conclusions only.
- Quote exact code, numbers, and errors. Summarise everything else.

## 2. Reading context (lean-ctx)

Ladder — stop at the first rung that answers the question.

1. `ctx_overview(task)` — task-relevant project map
2. `ctx_semantic_search(query)` — find the code by meaning, not filename
3. `lean-ctx read <file> -m map` — purpose, deps, exports
4. `lean-ctx read <file> -m signatures` — API surface
5. `lean-ctx read <file> -m aggressive` — body logic, syntax stripped
6. `lean-ctx read <file> -m entropy` — file is repetitive (generated, fixtures, logs)
7. `lean-ctx read <file> -m diff` — re-checking a file you already read; use this
   after every edit instead of re-reading the file
8. `lean-ctx read <file> -m full` — only for files you are about to edit
9. `lean-ctx -c <cmd>` — any verbose shell (git, npm, test, build, docker)

Also: `ctx_knowledge` to persist facts across sessions, `ctx_refactor` for renames
and reference-finding, `ctx_gain` when the user asks what was saved.

Banned: `cat` on a whole file, recursive `ls`/`find` to "look around", reading a
directory tree by hand, full-file Read when `map` or `signatures` would do.

## 3. Enough context before changing code

Do not edit until all four are true:

1. You can name the exact file(s) and symbol(s) that change.
2. You have read every caller of the symbol you are changing (`ctx_refactor`).
3. You know which test proves the change works, and have run it red first.
4. You know the existing pattern this repo already uses for this problem.

If any is false, gather it — or spawn one Explore subagent to gather it (§5).
A wrong edit costs more tokens than the read that would have prevented it.

## 4. Research before applying

For anything non-obvious (new dep, new pattern, unfamiliar API, perf fix):

1. Check the repo first — the pattern probably exists already.
2. Then the installed dependency's own docs/types.
3. Then the web, primary sources only (`research` skill).
4. Write the chosen approach in one sentence with the rejected alternative.
5. Then implement.

Never implement the first idea that compiles. Never invent an API — verify it.

## 5. Subagents

Use them aggressively for anything that fans out. They are how work goes parallel
and how the main context stays small.

Spawn a subagent when: searching >3 files, exploring an unknown area, running an
independent sub-problem, or reviewing (§9).

Every subagent prompt uses this contract. No exceptions.

```
GOAL: <one sentence, testable>
DONE WHEN: <exact artefact — file list, patch, 3 findings, yes/no>
BUDGET: <n> tokens, <n> tool calls
STOP EARLY IF: answer found | 2 dead ends | budget 80% spent
CONTEXT: <paths + facts already known — do not rediscover these>
FORBIDDEN: re-reading AGENTS.md, full-file reads, running the full suite,
           dev servers, editing files outside <scope>
RETURN: <=300 words. Conclusions + file:line. No transcripts, no code dumps.
```

Rules:

- Max 4 concurrent. Never two agents editing the same file.
- Read-only agents (Explore, review) may run wide; writing agents stay narrow.
- A subagent that hits budget returns what it has. It never silently continues.
- Give the subagent the facts you already know. Re-deriving context is the
  single biggest token leak.

## 6. Parallel work

1. Split the task into sub-problems with no shared files.
2. Fan them out in one batch of tool calls / one batch of subagents.
3. Integrate, then verify once at the end.

Batch independent tool calls in a single block — never serialise calls that do
not depend on each other. Sequence only true dependencies.

## 7. Verification — no dev servers

Forbidden: `npm run dev`, watch mode, browsers, screenshots, computer use,
manual clicking, "start the server and check".

Use instead, in this order:

1. Typecheck — `tsc --noEmit` (or repo equivalent)
2. Lint
3. Targeted test — single file or single test name, while iterating
4. Build — only if the change could break it
5. Full suite — once, at the end, before answering

Run these through `lean-ctx -c` so failures come back compressed. On failure,
read only the failing frame, not the whole file.

## 8. Code style

- Simplest thing that works. Complex feature, simple build. Ponytail decides ties.
- Ponytail's ladder — what `full` mode enforces — before writing anything: does it
  need to exist → already in the codebase → stdlib → native platform → installed
  dep → one line → minimum that works.
- No comments. Names and types carry the meaning. Sole exception: a non-obvious
  workaround, one line, with an issue link.
- No abstraction until the third occurrence. No config for one call site.
- No defensive layers, no speculative options, no "future-proofing".
- Never weakened: validation, error handling, security, accessibility, types.
- Delete dead code as you pass it.

## 9. Definition of done — the gate

Do not send a final answer until every line is true.

1. Full test suite passes. Typecheck passes. Lint passes.
2. Two adversarial reviews ran as subagents, in parallel, 15k each:
   - **Correctness**: find the input that breaks this. Bugs, missed callers,
     broken edge cases, untested paths. Return `<=3` findings, worst first.
   - **Simplicity**: what here should not exist? Over-abstraction, dead options,
     code a stdlib call replaces. Return `<=3` findings, worst first.
   Both are told to return "no findings" rather than invent something.
3. Every confirmed finding is fixed or explicitly declined with a reason.
4. Tests re-run and pass after the fixes.
5. Docs updated in the same change (§10).

If tests do not pass, say so plainly and stop. Never report a partial pass as done.

## 10. Docs

Follow the mattpocock convention. Docs are part of the change, not a follow-up.

| Artefact | When |
|---|---|
| ADR | Any decision with a rejected alternative — context, decision, consequence |
| Glossary / ubiquitous language | New domain term appears in code |
| Domain model | Entity, relationship, or invariant changes |
| Module doc | Public interface of a deep module changes |

## 11. Skills

The mattpocock skills are the default working method, not a fallback. Route every
task through this table and read the skill before starting, not halfway through.
A repo-local skill for the same job overrides the row; nothing else does.

| Task | Skill |
|---|---|
| Unsure which skill | `ask-matt` |
| Plan or spec is fuzzy | `grill-me`, `batch-grill-me` |
| Plan + docs together | `grill-with-docs` |
| Build a feature | `tdd`, then `implement` |
| Hard bug or perf regression | `diagnosing-bugs` |
| Review a diff | `code-review`, `review` |
| Module or interface design | `codebase-design`, `design-an-interface` |
| Work too big for one session | `wayfinder` |
| Split a plan into tickets | `to-tickets`, `to-spec` |
| Domain terms | `domain-modeling`, `ubiquitous-language` |
| Answer an unknown | `research` |
| Throwaway spike | `prototype` |
| Out of context | `handoff`, `claude-handoff` |
| Merge conflicts | `resolving-merge-conflicts` |

Improvising when a row matches is a defect.

## 12. Reporting to the user

Short. Numbers first. No filler, no preamble, no recap of steps already shown.
State assumptions in one line. Ask only when the answer changes what you build.


# Agent Governance Rules — SNP Camps (Hostinger KVM Stack)

## Architecture Overview

The authoritative application stack consists of:
- `frontend/`: React single-page application (React 18 + Tailwind CSS + Lucide)
- `backend/`: FastAPI async Python application with the PyMongo Async driver on a single-node MongoDB replica set
- `memory/`: PRD specifications and test credentials
- `docker-compose.prod.yml`: Hostinger KVM deployment, reminder worker, TLS and backups

The root Next.js + Supabase application is legacy and has been retired.

## Rules & Boundaries

- All development must take place exclusively within `frontend/` and `backend/`.
- Backend uses the PyMongo Async driver. Invariants are maintained via unique indexes, atomic conditional operations and multi-document transactions.
- Desk actions: Registration -> Print Prescription (`printed_at` presence) -> Mark Seen -> Clinical Fulfilment.
- Accessibility: High contrast, 44x44 minimum touch targets, responsive field-ready layout.
