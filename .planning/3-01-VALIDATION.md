# Plan Validation: 3-01

## Result: PASS_WITH_NOTES

The plan is structurally sound, covers all 10 roadmap tasks, and aligns with all 3-CONTEXT.md decisions. However, several issues should be addressed before execution to reduce risk and improve atomicity.

---

## Requirement Coverage

| Requirement | Roadmap Task | Covered By Plan | Status |
|-------------|-------------|----------------|--------|
| FR-3.1 (AST parsing) | 3.1, 3.2, 3.3 | T01, T02, T03, T05 | ✅ |
| FR-3.2 (Change detection) | 3.6 | T07 | ✅ |
| FR-3.3 (Build graph) | 3.4, 3.5 | T04, T06 | ✅ |
| FR-3.4 (Incremental update) | 3.7 | T07 | ✅ |
| FR-5.2 (MCP tools) | 3.9, 3.10 | T10 | ✅ |
| TR-2 (tree-sitter) | 3.1 | T02, T03 | ✅ |

All roadmap tasks (3.1–3.10) are covered. The plan adds T09 (query methods) which was implicitly needed by 3.9/3.10 but not explicitly listed as a separate roadmap task. This is a **reasonable addition** — `get_file_graph` cannot function without `get_subgraph()`, `get_dependencies()`, etc.

---

## Task Quality

| Task | Atomic? | Testable? | Verified? | Status |
|------|---------|-----------|-----------|--------|
| T01 — ParsedSymbol data class | ✅ | ✅ | ✅ | Good — single cohesive dataclass |
| T02 — Language detection + tree-sitter init | ✅ | ✅ | ✅ | Good — focused, includes ImportError handling |
| T03 — parse_file + symbol extraction | ⚠️ | ✅ | ✅ | **Large** — combines file reading, tree-sitter parsing, AST walking, and symbol emission |
| T04 — FileNode data class | ✅ | ✅ | ✅ | Good — single dataclass, independent |
| T05 — Edge extraction (7 types) | ❌ | ✅ | ✅ | **Too large** — 7 edge types with different parsing logic in one commit |
| T06 — FileGraph + build_graph | ❌ | ✅ | ✅ | **Too large** — class init + directory walk + parsing integration + node/edge creation + hash indexing |
| T07 — SHA-256 change detection + incremental update | ⚠️ | ✅ | ✅ | **Large but cohesive** — combines detection logic with graph update |
| T08 — Graph persistence save/load | ✅ | ✅ | ✅ | Good — focused, round-trip testable |
| T09 — Query methods (5 methods) | ⚠️ | ✅ | ✅ | **Acceptable** — 5 related query methods, but could benefit from splitting |
| T10 — MCP tool registration | ✅ | ✅ | ✅ | Good — 2 tools + server wiring, cohesive |

---

## Issues Found

### Major (should fix before execution):

1. **T05 is too large — 7 edge types in one commit**
   - **Problem:** IMPORTS_FROM, CALLS, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, and DEPENDS_ON all in a single commit. Each type requires different tree-sitter node detection logic.
   - **Risk:** If one edge type has bugs, the entire commit is tainted. Hard to bisect.
   - **Fix suggestion:** Split into 2–3 commits:
     - T05a: IMPORTS_FROM + CONTAINS (highest priority, simplest patterns)
     - T05b: CALLS + INHERITS + IMPLEMENTS (moderate complexity)
     - T05c: TESTED_BY + DEPENDS_ON (simple pattern matching, fallback)
   - **Impact on dependency chain:** T06 would depend on T05a (minimum), T05b, T05c can follow or be parallelized.

2. **T06 is too large — FileGraph class + build_graph combined**
   - **Problem:** This commit would create the class, implement directory walking, integrate ASTParser, create nodes, add edges, and populate SHA-256 index.
   - **Risk:** Multiple failure modes (directory walk bugs, parsing integration issues, edge creation errors) all in one commit.
   - **Fix suggestion:** Split into 2 commits:
     - T06a: FileGraph class with `add_node()`, `add_edge()`, `get_subgraph()` skeleton + basic NetworkX DiGraph init
     - T06b: `build_graph(directory)` — directory walk, parsing integration, node/edge population, hash indexing
   - **Impact on dependency chain:** T07, T08, T09 would depend on T06a (for graph structure) and T06b (for build logic).

3. **T03 missing error handling for syntax errors**
   - **Problem:** No success criteria or implementation notes address what happens when tree-sitter encounters a file with syntax errors (e.g., incomplete Python file, encoding issues).
   - **Risk:** Parser crashes on malformed files, causing `build_graph` to fail on the first bad file.
   - **Fix suggestion:** Add to T03 success criteria:
     - [ ] `parse_file()` on a file with syntax errors returns partial results or empty list (no crash)
     - [ ] Encoding errors are caught and logged
     - [ ] Unit test: parse a file with intentional syntax errors

### Minor (nice to fix):

4. **T04 could be parallelized with Wave 1**
   - **Observation:** T04 (FileNode) has no dependencies and is in a different file (`file_graph.py`) than Wave 1 tasks (`parser.py`).
   - **Suggestion:** Move T04 to Wave 1 or mark as "can run in parallel with T01–T03". The plan already notes this in T04's dependencies ("can be done in parallel with Wave 1"), but the wave grouping contradicts this.

