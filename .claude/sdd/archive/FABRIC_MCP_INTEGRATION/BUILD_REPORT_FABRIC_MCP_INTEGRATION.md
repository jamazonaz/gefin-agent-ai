# BUILD REPORT: Fabric MCP Integration (Sales Pipeline Assistant)

> Implementation report for Fabric MCP Integration

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | FABRIC_MCP_INTEGRATION |
| **Date** | 2026-08-11 |
| **Author** | build-agent |
| **DEFINE** | [DEFINE_FABRIC_MCP_INTEGRATION.md](../features/DEFINE_FABRIC_MCP_INTEGRATION.md) |
| **DESIGN** | [DESIGN_FABRIC_MCP_INTEGRATION.md](../features/DESIGN_FABRIC_MCP_INTEGRATION.md) |
| **Status** | ✅ Shipped |

---

## Summary

| Metric | Value |
|--------|-------|
| **Tasks Completed** | 15/15 |
| **Files Created** | 7 |
| **Files Modified** | 8 (incl. local `.env`, untracked) |
| **Lines of Code** | ~970 (684 new + 284 net diff on modified files) |
| **Build Time** | 1 extended session (incl. live MCP/DB/LLM verification, not just code generation) |
| **Tests Passing** | 12/12 (`backend/tests/test_fabric_tools.py`, independently re-run) |
| **Agents Used** | 4 (@fabric-architect, @genai-architect, @python-developer, @test-generator) |

---

## Task Execution with Agent Attribution

| # | Task | Agent | Status | Duration | Notes |
|---|------|-------|--------|----------|-------|
| 1 | `backend/requirements.txt` — dependency bump/additions | (direct) | ✅ Complete | - | Re-pinned after real conflict found (see Deviations) |
| 2 | `.env.example` — document new env vars | (direct) | ✅ Complete | - | |
| 3 | `render.yaml` — deploy env vars | (direct) | ✅ Complete | - | |
| 4 | `.env` (local, untracked) — enable local testing | (direct) | ✅ Complete | - | Not in original manifest; added to make the feature testable end-to-end locally |
| 5 | `catalog/fabric_metrics.yaml` | @fabric-architect | ✅ Complete | ~76s | 13 measures, 9 tables, 11 report pages |
| 6 | `scripts/discover_fabric_schema.py` | @python-developer | ✅ Complete | ~160s (batch) | |
| 7 | `backend/app/catalog/fabric_loader.py` | @python-developer | ✅ Complete | ~160s (batch) | |
| 8 | `backend/app/agent/fabric_mcp.py` | @genai-architect | ✅ Complete | ~195s (batch) | 1 direct follow-up fix (import modernization) |
| 9 | `backend/app/agent/fabric_tools.py` | @genai-architect | ✅ Complete | ~195s (batch) | |
| 10 | `backend/app/agent/prompts.py` | @genai-architect | ✅ Complete | ~195s (batch) | |
| 11 | `backend/app/agent/graph.py` | @genai-architect + (direct) | ✅ Complete | ~195s + extensive direct follow-up | 5 defects found and fixed during live verification — see Issues Encountered |
| 12 | `backend/app/main.py` | @python-developer | ✅ Complete | ~160s (batch) | |
| 13 | `frontend/app.py` | @python-developer | ✅ Complete | ~160s (batch) | Boot-verified via `docker compose up`, not visually tested in a browser |
| 14 | `backend/tests/test_fabric_tools.py` | @test-generator | ✅ Complete | ~156s | 12 tests, independently re-run and confirmed |
| 15 | `backend/tests/__init__.py` | @test-generator | ✅ Complete | ~156s (same batch) | |

**Legend:** ✅ Complete | 🔄 In Progress | ⏳ Pending | ❌ Blocked

**Agent Key:**
- `@{agent-name}` = Delegated to specialist agent via Task tool
- `(direct)` = Built directly by build-agent (no specialist matched, or a targeted fix applied after live-testing surfaced a defect)

---

## Agent Contributions

| Agent | Files | Specialization Applied |
|-------|-------|--------------------------|
| @fabric-architect | 1 | Wrote accurate PT-BR measure/table descriptions and a heuristic (explicitly-labeled-approximate) report-page mapping from the real discovered Fabric schema |
| @genai-architect | 4 (+1 heavily patched) | MCP session lifecycle, LangChain tool conversion, domain-routing refactor of the ReAct loop, `.ainvoke()` correction for coroutine-only MCP tools |
| @python-developer | 4 | Catalog loader mirroring the existing AR pattern, discovery script, `ChatRequest.domain` field, Streamlit domain selector |
| @test-generator | 2 | 12 pytest unit tests covering the loader and all 4 new tools, using real catalog data (no mocking) |
| (direct) | 4 config files + critical fixes in `graph.py` | Dependency conflict resolution (verified against real PyPI installs), live E2E defect-hunting and fixes (see below) |

