# MVP Agentic Change Plans

## Goal

Make agentic mode visibly useful for change-impact questions in the capstone MVP.
Direct RAG can already answer many locate and flow questions. Agentic research
must add value by returning actionable, cited change plans when it has collected
repository evidence, including when it stops at the configured tool budget.

## Scope

- Preserve direct RAG behavior on `/rag` and `repo-research rag`.
- Keep one bounded research agent and the existing `/research` contract.
- Replace self-referential initial search terms with generic change-analysis
  vocabulary.
- Return a deterministic bounded change plan when a change-mode research run hits
  budget after collecting evidence.
- Increase default agentic budget enough for reviewer demos while keeping
  environment and request overrides.
- Add a small offline MVP eval fixture and tests that assert change questions can
  produce evidence-backed change targets without live model calls.

## Non-goals

- No multi-agent orchestration.
- No automatic code changes or pull requests.
- No frontend redesign.
- No live LLM judge evaluation in default tests.
- No changes to direct-RAG prompts or answer validation.

## Acceptance Criteria

- A budget-limited change run with collected evidence returns a usable partial
  plan, not a generic insufficient-evidence answer.
- The answer includes cited evidence, likely change targets, implementation-flow
  guidance, risks, and unresolved questions.
- The trace still records the budget error type and tool-call count.
- Agentic default budget is `5` searches, `6` file reads, and `12` total tool
  calls.
- Initial search text no longer hardcodes this repository's internal class or
  function names.
- Focused tests pass without network or model calls.

## Implementation Notes

The bounded fallback is intentionally conservative. It does not claim the change
plan is complete; it builds a low-confidence plan from evidence the application
has already retrieved or read. This preserves grounding while making the MVP
agentic path useful for reviewer-facing change questions.
