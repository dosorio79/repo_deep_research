# M3.6 - Lovable Frontend Testing Harness

## Status

On hold.

## Goal

Build a thin React TypeScript frontend with Lovable after M3.5 establishes the
stable answer-plus-trace contract.

This milestone is a manual testing harness, not the full M5 product and
operations milestone.

## Intended scope

- question input;
- mode selector;
- retrieval mode selector;
- answer rendering;
- implementation flow, evidence, files, symbols, change targets, risks, and
  unresolved questions;
- trace/debug panel using the M3.5 `RagRunTrace` payload;
- local API configuration for `POST /rag`.

## Non-goals while on hold

M3.6 should not start until explicitly resumed. When it starts, it should still
avoid:

- feedback persistence;
- Logfire dashboards;
- telemetry database writes;
- authentication;
- repository ingestion UI unless a stable API already exists;
- agentic research UI beyond consuming an already implemented backend contract.

## Resume condition

Resume after M3.5 is complete and the `/rag` response envelope is stable enough
for frontend contract tests.
