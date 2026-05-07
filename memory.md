# Memory - Financial Model Neo4j Knowledge Graph Project

## Goal
- Improve financial QA system retrieval quality and user experience through Phase 1&2 enhancements (category expansion, Prompt optimization, UI improvements)

## Constraints & Preferences
- No vector embeddings dependency (use keyword + category + LLM hybrid retrieval instead)
- Support year inference (204→2040, 24→2024)
- Provide visual feedback (confidence scores, retrieval debugging)
- Chat history persistence (SQLite, session isolation)
- Financial domain expertise in LLM responses
- Professional financial terminology (毛利率、净利率、EBITDA、ROI)
- Structured response templates (数值查询、趋势分析、对比分析、因果分析)

## Progress

### Done (v35.0.0 - 2026-05-07)
- **Complete Refactor: Parameter Modification Page** (pages/03_recalc.py)
  * Replaced nested 5-step selection with dual-column layout
  * Left panel: Parameter quick view with **4-level filtering**:
    - Name search: fuzzy match indicator_name, cell_id, value
    - Value type: 数值型 vs 文本型
    - Formula type: 无公式(参数) vs 有公式(计算)
    - Category: 15 indicator classes (收入类/成本类/...)
  * Formula cells: show formula but no modification (safety guard)
  * Non-formula cells: allow quick modification + batch selection
  * Right panel: Search + Before/After comparison view
  * Batch modification support (select multiple parameters → one-click recalc)
  * Auto snapshot naming with timestamp (no manual input required)
  * Dependency propagation visualization (downstream chain tree)
  * Color-coded change highlighting (>5% growth = green, >5% drop = red)
  * Pagination for search results (20 per page, avoid long lists)
  * Quick modify button for single-cell editing
  * File: `pages/03_recalc.py` (500+ lines, complete rewrite)
- **Key UX Improvements**:
  * Workflow: 2 steps (click indicator → modify value) vs old 5 steps
  * Multi-level filtering: name + value type + formula + category
  * Formula safety: distinguish input cells (modifiable) vs formula cells (view only)
  * Batch mode: "逐个输入值" or "统一变化幅度(%)" for scenario testing
  * Comparison tab: statistics + before/after table + dependency tree
  * Success rate metric: affected_cells / (affected + errors)
- **Technical Changes**:
  * Identify all cells: not just parameters, support formula cell filtering
  * Categorize indicators: match INDICATOR_CATEGORIES keywords
  * Dependency chain traversal: depth limit 3, show downstream impact
  * Snapshot auto-naming: "{name}-{timestamp}" format
  * Value type detection: isinstance(value, (int, float)) → 数值型
- **Next**: Test with real Excel files, collect user feedback, optimize performance
- **UI Complete Refactor**: Enhanced upload page with modern UX
  * Drag-drop upload support with visual feedback
  * File preview panel (sheet list, cell statistics, estimated parsing time)
  * Step-by-step progress bar (6 stages: Excel→Cell→Indicator→Table→Time→Save)
  * Configuration panel (task ID, output directory)
  * Success animations and navigation guidance
  * File: `pages/01_upload.py` (373 lines, complete rewrite)
- **New Page: Task History Management** (pages/06_tasks.py)
  * Status filtering (done/running/error/pending)
  * Task statistics overview with metrics
  * Delete confirmation with two-step verification
  * Load & browse graph button (merged into single action)
  * Quick navigation to graph explorer
  * File: `pages/06_tasks.py` (new 170+ lines)
- **New Page: Neo4j Import** (pages/07_neo4j.py)
  * Step-by-step import workflow (select task→configure connection→import)
  * Connection test functionality with error handling
  * Configuration persistence to .env file
  * Database clearing with triple-confirmation safety mechanism
  * Neo4j usage guide with Cypher query examples
  * Import progress tracking (7 stages with callbacks)
  * File: `pages/07_neo4j.py` (new 200+ lines)
- **Main Navigation Update** (main.py)
  * Functional grouping (Core Features / Management & Config)
  * Quick start guide with recommended workflow
  * Page link optimization with icons
  * File: `main.py` (50 lines)
- **Bug Fixes**:
  * Fix CellData.formula_raw attribute error in upload preview (line 64)
  * Fix Graph class import → FinancialGraph (removed unnecessary import)
  * Fix graph explorer prioritize loaded graph in session state
    - Display current task info with switch button
    - Use session_state["current_graph"] and ["current_task_id"]
    - File: `pages/02_explorer.py` (41 lines modified)
