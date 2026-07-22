# Assignment 5: Reflection

## Part 1: LangGraph Workflow

1. I designed the workflow as an eight-node pipeline: request submission, risk assessment, manager review, budget validation, finance review, executive sign-off, processing, and rejection handling. The order follows the business escalation policy: validate first, assess risk second, then add human review only when the risk or budget status requires it.

2. The `interrupt()` pattern was useful because it keeps the workflow stateful while pausing for a human decision. The intuitive part was passing a clear review payload to the frontend. The challenging part was making each interrupt resume cleanly with either a dictionary decision or a JSON string decision from the UI.

3. Routing functions control the graph by turning business policy into conditional edges. They are important because approval systems are not linear: low-risk requests can skip human review, medium-risk requests need manager review, high-risk requests need finance review, and critical requests need executive sign-off.

## Part 2: Safety Guardrails

1. The input validation protects against negative amounts, requests over the budget ceiling, invalid departments, oversized fields, SQL injection patterns, script injection, and code execution strings such as `os.system` or `__import__`. Remaining gaps include more sophisticated prompt injection and semantic fraud detection that would require stronger classifiers or policy engines.

2. PII masking uses regular expressions for SSNs, credit cards, email addresses, and phone numbers. The trade-off is that regex masking is fast and predictable, but it can miss unusual formats or over-mask text that only resembles sensitive data.

3. Output filtering matters because sensitive information can appear after processing, summarization, tool output, or human comments. Even validated inputs do not guarantee safe outputs in a financial workflow.

## Part 3: CopilotKit Frontend

1. The `useLangGraphInterrupt` hook connects frontend review panels to backend graph interrupts by rendering approval UI when the graph pauses and sending the reviewer decision back through `resolve()`.

2. When an approval interrupt fires, the user sees a modal with request context, risk level, budget information, and approve/reject controls. This makes the HITL decision explicit and actionable.

3. The main integration challenge is keeping the frontend decision payload aligned with the backend state expected by the LangGraph nodes.

## Part 4: LangSmith Evaluation

1. The risk accuracy evaluator gives full credit for exact risk matches, half credit for adjacent risk levels, and no credit for non-adjacent errors. This reflects that low vs. medium is less severe than low vs. critical.

2. Evaluation is important because production AI systems need measurable reliability, not just plausible responses. I would extend the suite with more adversarial prompts, department-specific budget cases, and long-running workflow replay tests.

3. The evaluation framework makes it clear whether failures come from business routing, agent behavior, or safety/compliance issues.

## Bonus Features (if implemented)

No bonus features were implemented. I focused on the required workflow, guardrails, and evaluation framework.

## Key Learnings

- Human-in-the-loop workflows require careful state design.
- Safety needs to exist at both input and output boundaries.
- Evaluation should cover business correctness, agent behavior, and compliance separately.

## Ideas for Improvement

- Add persistent audit logs with timestamps and reviewer identity.
- Add a dashboard for pending reviews and approval bottlenecks.
- Add stronger semantic prompt-injection detection.
