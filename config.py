"""Configuration for the Data Lake Demo."""

import os
from pathlib import Path

# --- Paths ---
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
METADATA_DIR = PROJECT_DIR / "metadata"
CERT_RAW_DIR = DATA_DIR / "cert_raw"

# Data lake file paths
SECURITY_DIR = DATA_DIR / "security"
COMMS_DIR = DATA_DIR / "communications"
HR_DIR = DATA_DIR / "hr"
PROJECTS_DIR = DATA_DIR / "projects"

# --- AstraeaDB ---
ASTRAEA_HOST = os.getenv("ASTRAEA_HOST", "127.0.0.1")
ASTRAEA_PORT = int(os.getenv("ASTRAEA_PORT", "7687"))
ASTRAEA_BIN = os.getenv("ASTRAEA_BIN", "astraeadb")

# --- LLM ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")  # "anthropic" or "ollama"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "gemma3:12b")

# --- Embeddings ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embeddinggemma")
EMBEDDING_DIM_RAW = 768
EMBEDDING_DIM = 128  # Matryoshka truncation

# --- Data Generation ---
USER_COUNT = 200
SEED = 42

# Departments and their relative sizes
DEPARTMENTS = {
    "Engineering": 50,
    "Sales": 30,
    "Marketing": 20,
    "Finance": 15,
    "Human Resources": 15,
    "IT": 25,
    "Operations": 30,
    "Legal": 15,
}

# Security data: 90-day monitoring window
SECURITY_START = "2023-01-02"
SECURITY_END = "2023-03-31"
SECURITY_LOGON_TARGET = 18000
SECURITY_HTTP_TARGET = 25000
SECURITY_EMAIL_TARGET = 15000

# Communications data
TEAMS_START = "2018-01-01"
TEAMS_END = "2021-06-30"
TEAMS_TARGET = 40000

ZOOM_START = "2020-03-01"
ZOOM_END = "2024-12-31"
ZOOM_TARGET = 80000

# HR data
LEGACY_HR_START = "2017-01-01"
LEGACY_HR_END = "2021-12-31"

MODERN_HR_START = "2021-07-01"
MODERN_HR_END = "2024-12-31"

# Project management data
PM_START = "2019-01-01"
PM_END = "2024-12-31"
PM_TARGET = 12000

# --- Demo ---
MAX_TOOL_ROUNDS = 20
INTERACTIVE_PAUSE = os.getenv("INTERACTIVE", "false").lower() == "true"
