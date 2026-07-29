"""ROADMAP.md Phase 3, Step 3.3 -- the "Chef" conversational tool-calling
agent.

Package layout (per the execution spec, docs/PHASE3_HITL_CHEF_SPEC.md
section 2.1):
- `chef_agent.py` -- the LangGraph ReAct-style loop (llm_node <-> tools_node)
  + the deterministic response gate.
- `tools.py` -- the 7 tool functions, thin Pydantic-in/out wrappers over
  existing `app.services.*` modules. No tool reimplements any service
  logic; every safety-relevant decision still comes from
  `app.services.constraint_engine` alone.
- `prompts.py` -- the system prompt (safety contract + prompt-injection
  hardening framing) and the `<tool_output>` delimiter template.
- `memory.py` -- thread-transcript reconstruction (from `ChatMessage` rows)
  and the `agent_notes` read path the agent's `get_user_context` tool uses.

Invariant #1 (CLAUDE.md): the LLM in this package NEVER decides an allergy,
diet, or nutrition-verification outcome. It may only ask deterministic tools
for those answers and relay them; the response gate in `chef_agent.py` is
the deterministic backstop that enforces this even if the LLM's own text
tries to skip a safety check.
"""