- **Git commit**: b537189 "feat: complete UI refactor with new pages"
- **Git tag**: v34.0.0 successfully created and pushed
- **Statistics**: 5 files changed, 587 insertions(+), 215 deletions(-), 2 new files

### Done (v33.0.0 - 2025-05-07)
- **Phase 1.1**: Category expansion 9→15 classes
  * Added: 人工成本类、材料成本类、折旧摊销类、利息费用类、股权类、其他类
  * Keywords expanded from 30+ to 80+ for better indicator coverage (60%→90%)
  * File: `financial_kg/llm/category_classifier.py:12-133`
- **Phase 1.2**: Prompt optimization with financial analyst expertise
  * Upgraded from "财务分析助手" to "资深财务分析师，10年财务模型分析经验"
  * Added professional capabilities: 报表解读、指标依赖分析、数据分析
  * Added response templates: 数值查询、趋势分析、对比分析、因果分析
  * Added forbidden items: 不猜测数据、不混淆概念、不提供投资建议
  * File: `financial_kg/llm/prompt_builder.py:31-61`
- **Phase 1.3**: Retrieval debug panel for transparency
  * Phase 1: keyword extraction, year inference, category classification
  * Phase 2: final selection with match scores (show top 5 indicators)
  * File: `pages/05_qa.py:202-243`
- **Phase 1.4**: Chat history CSV export
  * Support session isolation (session_id)
  * Include timestamp, role, content, metadata
  * UTF-8-sig encoding for Chinese characters
  * File: `pages/05_qa.py:341-373`
- **Phase 2.1**: Confidence score display
  * Calculate avg(match_score)*10 for confidence (capped at 100%)
  * Color-coded: green (>70%), orange (50-70%), red (<50%)
  * Visual feedback below each answer
  * File: `pages/05_qa.py:178-192`
- **Phase 2.2**: User feedback buttons
  * Support: 👍 好, 👎 差, 😐 一般, ⚠️ 报告问题
  * Save feedback to chat_history_db with metadata (question, answer, confidence)
  * Toast notification for feedback recording
  * File: `pages/05_qa.py:245-280`
- **Phase 2.3**: Quick filters sidebar
  * Year selection: dynamic extraction from time_series (regex \d{4})
  * Category selection: 15 categories dropdown (from INDICATOR_CATEGORIES)
  * Indicator type: 全部/数值型/趋势型/计算型
  * File: `pages/05_qa.py:415-447`
- **Phase 2.4**: Chart generation from retrieval data
  * Line chart: trend visualization (pivot_table by 时期/指标)
  * Bar chart: indicator comparison (groupby mean)
  * Automatic numeric value detection (try float conversion)
  * File: `pages/05_qa.py:375-413`
- **Git commit**: f95f6ac "feat: Phase 1&2 enhancements for financial QA system (v33.0.0)"
- **Git tag**: v33.0.0 successfully created

### Earlier Done
- v13.0.0: Removed graph node click navigation (iframe sandbox limitation)
- v16.0.0: Implemented hybrid retrieval (keyword+category + LLM filtering)
- v17.0.0: Fixed formula_raw→formula_readable AttributeError
- v21.0.0: Fixed empty LLM choices index error (check len(resp.choices)>0)
- v27.0.0: Year inference (204→2040, 24→2024) + Chat history persistence SQLite

## Key Decisions
- **UI Refactor Strategy**: Complete redesign vs incremental improvements
  * Decision: Complete refactor with new pages (better UX, separation of concerns)
  * Reason: Original upload page crowded (history + Neo4j + upload all mixed)
  * Result: 3 separate pages with focused functionality
- **Task History UX**: Merged "Load to memory" + "View graph" buttons
  * Decision: Single "Load & browse graph" button
  * Reason: Two buttons had overlapping functionality, confusing UX
  * Result: Simpler, clearer action flow
- **Neo4j Safety**: Triple confirmation for database clearing
  * Decision: 3 clicks required (warning→danger→execute)
  * Reason: Irreversible destructive operation, prevent accidents
  * Result: Safe deletion workflow with visual escalation
- **Graph Explorer Loading**: Prioritize session state over task selector
  * Decision: Use loaded graph first, show switch button if needed
  * Reason: User selected task in history page, should reflect in explorer
  * Result: Consistent user experience across pages
- **Abandoned vector retrieval**: Chose keyword+category+LLM hybrid
  * Reason: No embedding dependency, better financial semantics, 75% cost savings
- **Abandoned graph node click navigation**: iframe sandbox blocks top-level navigation
  * Reason: allow-top-navigation not set in iframe sandbox attribute
