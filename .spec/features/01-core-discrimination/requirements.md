# Feature 01: Core Discrimination Algorithm

## Goal

Given a hypothesis, a current system, an alternative system, a source of
candidate inputs, and a judge, return the minimum set of inputs that
discriminate between current and alternative — i.e., inputs where the current
system's output is judged failing and the alternative's is judged passing.

This feature contains the pure algorithmic core. No real LLM integration, no
real user systems, no MCP or CLI. All external dependencies are injected.

## Acceptance criteria

- `src/hypothesize/core/types.py` defines the types used throughout:
  `Hypothesis`, `TestCase`, `DiscriminationResult`, `InsufficientEvidence`,
  `Verdict`, `ProbingDimension`, `CandidateInput`, `Budget`.
- `src/hypothesize/core/llm.py` defines an `LLMBackend` protocol with an
  async `complete(messages, **kwargs)` method. A `MockBackend` for testing
  lives under `tests/_fixtures/mock_backend.py`, not in `src/`.
- `src/hypothesize/core/judge.py` defines a `Judge` protocol and three
  implementations: `ExactMatchJudge`, `RubricJudge`, `PairwiseJudge`. All
  three use the injected `LLMBackend` where relevant.
- `src/hypothesize/core/decompose.py` implements `decompose_hypothesis` which
  takes a hypothesis string and a context, returns a list of
  `ProbingDimension` objects. Prompts live in `prompts.py` in the same
  module, separated for easy iteration.
- `src/hypothesize/core/generate.py` implements `generate_candidates` which
  takes a hypothesis, a single `ProbingDimension`, a context, and a count,
  and returns `CandidateInput` objects. The discrimination loop iterates
  dimensions and calls `generate_candidates` once per dimension.
  Budget-aware.
- `src/hypothesize/core/discrimination.py` implements
  `find_discriminating_inputs` composing the above. Returns a
  `DiscriminationResult` with either the discriminating inputs or an
  `InsufficientEvidence` signal.
- When fewer than 3 discriminating inputs are found after exhausting
  candidates within budget, return `InsufficientEvidence` with a reason.
- When more than N discriminating inputs are found (default N=10), return
  at most N, chosen for diversity (cluster-based sampling on candidate
  embeddings is out of scope; use a simple diversity heuristic for now).
- All code covered by tests using `MockBackend`. Test coverage on
  `src/hypothesize/core/` at least 80%.
- Full test suite runs offline with no network calls.

## Non-goals (explicit)

- Not in this feature: real LLM backend implementation (that's Feature 02).
- Not in this feature: dataset-specific adapters or example systems
  (Feature 03).
- Not in this feature: CLI, MCP server, Claude Code skill (Feature 04).
- Not in this feature: embedding-based candidate clustering. Use a simple
  diversity heuristic (e.g., pick inputs that differ maximally in surface
  tokens) for now.
- Not in this feature: automatic alternative-system generation (the
  "improve the prompt" behavior). That lives in Feature 02.

## Dependencies

None. This is the first feature.
