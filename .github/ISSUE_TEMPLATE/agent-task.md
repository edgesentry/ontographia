---
name: Coding-agent task
about: Task brief for a coding agent, including the recommended lane.
title: ""
labels: ""
assignees: ""
---

# Coding-agent task

## Agent and model

FILL_ME

## Recommended lane / model / agent

- Implementation: FILL_ME
- Fallback: FILL_ME
- Model check: FILL_ME

## Goal

FILL_ME

## Context links

- Pull request: FILL_ME
- Files: FILL_ME
- Head SHA: FILL_ME

## Scope In-Out

In:

FILL_ME

Out:

FILL_ME

## Steps or review focus

FILL_ME

## Acceptance criteria and output format

- FILL_ME
- For reviews, the result starts with `Model: <name/id>` and names the model that produced it.
- For reviews, the result includes a VERDICT line and findings grouped by severity.

## Constraints

- Do not merge; the maintainer merges.
- Do not run git or gh; the kit adapter or the calling script does that after
  the scope check (see
  [Coding agents change files only](https://github.com/yohei1126/agent-ops-kit/blob/main/docs/shared-rules.md#coding-agents-change-files-only)).
- Do not change secrets or credentials.
- Work in a separate worktree.

## Where to write the result

FILL_ME