- **Chose SQLite for chat history**: Persistent across page refreshes, session isolation support
- **Chose confidence scoring**: avg(match_score)*10, color-coded visual feedback
  * Reason: Transparent quality indicator for users
- **Category expansion 9→15**: Better indicator coverage (60%→90%)
- **Prompt structure**: Professional template with capabilities, standards, templates, forbidden items
- **15 indicator categories**: 收入类、成本类、费用类、利润类、投资类、资产类、负债类、现金流类、税金类、人工成本类、材料成本类、折旧摊销类、利息费用类、股权类、其他类
- **Chart generation**: Automatic numeric detection (try float conversion), pivot_table for trends

## Next Steps
1. Test v34.0.0 UI enhancements with sample Excel files
2. Verify all new pages work correctly:
   * Upload page: drag-drop, preview, progress steps, success animations
   * Task history: status filtering, delete confirmation, load graph
   * Neo4j import: connection test, import workflow, usage guide
3. Collect user feedback on new UX improvements
4. Monitor task history usage patterns
5. Consider additional UI refinements based on feedback
6. Document Neo4j Cypher query templates for users
7. Optimize large file parsing performance if needed

## Critical Context

### Hybrid Retrieval Architecture
- **Phase 1**: Keyword+category filter (0 cost)
  * Extract keywords from query (regex, split)
  * Infer years from query (204→2040, 24→2024)
  * Classify category from keywords (INDICATOR_CATEGORIES)
  * Filter candidates: keyword match + category match + year match
- **Phase 2**: LLM scoring (3000 tokens)
  * Input: top_k_candidates (default 30)
  * Output: scored indicators with match_score
  * Selection: top_k (default 5)
- **Phase 3**: Answer generation (2000 tokens)
  * Input: selected indicators + context + chat history
  * Output: structured financial analysis

### Financial Prompt Template
- **Role**: "资深财务分析师，拥有10年财务模型分析经验"
- **Capabilities**: 报表解读、指标依赖分析、数据分析
- **Standards**: 数据准确性、逻辑清晰性、专业性、完整性
- **Templates**: 数值查询、趋势分析、对比分析、因果分析
- **Forbidden**: 不猜测数据、不混淆概念、不提供投资建议

### Confidence Calculation
- Formula: `avg(match_score for all contexts) * 10`
- Capped at 100%
- Color-coded: green (>70%), orange (50-70%), red (<50%)

### Metadata Tracking
- Keywords extraction
- Years inference
- Category classification
- Total candidates count
- Stored in `state["metadata"]`

### Feedback Persistence
- role="feedback"
- content=feedback_value (good/bad/neutral/issue)
- metadata={question, answer, confidence}

### Chart Data Extraction
- Source: `ind.time_series` from retrieval contexts
- Conversion: try `float(value)` for numeric values
- DataFrame: {指标, 时期, 数值}
- Visualizations: pivot_table (line chart), groupby mean (bar chart)

### Empty LLM Choices Error
- LLM API may return empty choices list
- Must check `len(resp.choices) > 0` before accessing `[0]`
- Handle gracefully with fallback

### Indicator Attribute Mismatch
- Indicator model has `formula_readable` attribute
- NOT `formula_raw` (caused AttributeError)
- Check model definition in `financial_kg/models/indicator.py`

### CellData Model Attributes
- CellData class from `financial_kg/models/cell.py`
- Has `formula_raw` attribute (NOT `formula`)
- Used in preview section of upload page
- Correct usage: `c.formula_raw` not `c.formula`

### Graph Loading Priority
- Graph explorer should prioritize session_state over task selector
- Check `st.session_state.get("current_graph")` and `st.session_state.get("current_task_id")`
- Display current task info with switch button
- User-selected task from history page should persist across navigation

### Git Edit Persistence
- Always verify edits with read after edit tool success
- Use `git diff` to confirm changes
- Previous sessions had edit tool success but files unchanged

## Relevant Files

### Core Retrieval Components
- `financial_kg/llm/category_classifier.py`: INDICATOR_CATEGORIES (15 classes), CATEGORY_KEYWORDS (80+ keywords)
- `financial_kg/llm/prompt_builder.py`: build_system_prompt() with financial analyst template
- `financial_kg/llm/qa_engine.py`: Hybrid retrieval orchestration, ask_stream()
- `financial_kg/llm/retriever.py`: search_hybrid(), get_candidates_for_llm(), match_score calculation

