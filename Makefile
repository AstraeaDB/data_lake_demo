PYTHON := python3
ASTRAEA_BIN ?= astraeadb
ASTRAEA_PORT ?= 7687
ASTRAEA_UI_DIR ?= /Users/jimharris/Documents/astraea-UI

.PHONY: help deps generate-data embeddings start-astraea ingest validate setup \
        demo narrated interactive test clean stop-astraea ui

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Setup Pipeline ---

deps:  ## Install Python dependencies
	$(PYTHON) -m pip install -r requirements.txt
	@$(PYTHON) -m pip install -e /Users/jimharris/Documents/astraeadb/python/ 2>/dev/null \
		|| $(PYTHON) -m pip install /Users/jimharris/Documents/astraeadb/python/ 2>/dev/null \
		|| echo "NOTE: Could not install astraeadb client. Ingestion will use sys.path fallback."

generate-data:  ## Generate all data lake files (synthetic + CERT-schema)
	$(PYTHON) scripts/generate_data.py

start-astraea:  ## Start AstraeaDB server (background)
	@if lsof -i :$(ASTRAEA_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "AstraeaDB already running on port $(ASTRAEA_PORT)"; \
	else \
		$(ASTRAEA_BIN) serve --port $(ASTRAEA_PORT) & \
		sleep 2; \
		echo "AstraeaDB started on port $(ASTRAEA_PORT)"; \
	fi

stop-astraea:  ## Stop AstraeaDB server
	@-pkill -f "$(ASTRAEA_BIN) serve" 2>/dev/null && echo "AstraeaDB stopped" || echo "AstraeaDB not running"

embeddings:  ## Generate embeddings for metadata descriptions (requires Ollama)
	$(PYTHON) scripts/generate_embeddings.py

ingest: start-astraea  ## Load metadata graph into AstraeaDB
	$(PYTHON) scripts/ingest_metadata.py

validate:  ## Validate data files and metadata consistency
	$(PYTHON) -m pytest test_demo.py -v --tb=short -k "TestDataIntegrity or TestMetadataFiles or TestDuckDbTools"

setup: deps generate-data embeddings ingest validate  ## Full setup pipeline
	@echo ""
	@echo "Setup complete! Run 'make demo' to start the presentation."

setup-no-embeddings: deps generate-data ingest validate  ## Setup without embeddings (skip Ollama requirement)
	@echo ""
	@echo "Setup complete (without embeddings). Run 'make demo' to start."

# --- Demo ---

demo: start-astraea  ## Run the full narrated demo + interactive chat
	$(PYTHON) -m src.orchestrator --mode full

narrated: start-astraea  ## Run only the narrated walkthrough
	$(PYTHON) -m src.orchestrator --mode narrated --interactive

interactive: start-astraea  ## Run only the interactive chat
	$(PYTHON) -m src.orchestrator --mode interactive

# --- Optional: Astraea UI ---

ui:  ## Start Astraea UI for graph visualization (optional)
	@echo "Starting Astraea UI..."
	@echo "Make sure AstraeaDB is running (make start-astraea)"
	cd $(ASTRAEA_UI_DIR) && cargo leptos serve

# --- Development ---

test:  ## Run full test suite
	$(PYTHON) -m pytest test_demo.py -v --tb=short

test-quick:  ## Run quick tests (no AstraeaDB required)
	$(PYTHON) -m pytest test_demo.py -v --tb=short -k "not TestEndToEnd"

clean:  ## Remove generated data files
	rm -rf data/security/ data/communications/ data/hr/ data/projects/ data/cert_raw/
	rm -f metadata/embeddings.json metadata/id_map.json metadata/user_mapping.json
	@echo "Cleaned. Run 'make setup' to regenerate."
