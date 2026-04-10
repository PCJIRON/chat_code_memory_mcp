# Plan Validation: 6-01

## Result: PASS_WITH_NOTES

The Phase 6 plan is well-structured and mostly ready for execution. The 16 tasks across 5 waves cover all requirements from 6-CONTEXT.md with clear atomicity, testability, and verification criteria. Two MAJOR items and three MINOR items should be addressed before or during execution.

---

## Requirement Coverage

| Requirement (from 6-CONTEXT.md) | Covered By | Status |
|--------------------------------|-----------|--------|
| Fix auto-retrieve (query extraction) | T1, T2, T7 | ✅ |
| Dual context injection (system prompt + response append) | T6, T7 | ⚠️ Partial |
| Semantic classifier (sentence-transformers centroids) | T3, T13 | ✅ |
| Unified ChromaDB storage (type metadata) | T4, T10, T14 | ✅ |
| Full file change tracking (path+time+type+symbols+snippets) | T8, T9, T10 | ✅ |
| HybridContextBuilder (ChromaDB + FileGraph routing) | T5, T11, T12 | ✅ |
| `get_context` returns actual data (not stub) | T5, T12 | ✅ |
| File change history queryable by date range | T10 | ✅ |
| All 224 existing tests still pass | T2, T14, T15 | ✅ |
| New tests (target 280+) | T13–T16 | ✅ |
| README updated with hybrid behavior | T16 | ✅ |
| Intent classifier 90%+ accuracy | T3, T13 | ⚠️ Implicit |

---

## Task Quality

| Task | Atomic? | Testable? | Verified? | Status |
|------|---------|-----------|-----------|--------|
| T1: Fix query extraction | ✅ | ✅ | ✅ | Good — single focused change |
| T2: Verify monkey-patch | ✅ | ✅ | ✅ | Good — integration test |
| T3: IntentClassifier | ✅ | ✅ | ✅ | Good — new class, clear API |
| T4: ChatStore type-aware | ✅ | ✅ | ✅ | Good — backward compatible |
| T5: HybridContextBuilder | ✅ | ✅ | ✅ | Good — replaces stub |
| T6: Update ContextInjector | ✅ | ✅ | ✅ | Good — delegation change |
| T7: Wire into mcp_server | ✅ | ✅ | ⚠️ | Good — but touches wiring logic |
| T8: FileGraph hooks | ✅ | ✅ | ✅ | Good — optional hook |
| T9: FileWatcher hooks | ✅ | ✅ | ✅ | Good — backward compatible |
| T10: query_file_changes | ✅ | ✅ | ✅ | Good — new method |
| T11: FileGraph structural queries | ✅ | ✅ | ✅ | Good — extends T5 |
| T12: Update get_context tool | ✅ | ✅ | ✅ | Good — tool registration |
| T13: IntentClassifier tests | ✅ | ✅ | ✅ | Good — 12+ tests planned |
| T14: ChatStore file change tests | ✅ | ✅ | ✅ | Good — 10+ tests planned |
| T15: Integration tests | ✅ | ✅ | ✅ | Good — 8+ tests planned |
| T16: README update | ✅ | ✅ | ✅ | Good — documentation |

---

## Issues Found

### MAJOR (should fix — can address during execution)

**M1: Dual injection not fully implemented in plan**
- **Issue:** 6-CONTEXT.md Decision 1 explicitly commits to "Both system prompt + response append (dual injection)". The plan only addresses response append (T6 returns `"[Auto-Context]\n{content}\n[Sources: ...]"` format, T7 wires it into monkey-patch response). There is **no task** for system prompt injection via `instructions` parameter.
- **Impact:** The plan only delivers half of Decision 1. Response-only injection was the existing approach that "LLM ignores it" per the problem statement.
- **Fix suggestion:** Add a task (or expand T7) to set `mcp._mcp_server.instructions` with a dynamic-capable pattern. Per 6-RESEARCH.md Approach 1A, `instructions` is static at startup. Either: (a) accept static instructions describing the auto-context capability, or (b) document that dual injection is deferred to a future phase with a note in 6-01-SUMMARY.md. At minimum, update T6/T7 validation criteria to explicitly mention system prompt injection status.

