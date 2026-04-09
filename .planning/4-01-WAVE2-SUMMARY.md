# Summary: Phase 4 Wave 2 — Session Index, Import Matching, Double-Parse Fix

## Tasks Completed
| Task | Commit | Status |
|------|--------|--------|
| T05 | `598f6e5` | ✅ |
| T06 | `d77b581` | ✅ |
| T07 | `801d943` | ✅ |

## Task Details

### T05 — Optimize list_sessions with Session Index JSON
- Added `_SESSION_INDEX_PATH` constant (`./data/session_index.json`)
- Added `session_index_path` parameter to `ChatStore.__init__` for test isolation
- Implemented `_load_session_index()`, `_rebuild_session_index()`, `_save_session_index()`
- Implemented `_update_session_index()` — called after `store_messages()`
- Implemented `_remove_from_session_index()` — called after `delete_session()`
- Updated `list_sessions()` to read from in-memory index (O(1) instead of O(n) ChromaDB query)
- Updated `prune_sessions()` to save index after pruning
- Updated test fixture to use isolated `tmp_path` for session index
- **27/27 chat_store tests pass** (no regressions)

### T06 — Fix Import Matching with AST Node Parsing
- Added `_parse_import_module()` helper to extract module names from import symbols
- Rewrote `extract_imports_edges()` to use parsed module names instead of substring matching
- Also updated `extract_depends_on_edges()` to use the same AST-based approach
- Module matching: `import os` → extracts `os` → matches `os.py` (not `some_os_helper.py`)
- `from pathlib import Path` → extracts `pathlib` → matches `pathlib.py`
- **160/160 total tests pass** (no regressions)

### T07 — Eliminate Double-Parsing in update_graph
- Added `new_symbols: dict[str, list]` to retain symbols from first pass
- First pass: parse files, store symbols in `new_symbols`, create nodes
- Second pass: read symbols from `new_symbols` (fallback to re-parse only if missing)
- `parse_file()` now called exactly once per changed file
- Same edges produced as before (verified by existing tests)
- **160/160 total tests pass** (no regressions)

## Deviations
- **None.** All tasks implemented exactly as specified in the plan.
- Added `session_index_path` parameter to `ChatStore.__init__` (not in plan spec) to enable test isolation — this is a minor enhancement that improves testability without changing default behavior.

## Verification
- All 160 tests pass in ~29s
- 3 atomic commits created with correct `[GSD-4-01-T{n}]` format
- No test regressions across all 4 test files
- Session index file created at `./data/session_index.json` on first store
- Import matching uses AST node parsing (no substring false positives)
- update_graph calls parse_file exactly once per changed file
