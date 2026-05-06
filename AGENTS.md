# AGENTS.md - Financial Model Neo4j Knowledge Graph

## Repository Overview
Financial Model Knowledge Graph Explorer - Parses Excel financial models and creates a 3-layer knowledge graph (Cell/Indicator/Table) with Neo4j integration.

### Core Components
- **Streamlit frontend**: Located in `main.py` and `pages/*.py` (ordered numerically: 01_upload to 05_qa)
- **Knowledge Graph Engine**: In `financial_kg/` package with parser, storage, models, LLM, and visualization modules  
- **Data Processing Layer**: Excel parsing, formula extraction, dependency analysis
- **Storage Layer**: JSON (local), Neo4j (optional)
- **LLM Integration**: Qwen 3.6 model used (based on repo name)

## Setup & Dependencies

```bash
pip install -r requirements.txt
```

Key requirements: streamlit, openpyxl, neo4j, openai, pandas, networkx, pyvis

### Environment Variables
Copy `.env.example` to `.env`:
```
# LLM Configuration
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your-qwen-api-key-here
LLM_MODEL=qwen3.6  # or appropriate model

# Neo4j Configuration  
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password-here
```

## Running the Application

Start with the dedicated batch script:
```bash
./run_streamlit.bat
```

Alternative direct command:
```bash
streamlit run main.py --server.port=8534
```

## Key Commands & Operations

### Development Commands
- `streamlit run main.py --server.port=XXXX` - Start the app on custom port
- `python -m streamlit run main.py` - Alternative if direct streamlit fails

### Test Specific Files (Python)
- To test parser separately: `python -c "from financial_kg.parser.excel_reader import read_excel; print('Parser OK')"`
- To test Neo4j connection: `python -c "from financial_kg.storage.neo4j_store import Neo4jStore; # Test code"`

## Architecture Notes

### Multi-Layer Graph Structure
1. **Cell Layer**: Individual Excel cells with formulas/values/formatting
2. **Indicator Layer**: Financial indicators aggregated from cells  
3. **Table Layer**: Logical groupings of cells and indicators
4. Relationships: BELONGS_TO, DEPENDS_ON, CALCULATES_FROM, FEEDS_INTO

### File Organization
- `main.py`: Streamlit entry point 
- `pages/*.py`: Ordered numbered pages for UI flow 01-05
- `financial_kg/`: Main package structure
  - `parser/`: Excel reading, formula parsing, cell/indicator/table extraction
  - `models/`: Cell, Indicator, Table, and Graph dataclasses
  - `storage/`: JSON store, Neo4j integration, task database
  - `llm/`: Q&A engine, prompt builder, retriever with Cypher generation
  - `viz/`: Graph visualization and propagation graph tools
  - `engine/`: Recalculation engine, snapshot management, dependency analysis
- `output/`: Default directory for exported JSONs
- `snapshots/`: Snapshot storage for comparison views
- `tasks.db`: SQLite database tracking task status

## Important Gotchas & Quirks

### Excel Processing 
- Large Excel files require substantial RAM and processing time
- Formula references must use standard Excel notation (Sheet!A1 style)
- Range expansions limited by `MAX_RANGE_EXPANSION` in config (def 2000 cells)
- Files with protected sheets are not supported

### Neo4j Operations
- Connection requires Neo4j instance running at configured endpoint
- Bulk imports can be memory-intensive
- Import process has 7 stages (see pages/01_upload.py) - monitor progress bars
- Database clearing is irreversible

### UI Behavior  
- Sessions store current graph in memory (may cause bloat with very large models)
- Multi-user support not designed in - file locking not implemented
- Task DB handles history tracking and file cleanup on deletion

### LLM Integration
- Qwen 3.6 model expected based on project name
- API calls include retries and error handling
- Financial context requires specific prompt engineering patterns
- Cost optimization important for complex queries

## Testing & Verification

### Quick Health Checks
1. **App startup**: Run `./run_streamlit.bat` and verify UI loads
2. **Parser import**: Test import with: `python -c "from financial_kg.parser.excel_reader import read_excel"`
3. **Config loaded**: Check `.env` exists and has required variables
4. **Directory structure**: Verify `output/`, `snapshots/` permissions

### Sample Test Workflows
1. Upload sample Excel and verify parsing completes 
2. Navigate graph in explorer view
3. Save and restore snapshots
4. Execute simple LLM query on graph data

## Common Pitfall Avoidance

- **Port conflicts**: Default port 8534 hardcoded in batch file (change if needed)
- **Memory usage**: Large graphs may exceed Streamlit's default memory limits
- **Path issues**: Relative paths for output and snapshots - avoid running in subdirs  
- **File formats**: Only xlsx/xls formats supported in upload UI
- **Neo4j connections**: Always clear sensitive credentials from memory when debugging

## Critical Files for Understanding
- `config.py`: All environment settings and defaults 
- `models/graph.py`: Central graph data structure
- `parser/cell_extractor.py`: Core formula parsing logic
- `storage/neo4j_store.py`: Neo4j import/export implementation