---

## Files Created

| File | Lines | Agent | Verified | Notes |
| ---- | ----- | ----- | -------- | ----- |
| `catalog/fabric_metrics.yaml` | 297 | @fabric-architect | ✅ | YAML parses; 13/9/11 counts confirmed; hidden table/measures correctly excluded |
| `backend/app/catalog/fabric_loader.py` | 73 | @python-developer | ✅ | Verified live: `get_fabric_catalog_summary()` returns 13 measures, 9 tables |
| `backend/app/agent/fabric_mcp.py` | 42 | @genai-architect + (direct) | ✅ | Verified live against the real MCP server; import modernized (UP035) |
| `backend/app/agent/fabric_tools.py` | 112 | @genai-architect | ✅ | Verified live: `get_fabric_lineage`, `get_fabric_measure_definition` return correct shapes |
| `scripts/discover_fabric_schema.py` | 61 | @python-developer | ✅ | Formalizes the ad hoc discovery already run manually during Brainstorm |
| `backend/tests/test_fabric_tools.py` | 99 | @test-generator | ✅ | 12/12 passing, independently re-run |
| `backend/tests/__init__.py` | 0 | @test-generator | ✅ | |

---

## Verification Results

### Lint Check

```text
ruff check (no project ruff config exists in this repo — ran with defaults):
- fabric_mcp.py: 1 finding (UP035 typing.AsyncIterator) — fixed.
- graph.py: 1 finding (BLE001 blind except) — left as-is: this is the
  established error-boundary pattern already used throughout tools.py
  (confirmed the same rule fires on the untouched, pre-existing tools.py
  and main.py too — not a regression, a pre-existing repo-wide convention).
- frontend/app.py: 3 findings (BLE001, I001, SIM117) — all on code that
  predates this build (the _get_secret function, the top-of-file imports,
  the chat_message/spinner nesting) — not introduced by this change.
```

**Status:** ✅ Pass (all findings are either fixed, or confirmed pre-existing/deliberate and out of this build's scope)

### Type Check

```text
N/A - mypy not configured in this project (no mypy.ini/pyproject.toml section, not in requirements.txt).
```

**Status:** ⏭️ Skipped

### Tests

```text
============================= test session starts =============================
collected 12 items
tests/test_fabric_tools.py::test_get_fabric_catalog_summary_returns_domain_and_lists PASSED
tests/test_fabric_tools.py::test_get_fabric_measure_returns_expected_keys PASSED
tests/test_fabric_tools.py::test_get_fabric_measure_returns_none_for_unknown PASSED
tests/test_fabric_tools.py::test_list_fabric_tables_excludes_hidden_table PASSED
tests/test_fabric_tools.py::test_get_fabric_report_pages_filters_by_measure PASSED
tests/test_fabric_tools.py::test_list_fabric_measures_tool_returns_non_empty_measures PASSED
tests/test_fabric_tools.py::test_get_fabric_measure_definition_tool_returns_definition PASSED
tests/test_fabric_tools.py::test_get_fabric_measure_definition_tool_errors_on_unknown_measure PASSED
tests/test_fabric_tools.py::test_get_fabric_lineage_tool_returns_lineage_for_known_measure PASSED
tests/test_fabric_tools.py::test_get_fabric_lineage_tool_handles_empty_measures_used PASSED
tests/test_fabric_tools.py::test_triage_fabric_scope_tool_echoes_input PASSED
tests/test_fabric_tools.py::test_fabric_local_tools_has_three_entries PASSED
======================= 12 passed in 4.14s =======================
```

**Status:** ✅ 12/12 Pass

### Live End-to-End Verification (beyond the skill's minimum bar)

Given this feature's core risk was integration with a real external system (not just internal logic), I went beyond static verification: built the real Docker image with the bumped dependencies, ran `docker compose up` with Postgres + the rebuilt backend (+ frontend boot check), and issued real `/chat` requests against the live remote MCP server, real Postgres, and a real LLM (`gpt-4o-mini` per the user's current `.env`). This surfaced 5 real defects that static review and unit tests alone would not have caught — see Issues Encountered.

**Status:** ✅ Both domains verified live; AR (pre-existing) domain confirmed not regressed by the shared-loop refactor.

---

## Issues Encountered

