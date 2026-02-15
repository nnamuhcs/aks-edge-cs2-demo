import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["TRACKER_SEED_DAYS"] = "10"
os.environ["PROVIDER_NAME"] = "mock"

from app.database import Base, engine


def pytest_sessionstart(session):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def pytest_sessionfinish(session, exitstatus):
    Base.metadata.drop_all(bind=engine)
    try:
        os.remove("test.db")
    except FileNotFoundError:
        pass
