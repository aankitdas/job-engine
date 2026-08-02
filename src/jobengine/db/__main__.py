"""CLI: uv run python -m jobengine.db {init|migrate|stats}"""

import argparse

from jobengine.db.migrate import DEFAULT_DB_PATH, connect, init, migrate, stats


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobengine.db")
    parser.add_argument("command", choices=["init", "migrate", "stats"])
    args = parser.parse_args()

    conn = connect(DEFAULT_DB_PATH)
    try:
        if args.command == "init":
            init(conn)
            print(f"schema ready at {DEFAULT_DB_PATH}")
        elif args.command == "migrate":
            migrate(conn)
            print("migrations applied")
        elif args.command == "stats":
            for table, count in sorted(stats(conn).items()):
                print(f"{table:<24} {count}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