5. **No explicit progress logging for large directory builds**
   - **Risk:** R3.3 (1000+ files) is acknowledged but no task includes progress logging. During Wave 2 execution, the user would see no output for potentially minutes.
   - **Suggestion:** Add to T06 success criteria:
     - [ ] `build_graph()` logs progress (e.g., "Parsed 50/200 files...")
     - [ ] Or at minimum, logs total file count at start and completion summary at end

6. **NetworkX serialization edge cases not explicitly tested in T08**
   - **Risk:** R3.4 mentions serialization issues with complex edge attributes. T08's success criteria cover round-trip equality but not edge cases.
   - **Suggestion:** Add to T08 success criteria:
     - [ ] Graph with 0 edges saves/loads correctly
     - [ ] Graph with self-loops (if any) handles correctly
     - [ ] Line number attributes survive round-trip as integers (not strings)

7. **T10 dependency on T07 and T08 may be overly strict**
   - **Observation:** `track_files` could work with just in-memory `build_graph()` — it doesn't strictly need incremental updates (T07) or persistence (T08).
   - **Suggestion:** Consider relaxing T10 dependencies to T06, T09 (minimum). T07 and T08 are enhancements that can be added later. However, keeping the strict ordering is safer for a weekend project scope.

---

## 3-CONTEXT.md Alignment Check

| Decision | Covered In Plan | Status |
|----------|----------------|--------|
| D1: tree-sitter-language-pack | T02 (detect_language with ImportError handling) | ✅ |
| D2: Qualified name format `/abs/path/file.py::ClassName.method_name` | T01 (qualified_name property with `::` delimiter) | ✅ |
| D3: All 7 edge types | T05 (all 7 listed with examples) | ✅ |
| D4: JSON persistence via node_link_data() | T08 (explicitly mentions node_link_data) | ✅ |
| D5: Per-file SHA-256 hashing | T04 (update_hash), T07 (SHA-256 index comparison) | ✅ |
| D6: Incremental update strategy | T07 (update_graph with changed_files, only re-parse changed) | ✅ |
| D7: MCP tools return JSON via json.dumps(indent=2) | T10 (explicitly states json.dumps(indent=2)) | ✅ |

---

## Risk Coverage

| Risk | Addressed In Plan | Status |
|------|-------------------|--------|
| R3.1: tree-sitter-language-pack Windows install failure | Implementation Notes: fallback to regex parsing documented. T02 includes ImportError handling. | ✅ |
| R3.2: Grammar compilation fails for certain languages | T02: ImportError caught, language set to "unsupported". | ✅ |
| R3.3: Large directory parsing (1000+ files) | T06: skip directories listed. T07: incremental updates mitigate. **No progress logging.** | ⚠️ Partial (see Minor #5) |
| R3.4: NetworkX serialization edge cases | T08: node_link_data() used. **No edge case tests.** | ⚠️ Partial (see Minor #6) |

---

## Wave Grouping Assessment

| Wave | Tasks | Assessment |
|------|-------|------------|
| Wave 1 | T01, T02, T03 | ✅ Logical — parser foundation |
| Wave 2 | T04, T05, T06, T07 | ⚠️ T04 is independent and could be Wave 1. T05 and T06 are too large and should be split. |
| Wave 3 | T08, T09, T10 | ✅ Logical — persistence + integration |

---

## Gaps Identified

1. **No explicit directory filtering configuration** — T06 hardcodes skip patterns (`.git`, `__pycache__`, `.venv`, `node_modules`). The ROADMAP.md doesn't require configurable filtering, so this is acceptable for MVP.

2. **No TESTED_BY implementation detail** — T05 mentions matching `test_*.py` / `*_test.py` patterns but doesn't specify how `TESTED_BY` edges will be resolved when test files don't have matching source files (e.g., `test_utils.py` when `utils.py` doesn't exist). Suggestion: edge should only be created when the target file exists in the graph.

3. **No `__init__.py` update task** — If `edges.py` is created as suggested (or if edge extraction lives in `parser.py`), the package `__init__.py` may need updates. Not mentioned anywhere.

---

## Recommendations

### Before Execution (recommended):
1. **Split T05** into T05a (IMPORTS_FROM + CONTAINS), T05b (CALLS + INHERITS + IMPLEMENTS), T05c (TESTED_BY + DEPENDS_ON). Update dependency chain accordingly.
2. **Split T06** into T06a (FileGraph class skeleton) and T06b (build_graph implementation). Update dependency chain.
3. **Add error handling criteria to T03** for syntax errors and encoding issues.
4. **Move T04 to Wave 1** or note it can execute in parallel with T01–T03.

### During Execution (monitor):
5. **Add progress logging** to T06 for large directory builds.
6. **Test tree-sitter installation early** (T02) to confirm Windows compatibility before investing in full parser implementation.
7. **Verify NetworkX round-trip with edge cases** in T08 (empty graph, integer types).

---

## Iteration History
- Attempt 1: PASS_WITH_NOTES — Plan covers all requirements but has 3 major atomicity issues and 4 minor improvements.

## Recommendation: **APPROVE WITH CONDITIONS**

The plan is approved for execution **provided** the executor addresses the 3 major issues during implementation:
1. Be prepared to split T05 into smaller commits if edge extraction proves complex.
2. Be prepared to split T06 into class skeleton + build logic if the commit scope grows too large.
3. Handle syntax errors gracefully in T03 — do not let one bad file crash the entire parser.

The minor issues (#4–#7) are optional improvements that can be addressed during execution without blocking progress.
