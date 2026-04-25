# HotpotQA — curated discriminating cases for video

Three cases, not four. The 50-item filter pass produced exactly three
items where DIRECT failed and DECOMPOSE passed under exact-match
judging. Inventing a fourth would mean lowering the quality bar or
re-running with different randomness until the count came out right;
both are dishonest. The natural set is three, all strong.

See `examples/hotpotqa/output/multi_hop_filter_run1.yaml` for the
full filter run output and `CURATED.yaml` for a machine-readable
version of this list.

## Filter run summary

| outcome              | count |
|----------------------|-------|
| both correct         | 17    |
| both wrong           | 27    |
| only decompose right | **3** |
| only direct right    | 3     |
| total                | 50    |

The 3-vs-3 only-X-right split is itself a finding: decomposed
reasoning helps on chained-entity questions but also costs DIRECT-
solvable items by inducing over-cautious refusals or speculative
intermediate steps. The video should not oversell DECOMPOSE as
strictly better — only as better on the failure mode under test.

## Curated cases

### Case 1 — Edward James Olmos / Miami Vice

**Question:** *C. Bernard Jackson founded the center that started the
career of which actor, who played the part of Marty Castillo in
"Miami Vice"?*

- DIRECT prompt answer: **John Ortiz**  ❌
- DECOMPOSE prompt answer: **Edward James Olmos**  ✓
- Gold answer: *Edward James Olmos*

Why it's strong: classic two-hop bridge — center founder → notable
alumnus, with a specific role anchor ("Marty Castillo") that lets
the audience verify the answer at a glance. DIRECT visibly latched
onto "Marty Castillo" and produced the wrong actor; DECOMPOSE
walked the bridge.

### Case 2 — The Sound of Music / Ruth Leuwerik

**Question:** *What musical was inspired by the films that included
Ruth Leuwerik's best known role?*

- DIRECT prompt answer: **Elisabeth**  ❌
- DECOMPOSE prompt answer: **The Sound of Music**  ✓
- Gold answer: *The Sound of Music*

Why it's strong: the answer is an iconic cultural artefact, and
the bridge ("Ruth Leuwerik's best known role" → "Maria von Trapp in
*The Trapp Family*" → "inspired *The Sound of Music*") is the
textbook chained-entity shape the hypothesis is about. The wrong
DIRECT answer is also a real musical, which makes the failure look
like confident-but-wrong rather than refusal.

### Case 3 — Cartoon Network / Gerald Bald Z

**Question:** *The show featuring a young boy named Gerald Bald Z
premiered on what TV channel?*

- DIRECT prompt answer: **Nickelodeon**  ❌
- DECOMPOSE prompt answer: **Cartoon Network**  ✓
- Gold answer: *Cartoon Network*

Why it's strong: short, vertical-friendly. The wrong answer
(Nickelodeon) is the obvious default for "kids' show with a
character named Gerald" — DIRECT pattern-matches on the genre and
gets the channel wrong. DECOMPOSE has to actually identify the show
before answering the channel question.

## Selection rationale

Per the brief's selection criteria:

1. **Question length** — case 2 and case 3 are 13 words each. Case
   1 is 23 words; the brief suggested under 18 but allowed longer
   for QA. Case 1's structure ("X founded the center that started
   the career of Y, who played Z in W") is self-evidently
   chained, so the length earns its keep.
2. **Self-evidently multi-hop** — every case has a visible bridge
   entity (the center, Ruth Leuwerik's role, the show name) that
   the question forces the answerer to traverse.
3. **Surface-level interesting** — Miami Vice, The Sound of Music,
   Cartoon Network are all instantly recognizable.
4. **Diverse structure** — person-finding, musical-finding,
   channel-finding. No two cases share an answer type.

## Video layout reference

```
Question: <text>

Direct prompt:     <wrong answer>     ❌
Decomposed prompt: <right answer>     ✓
                                      (gold: <gold answer>)
```
