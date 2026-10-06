import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test-copilot.db"
os.environ["APP_ENV"] = "development"
os.environ["AI_ANALYSIS_ENABLED"] = "false"


@pytest.fixture(autouse=True)
def reset_database():
    from app.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
