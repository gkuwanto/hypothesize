# Product

Hypothesize turns informal LLM failure hypotheses into minimum discriminating
regression benchmarks. It is a developer-workflow tool, not a comprehensive
eval generator.

## Thesis

Existing eval generation tools (Ragas, DataMorgana, NeMo Curator, ProbeLLM)
produce comprehensive benchmarks. They are optimized for coverage and
diversity. That is the wrong optimization for the most common day-to-day
case: a stakeholder complains, an engineer wants to verify the complaint and
produce a targeted regression test in under a few minutes and under a few
dollars of tokens.

Hypothesize optimizes for the minimum set of test cases that discriminate
between a current system and a plausibly-better alternative, given a stated
hypothesis. Fewer tokens per iteration. Composable over time. Tests have a
stated reason for existing (the hypothesis they prove).

## Users

- ML engineers maintaining LLM-backed production systems
- Prompt engineers iterating on system prompts with stakeholder feedback
- Claude Code users who want regression tests to live in their repo

## Non-users (out of scope)

- Teams doing pre-training evaluation at scale
- Users who want comprehensive benchmarks (use Ragas)
- Users who want autonomous failure discovery (use ProbeLLM)

## Success criteria for the MVP

- Generates a discriminating benchmark for a stated hypothesis in under 60
  seconds of wall time and under $1 of LLM spend for most cases
- Works against at least three system types (classifier, RAG QA, agent)
  demonstrated via `examples/`
- Packaged as a Claude Code skill and an MCP server
- Regression suite composes across multiple hypotheses; past tests can be
  revalidated with `hypothesize validate`
