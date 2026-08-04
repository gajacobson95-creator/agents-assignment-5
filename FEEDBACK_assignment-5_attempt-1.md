## Grade: 90 / 100

**Assignment:** Financial Approval — Human-in-the-Loop (LangGraph + CopilotKit + LangSmith)  
**Attempt:** 1 of 2  ·  **Graded:** 2026-08-04  ·  Commit `7f2075c`

### Score breakdown
| Criterion | Max | Earned | Notes |
|-----------|-----|--------|-------|
| langgraph_workflow | 35 | 33 | All 8 nodes and 6 routers correct, graph.py:28 fully wired and compiled with the checkpointer. Notably, every node appends to a copied decisions list using the exact {stage, decision, reasoning} schema the Layer 3 audit evaluator expects, and process_request emits approval_path and human_reviews so the eval layer has real data to score. Deduction: _parse_decision defaults to approved on a malformed payload (see below), and assess_risk is gated on an env-var key check rather than try/except alone. (`backend/agent/nodes.py:182`) |
| safety_guardrails | 20 | 20 | validate_request enforces amount, ceiling, department, all three length limits and injection scanning, and tolerates None values throughout. validate_amount additionally coerces non-numeric input rather than raising. sanitize_output masks all four PII classes and mask_financial_details handles dollars and account numbers. (`backend/guardrails/input_validator.py:27`) |
| langsmith_eval | 20 | 20 | Correct ordered-level adjacency banding with a membership guard, and both evaluators default every argument and tolerate reference_outputs arriving via kwargs. They also return a reasoning string alongside the score, which the runner does not require but which makes results readable. (`backend/evaluation/evaluators.py:14`) |
| three_layer_eval | 50 | 40 | Layer 1 is fully correct and the dataset generator is unusually robust operationally — a deterministic _fallback_dataset means generation works with no API key, and validation is complete. Deduction: Layer 2 contains no RAGAS at all (overlap ratio, weighted status+reasoning score, and keyword counting stand in for ToolCallAccuracy, AgentGoalAccuracyWithReference and TopicAdherence), and Layer 3's hallucination evaluator (line 192) is a fixed suspicious-phrase list rather than RAGAS Faithfulness or an LLM judge. (`backend/evaluation/three_layer_evaluators.py:92`) |
| Integrity deduction | — | 0 | Provided files unmodified |
| **Total** | **100** | **90** | |

### What went well
- Excellent state design: decisions entries carry stage/decision/reasoning exactly as the audit evaluator expects, and process_request and handle_rejection both emit approval_path and human_reviews — so the Layer 1 evaluators can actually score this graph's real output.
- The graph runs without an API key: assess_risk derives a threshold-based risk level and only calls the LLM when a key is present, and the dataset generator falls back to a deterministic case set.
- Guardrails are defensively written throughout — None-tolerant text handling and numeric coercion in validate_amount mean malformed input produces a clean rejection message rather than a TypeError.
- Every evaluator returns a reasoning string, making a failed eval run self-explanatory.

### What to improve (actionable)
- backend/agent/nodes.py:33 — _parse_decision(raw, default_approved=True) means an unparseable or non-dict resume payload is treated as an approval. On a human approval gate for financial requests this fails open; defaulting to False would fail closed, which is the safer direction for exactly this kind of control.
- backend/evaluation/three_layer_evaluators.py:92 — Layer 2 carries 12 points for RAGAS metrics and none of the three evaluators import RAGAS. Your heuristics are reasonable, but the intended shape is a real ToolCallAccuracy/AgentGoalAccuracyWithReference/TopicAdherence call with the heuristic kept behind a try/except fallback.
- backend/evaluation/three_layer_evaluators.py:192 — the hallucination check scans for five fixed phrases such as 'cfo said' and 'board approved'. That cannot generalise; the spec allows either RAGAS Faithfulness or a short LLM-judge prompt, and you already have get_llm() wired elsewhere.
- backend/evaluation/dataset_generator.py:163 — when the LLM path fails, generate_eval_dataset silently returns the canned fallback dataset. The resilience is good, but logging which path produced the data would keep an eval run honest about whether it exercised LLM-generated cases.
- backend/evaluation/three_layer_evaluators.py:178 — the policy review check uses human_reviews >= required_reviews, so an over-reviewed request still passes. The spec asks for the required count, so an equality check would catch unnecessary escalation too.

### Automated checks
- ✅ All required files implemented
- ✅ Provided files unmodified
- ✅ 0/0 output artifacts committed
- ✅ Reflection 535 words

### Resubmission
You may resubmit **once**. Push fixes to this repo, then notify the instructor; we'll re-grade as **Attempt 2 (final)**. This is attempt 1 of 2.

---
*Graded automatically with Claude Code against the course rubric. Questions → contact the instructor.*


---
<sub>🔎 **Autograder record** — attempt 1 of 2 · graded at commit `7f2075c` · delivered 2026-08-04T04:36:03Z. Commits pushed to `main` after this timestamp are treated as a resubmission.</sub>