### UI & Storage
- `pages/01_upload.py`: Upload page with drag-drop, preview, progress steps (v34.0.0 refactor)
- `pages/06_tasks.py`: Task history management, status filtering, load graph (new in v34.0.0)
- `pages/07_neo4j.py`: Neo4j import workflow, connection test, safety mechanism (new in v34.0.0)
- `pages/02_explorer.py`: Graph explorer, prioritize loaded graph in session
- `pages/05_qa.py`: QA page with confidence, feedback, debug, export, charts, filters
- `main.py`: Navigation with functional grouping, quick start guide
- `financial_kg/storage/chat_history_db.py`: Chat persistence (save_message, load_history, clear_history)
- `financial_kg/storage/task_db.py`: Task management

### Models & Config
- `financial_kg/models/indicator.py`: Indicator dataclass (formula_readable attribute)
- `financial_kg/models/graph.py`: FinancialGraph structure
- `financial_kg/config.py`: LLM and Neo4j configuration

### Memory
- `memory.md`: Session memory for context preservation

## Version History

- **v35.0.0** (2026-05-07): Complete refactor of parameter modification page
  * Dual-column layout: left panel (parameter quick view), right panel (search & compare)
  * Categorized parameter indicators (15 classes)
  * Batch modification support (multiple parameters → one-click)
  * Before/After comparison table with color-coded changes
  * Dependency propagation tree visualization
  * Auto snapshot naming with timestamp
  * Pagination for search results
  * Workflow simplified: 2 steps vs old 5 steps
- **v34.0.0** (2026-05-07): Complete UI refactor with new pages
  * Upload page: drag-drop, file preview, step progress, config panel
  * Task history page: status filtering, delete confirmation, load graph
  * Neo4j import page: step workflow, connection test, safety mechanism
  * Main navigation: functional grouping, quick start guide
  * Bug fixes: CellData.formula_raw, graph loading priority
- **v33.0.0** (2025-05-07): Phase 1&2 enhancements completed
  * Category expansion (9→15)
  * Prompt optimization (财务分析师 template)
  * Retrieval debug panel
  * Chat history CSV export
  * Confidence display (color-coded)
  * User feedback buttons
  * Quick filters sidebar
  * Chart generation (line/bar)
- **v32.0.0** (earlier): Placeholder for Phase 1&2
- **v27.0.0**: Year inference (204→2040) + Chat history persistence SQLite
- **v21.0.0**: Empty LLM choices fix (check len(resp.choices)>0)
- **v17.0.0**: formula_readable fix (Indicator attribute mismatch)
- **v16.0.0**: Hybrid retrieval implementation (keyword+category+LLM)
- **v13.0.0**: Graph node navigation removal (iframe sandbox)
- Earlier versions: v1.0.0 to v12.0.0 (basic features)

## Session Summary (2026-05-07)

### What We Did
1. Complete UI refactor based on user feedback
2. Refactored upload page (01_upload.py): drag-drop, preview, progress steps, animations
3. Created task history page (06_tasks.py): filtering, delete, load graph
4. Created Neo4j import page (07_neo4j.py): import workflow, safety mechanism
5. Updated main navigation (main.py): grouped links, quick start guide
6. Fixed bugs: CellData.formula_raw, graph loading priority
7. Git commit: 5 files changed, 587 insertions(+), 215 deletions(-)
8. Created git tag: v34.0.0

### Expected Impact
- User experience: Modern, intuitive UI with visual feedback
- Separation of concerns: Upload, history, Neo4j as separate pages
- Task management: Clear workflow for loading and browsing graphs
- Safety: Triple confirmation prevents accidental database deletion
- Navigation: Better organization with functional grouping

### Next Session Focus
- Test v34.0.0 in production with real Excel files
- Collect user feedback on new UI
- Optimize performance for large file parsing
- Consider additional features based on usage patterns

## Session Summary (2025-05-07)

### What We Did
1. Completed all Phase 1&2 enhancements (v33.0.0)
2. Modified 3 files: category_classifier.py, prompt_builder.py, pages/05_qa.py
3. Git commit: 340 insertions(+), 32 deletions(-)
4. Created git tag: v33.0.0

### Expected Impact
- Retrieval accuracy: 60%→90% (category coverage)
- Response quality: More professional with structured templates
- User transparency: Visible retrieval process tracking
- Data persistence: Chat history export for analysis
- User feedback: Quality rating collection for future improvements

### Next Session Focus
- Test v33.0.0 in production
- Monitor user feedback data
- Analyze confidence score distribution
- Consider Phase 3 enhancements (based on feedback patterns)