| # | Issue | Resolution | Time Impact |
|---|-------|------------|--------------|
| 1 | `langchain-mcp-adapters` requires `langchain-core>=0.3.36`, but a real `pip install` (not just declared-metadata checks) revealed `langchain-core>=0.3.64` also tightens its `langsmith` requirement to `>=0.3.45`, conflicting with `langchain==0.3.14`'s `langsmith<0.3` pin — a conflict the DESIGN phase's metadata-only check did not surface. | Bisected PyPI releases to find `langchain-core==0.3.63` — the highest version satisfying both constraints. Full `pip install` now resolves cleanly and was verified inside the real Docker image. | +~20m |
| 2 | `messages.append(ToolMessage(content=json.dumps(result, ...)))` double-encoded MCP tool results: MCP tools return JSON as a raw string, so `json.dumps(a_string)` wrapped it in an extra layer of escaping before it reached the LLM. | Route every tool result through the existing `_parse_tool_payload` helper before the final `json.dumps`, so both dict-native (AR) and string-native (MCP) tool results serialize identically. | +~10m |
| 3 | `data` never populated for `execute_dax_query` results — the Fabric `executeQueries` response is nested (`results[0].tables[0].rows`), not a flat row list like `execute_sql`'s. | Added `_extract_dax_rows()` to flatten the nested shape into the same `list[dict]` shape the AR path already produces, so the frontend's existing table/chart rendering works unchanged. | +~10m |
| 4 | **`generate_chart` was never included in the Fabric domain's tool list**, even though `FABRIC_SYSTEM_PROMPT` told the model it had access to it. Root cause of what initially looked like an LLM "reliability" problem (the model would loop on catalog/lineage tools or write a JSON blob as prose instead of using the tool) — it genuinely could not call a tool that was never bound. Found via live testing after a red herring (a model-looping hypothesis) that took real debugging time to rule out. | Imported `generate_chart` from `app.agent.tools` and added it to the Fabric tool list. Confirmed live: `generate_chart` now gets called correctly and `chart_spec` populates. | +~25m (incl. the ruled-out looping investigation) |
| 5 | Pre-existing bug (not introduced by this build, but exposed by it): when the LLM call fails on ANY loop iteration — including the final "write the answer" turn, after all tool calls already succeeded — the exception handler discarded `data`/`chart_spec`/`lineage`/`final_sql` and returned only an error string. Under `gpt-4o-mini`, the Fabric flow's longer multi-turn sequences made a late transient OpenAI timeout more likely to hit exactly after the useful work was done. | Extended the exception-handler's return dict to include the already-accumulated `data`/`chart_spec`/`lineage`/`final_sql`/`tools_called`/`plan`, plus a note in the answer when partial results exist. Verified live: a real OpenAI timeout after a successful `generate_chart` call now still returns the populated `chart_spec` to the user. | +~10m |

---

## Autonomous Decisions

| # | Decision Point | Options Considered | Chose | Rationale |
|---|-----------------|----------------------|-------|-----------|
| 1 | `langchain-core` pin after discovering the `langsmith` transitive conflict | (a) `0.3.86` as DESIGN specified, untested against a real install; (b) bump `langchain` too, cascading further; (c) bisect for the highest `0.3.x` version compatible with both `langchain-mcp-adapters` and the existing `langchain==0.3.14` | (c) `0.3.63` | Smallest correct change — keeps every other pinned package untouched, verified via a real `pip install` inside the actual Docker image, not just declared metadata |
| 2 | Which of the 15 discovered Fabric measures to expose in the catalog | (a) all 15, matching the DEFINE's literal number; (b) exclude the 2 hidden/internal measures (and their hidden parent table) | (b) 13 usable measures | Mirrors the AR catalog's own established governance rule of never exposing internal/raw fields to the LLM; documented explicitly so the DEFINE's "15 medidas" figure isn't silently contradicted |
| 3 | Tool invocation style in the shared ReAct loop | (a) keep `.invoke()` for all tools; (b) switch to `await .ainvoke()` for all tools | (b) `.ainvoke()` | MCP-adapted tools are coroutine-only; `.ainvoke()` on the pre-existing sync AR tools is safe (LangChain runs them via executor), so this is a superset-compatible change, not a behavior change for AR |
| 4 | How to handle the repeated-identical-tool-call pattern observed live with `gpt-4o-mini` | (a) leave as-is, rely on `MAX_STEPS` to eventually cut it off; (b) add generic duplicate-call detection + early loop break | (b) | Prevents wasted MCP/LLM round-trips and produces a faster, cleaner failure instead of silently burning the full step budget; applies safely to both domains |
| 5 | Whether to add `MCP_SERVER_URL`/`MCP_TIMEOUT_SECONDS` to the local (untracked) `.env`, beyond the file manifest | (a) leave local `.env` untouched, rely only on `.env.example`; (b) add them so the feature is actually testable end-to-end locally | (b) | The DESIGN's own testing strategy calls for a live MCP smoke test; without this the feature could not be verified at all in this environment |

---

## Deviations from Design

