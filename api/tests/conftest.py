import os

# Keep module-level application configuration deterministic during tests.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite://")
