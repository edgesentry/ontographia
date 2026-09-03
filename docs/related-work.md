# Related work

Adjacent research improves **LLM → Cypher** (or general LLM decoding) along two axes Ontographia cares about: **what context the model sees**, and **how much / how often to verify and resample**. Ontographia shares the end goal (safe, accurate Cypher) but places the LLM one layer earlier.

Pipeline and design principles: [Architecture](architecture.md).

| Work | Focus | Relation to Ontographia |
|------|--------|-------------------------|
| [Enhancing Text2Cypher with Schema Filtering](https://arxiv.org/html/2505.05118) (Ozsoy, 2025) | Prompt-time schema pruning (exact-match, NER-masked, similarity) to cut noise, hallucinations, and token cost when the model writes Cypher | Complementary for the **app / agent layer**: the same idea applies when building Intent prompts from large ontologies (`build_initial_user_message` and friends). Ontographia’s core still never receives raw Cypher from the model. |
| [Explore iterative refinement for Text2Cypher](https://neo4j.com/blog/developer/iterative-refinement-for-text2cypher/) (Ozsoy, 2025) | Post-generation **verify → correct** loops over Cypher (rule-based, CyVer, execution-based, LLM-based) | Parallel concern, different object: Ontographia validates and repairs at the **Intent / COM** boundary, then emits Cypher deterministically. A refinement loop over Intent (then re-compile) fits this architecture better than rewriting emitted Cypher. |
| [Make Every Penny Count: Difficulty-Adaptive Self-Consistency](https://aclanthology.org/2025.findings-naacl.383.pdf) (Wang et al., NAACL 2025 Findings) | Allocate self-consistency samples by **prior + posterior difficulty** so easy queries avoid redundant resampling | Orthogonal cost control for Intent generation: simple intents can take one constrained decode; hard ones (large ontology, ambiguous terms) can spend more samples or a fuller schema. Does not replace ontology validation or deterministic emission. |
| [Learning How Hard to Think: Input-Adaptive Allocation of LM Computation](https://openreview.net/pdf?id=6qUUgw9bAZ) (Damani et al., ICLR 2025; [arXiv:2410.04707](https://arxiv.org/abs/2410.04707)) | Predict which inputs benefit from extra test-time compute (adaptive best-of-*k*, routing expensive vs cheap decoders) | Same budgeting idea for the agent layer: skip expensive Intent refinement / execution feedback when a first Intent already validates and compiles cleanly. Complements Ontographia’s cheap deterministic core rather than competing with it. |

## Approach contrast

- **Schema filtering & Cypher refinement** assume the LLM produces Cypher and mitigate failure modes around that choice (smaller schema in the prompt; check/fix the query afterward).
- **Difficulty-adaptive decoding** (DSC, input-adaptive allocation) assume expensive multi-sample or multi-verifier loops and ask *when* to spend that compute. The Text2Cypher iterative-refinement post cites both as motivation to skip verification on simple queries.
- **Ontographia** keeps the LLM on schema-constrained **Intent JSON**, uses the ontology as the source of truth for names and structure, binds filter values as parameters, and compiles via a controlled AST. Syntax and injection risk leave the model’s job; remaining hard problems (wrong field among many plausible ones) sit in Intent generation — where schema filtering, Intent-level refinement, and difficulty-adaptive spend are natural next steps, not Cypher rewriting.

Measured stress-test baseline (silent wrong fields still compile on large ontologies): [Evaluation — Track A](evaluation.md#track-a--distractor-ontology-stress-test).