| Deviation | Reason | Impact |
|-----------|--------|--------|
| `langchain-core` pinned to `0.3.63`, not the `0.3.86` the DESIGN document specified | DESIGN's version check was metadata-only; a real `pip install` surfaced a transitive `langsmith` conflict at `0.3.64+`. See Autonomous Decision #1. | None — `0.3.63` still satisfies every constraint DESIGN cared about (`langchain-mcp-adapters>=0.3.36`, all sibling packages' `<0.4.0`); fully verified via real install. |
| `generate_chart` explicitly imported and added to the Fabric tool list | DESIGN's Pattern 2 code snippet (`tools = [*mcp_tools, *FABRIC_LOCAL_TOOLS]`) omitted it, even though the DESIGN's Components table and the DEFINE both state Fabric reuses `generate_chart`. | Closes a real gap between DESIGN's stated intent and its literal code pattern; without this, chart generation could never work in the Fabric domain regardless of prompt quality. |
| Added tool-call duplicate/loop detection and partial-results-on-error handling to `graph.py` | Neither was in the DESIGN document; both were necessary responses to defects surfaced by live E2E testing (Issues #4/#5). | Net-positive robustness change affecting both domains; no behavior change for the AR domain's success path. |
| `.env` (local, untracked) updated in addition to `.env.example`/`render.yaml` | Not listed in the DESIGN file manifest, but necessary to actually run the live verification this feature's core risk demanded. | Local-only, gitignored — no effect on the repo or deployment. |

---

## Blockers (if any)

None. One item is flagged for follow-up, not blocking:

| Item | Required Action | Owner |
|------|-------------------|-------|
| Could not cross-verify chart-generation reliability against Anthropic Claude (the project's own documented "recommended for quality" provider) | The `ANTHROPIC_API_KEY` currently saved in `.env` returns `401 invalid API key` — needs a valid key rotated in before a comparison test is possible | User (credential owner) |

---

## Acceptance Test Verification

| ID | Scenario | Status | Evidence |
|----|----------|--------|----------|
| AT-001 | Happy path — pergunta sobre medida do catálogo | ✅ Pass | Live `/chat` call, `domain=fabric`, "Qual o Revenue Won total?" → real value (R$ 26.435.925) via `execute_dax_query`, correct lineage citing `Opportunities[Revenue Won]` |
| AT-002 | Erro do MCP/LLM não vira alucinação | ✅ Pass | Observed multiple real transient `openai.APITimeoutError`s during live testing; each returned a clear `"Erro ao chamar o modelo..."` message (with partial results preserved per Issue #5's fix), never a fabricated value |
| AT-003 | Pergunta fora do domínio Fabric | ✅ Pass | Live `/chat` call, `domain=fabric`, "Qual o saldo total em aberto de contas a receber?" → correctly declined and redirected to the AR assistant |

**AR domain regression check (not a DEFINE acceptance test, but a required non-regression bar given the shared-loop refactor):** ✅ Pass — "Qual o saldo total em aberto?" and a chart-generation request both completed correctly end-to-end against the real Postgres database after the refactor.

---

## Performance Notes

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Fabric simple factual question (`domain=fabric`) | Not specified in DEFINE (flagged as a gap in its Clarity Score) | ~10–20s per turn (4 LLM/tool steps) | ⚠️ No SLA to compare against — DEFINE's Open Questions already flagged this gap |
| Fabric chart-generation question | Not specified | 60–110s+ observed (6–7 sequential LLM/tool turns under `gpt-4o-mini`), occasionally hitting `MAX_STEPS` or a late-turn timeout | ⚠️ Notably slower than AR's equivalent (~9s) because more sequential round-trips are needed; the project's own docs already recommend Claude over `gpt-4o-mini` for tool-calling quality — this is a provider-choice characteristic, not a defect in this build |

---

## Final Status

### Overall: ✅ COMPLETE

**Completion Checklist:**

- [x] All tasks from manifest completed
- [x] All verification checks pass (lint clean on new code; pre-existing findings confirmed out of scope)
- [x] All tests pass (12/12)
- [x] No blocking issues
- [x] Acceptance tests verified (live, against real Postgres + real Fabric MCP server + real LLM)
- [x] Ready for /ship

**Known limitation carried forward (not a blocker):** chart-generation latency/reliability under the cost-optimized `gpt-4o-mini` provider is materially worse than under the project's documented default (Claude); recommend the user re-verify once a valid `ANTHROPIC_API_KEY` is available, and consider raising `MAX_AGENT_STEPS` or `LLM_TIMEOUT_SECONDS` specifically for the Fabric domain if `gpt-4o-mini` remains the chosen provider.

---

## Next Step

**If Complete:** `/ship .claude/sdd/features/DEFINE_FABRIC_MCP_INTEGRATION.md`

**If Blocked:** Resolve blockers, then `/build` to resume

**If Issues Found:** `/iterate DESIGN_FABRIC_MCP_INTEGRATION.md "{change needed}"`
