import argparse
from datetime import date

from app.database import Base, SessionLocal, engine
from app.services.tracker import track_prices_for_date


def main() -> None:
    parser = argparse.ArgumentParser(description="CS2 skin tracker jobs")
    parser.add_argument("command", choices=["track-once"], help="Job command")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.command == "track-once":
            created = track_prices_for_date(db, date.today())
            print(f"Created snapshots: {created}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
