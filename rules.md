# Engineering rules

- Repository-locked Python 3.12.x patch; uv is the sole environment and dependency manager.
- FastAPI, Pydantic v2, PostgreSQL, SQLAlchemy 2, psycopg 3, pytest, Ruff, and mypy form the Core
  baseline.
- Deterministic Ground Truth > Human Gold > LLM Judge.
- No false-green results, secret leakage, or speculative architecture.
- One phase at a time; pass its gate before progression.
- No automatic commit or push.
