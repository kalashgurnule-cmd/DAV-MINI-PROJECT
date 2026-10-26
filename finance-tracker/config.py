"""Central configuration for the Personal Finance Shadow Tracker."""
from pathlib import Path

# Reproducibility: every run produces identical synthetic data
SEED = 42

# How many months of history the synthetic generator should create.
# 38 months ≈ 3.2 years: the yearly zombie (Prime Video) needs >= 3 occurrences
# for the interval detector, and inflation YoY needs a long window too.
DATA_MONTHS = 38

# Server
HOST = "127.0.0.1"
PORT = 5000

# Paths
BASE_DIR = Path(__file__).resolve().parent          # project root
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "finance.db"
FRONTEND_DIR = BASE_DIR / "frontend"

SQLALCHEMY_URI = f"sqlite:///{DB_PATH.as_posix()}"