**M2: T5 and T11 have a circular dependency concern**
- **Issue:** T5 says "queries FileGraph for structural context when file intent detected" but T11 says "Enhance `HybridContextBuilder` with FileGraph structural queries". T5's validation criteria includes FileGraph querying, but T11 is in Wave 4 while T5 is in Wave 2. This means T5 either has a stub FileGraph call (making T5 incomplete) or T11 is redundant.
- **Impact:** Either T5 overpromises (claims FileGraph integration but doesn't deliver) or T11 duplicates work already done in T5.
- **Fix suggestion:** Clarify the split. Either: (a) T5 handles ChromaDB routing only, T11 adds FileGraph queries (clean separation), or (b) T5 includes both and T11 is removed. Recommendation: Option (a) — update T5 validation to remove FileGraph mentions, move them to T11 where they belong. Update the dependency graph: T11 depends on T5 (HybridContextBuilder exists) but T5 does NOT depend on FileGraph queries.

### MINOR (nice to fix)

**m1: T7 touches mcp_server.py which already has complex monkey-patch logic**
- **Issue:** T7 updates `_wire_interception()` to create `IntentClassifier` and `HybridContextBuilder` singletons. This function already handles `AutoSaveMiddleware` and `ContextInjector`. Adding two more singletons increases complexity. The plan doesn't specify what happens if the classifier or builder fails to initialize.
- **Fix suggestion:** Add error handling validation to T7: "If IntentClassifier fails to init (model unavailable), fall back to 'both' intent". Also consider a `get_classifier()` and `get_hybrid_builder()` module-level getter pattern consistent with `get_store()` and `get_graph()`.

**m2: T16 README update has no specific content requirements**
- **Issue:** T16 says "update README with Phase 6 hybrid context documentation" but doesn't specify what sections to add. The plan lists 5 validation bullets but no structure guidance.
- **Fix suggestion:** Add specific sections: "Hybrid Context System", "Intent Classification", "File Change Tracking", "Auto-Retrieve Behavior". Reference the architecture diagram from 6-CONTEXT.md.

**m3: Wave 3 T8-T10 dependency graph shows T10 as independent, but T14 (test) depends on T10**
- **Issue:** T10 adds `query_file_changes()` method. T14 tests it. The dependency graph correctly shows this, but the "Parallel Opportunities" section says "T8, T9, T10 can execute in parallel". T10 is independent of T8/T9 but T14 depends on all three. This is fine for execution but worth noting that T14 must wait for T10.
- **Fix suggestion:** No action needed — this is correctly modeled. Just a documentation nit.

### NIT (cosmetic)

**n1: Plan says "16 tasks" but Wave 3 has T8-T10 (3 tasks) and lists "FileGraph hooks, FileWatcher hooks, query method" — these are all file-change-related and could conceptually be one task split into three. Not a problem, just confirming atomicity is genuine.** → All three tasks are genuinely atomic (different files, different concerns). Good.

**n2: The "Expected test count: 280+" claim:** Plan says 224 existing + ~56 new = 280+. The actual test function count from grep is ~314 `def test_` patterns (though some may be helpers, not tests). The 224 figure comes from STATE.md Phase 5 results. The ~56 new count is: T13 (12) + T14 (10) + T15 (8) + T2 (1) + T4 (6) + T5 (10) + T6 (4) + T8 (4) + T9 (4) + T10 (6) + T11 (6) + T12 (4) = 75 new tests, not 56. The 280+ target is actually conservative — expect ~299+.

**n3: T3 validation says "Classification latency <100ms per query" but this is hard to enforce as a test assertion without timing infrastructure.** → Consider making this a non-blocking validation note rather than a hard test requirement.

---

## Wave-by-Wave Risk Assessment

| Wave | Risk Level | Assessment |
|------|-----------|------------|
| **Wave 1 (T1-T2)** | 🟢 Low | T1 is a single function fix with clear validation. T2 is a straightforward integration test. Highest impact/lowest risk wave. |
| **Wave 2 (T3-T7)** | 🟡 Medium | T3 (IntentClassifier) depends on sentence-transformers being available — model download could fail. T5 is the largest single task (HybridContextBuilder rewrite). T7 touches the most fragile code (monkey-patch wiring). Mitigation: T2 already verifies monkey-patch works before Wave 2 starts. |
| **Wave 3 (T8-T10)** | 🟢 Low | All three tasks add optional hooks with graceful degradation. No breaking changes to existing APIs. T10 is a straightforward new method. |
| **Wave 4 (T11-T12)** | 🟡 Medium | T11 adds FileGraph structural queries — depends on FileGraph being populated (may be empty in test env). T12 updates tool registration — low risk if T5 is solid. Main risk: FileGraph empty during integration tests (mitigated by graceful degradation). |
| **Wave 5 (T13-T16)** | 🟢 Low | Testing and documentation. T15 is the highest risk here (integration tests depend on all previous tasks working). If any earlier task is incomplete, T15 will fail. |

### Critical Path Risk
```
T1 → T2 → T3 + T4 → T5 → T6 → T7 → T8 → T11 → T12 → T15
```
The critical path has 11 sequential dependencies. Any delay in T5 (largest task) cascades through the entire plan. Recommend executing T3 and T4 in parallel where possible.

---

## Iteration History
- Attempt 1: PASS_WITH_NOTES (2 MAJOR, 3 MINOR, 3 NIT)

---

## Recommendation: APPROVE with conditions

The plan is **ready for execution** with the following conditions:

1. **Before Wave 2:** Clarify T5 vs T11 FileGraph responsibility split (M2). Update T5 validation to exclude FileGraph queries if T11 owns them.
2. **During Wave 2/3:** Document dual injection status (M1) — either implement system prompt injection or note as deferred.
3. **During Wave 2:** Add error handling to T7 for classifier initialization failures (m1).
4. **During Wave 5:** Update expected test count to ~300 (n2) — the plan underestimates new test count.

All MAJOR items can be addressed during execution without replanning. The plan's structure, atomicity, and test coverage are strong. The risk mitigations listed in the plan are appropriate and comprehensive.

**Green light to proceed with Phase 6 execution.**
