"""Copy Solar Setu data from SQLite to an existing PostgreSQL schema.

This script never writes to the SQLite source. Run `flask db upgrade` against
PostgreSQL first, then run this script with DATABASE_URL set to PostgreSQL.
"""
import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine, MetaData, select, text

from app import create_app
from app.models import db

TABLE_ORDER = [
    "users",
    "user_locations",
    "solar_providers",
    "solar_solutions",
    "saved_comparisons",
    "tariff_table",
    "subsidy_scheme",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default="solar_app.db", help="SQLite source file")
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL must point to PostgreSQL; the SQLite source is never the destination.")

    source_url = f"sqlite:///{Path(args.sqlite).resolve()}"
    source_engine = create_engine(source_url)
    destination_app = create_app(skip_seed=True)
    with destination_app.app_context():
        destination_engine = db.engine
        source_metadata = MetaData()
        destination_metadata = MetaData()
        source_metadata.reflect(bind=source_engine)
        destination_metadata.reflect(bind=destination_engine)
        missing_destination = [name for name in TABLE_ORDER if name not in destination_metadata.tables]
        if missing_destination:
            raise SystemExit(f"Destination is missing tables. Run 'flask db upgrade' first: {missing_destination}")

        with source_engine.connect() as source_connection, destination_engine.begin() as destination_connection:
            source_tables = {name: source_metadata.tables[name] for name in TABLE_ORDER if name in source_metadata.tables}
            destination_tables = {name: destination_metadata.tables[name] for name in TABLE_ORDER}
            counts = {}
            for name in TABLE_ORDER:
                source_rows = source_connection.execute(select(source_tables[name])).mappings().all() if name in source_tables else []
                destination_table = destination_tables[name]
                if source_rows:
                    destination_connection.execute(destination_table.insert(), [
                        {key: value for key, value in row.items() if key in destination_table.c}
                        for row in source_rows
                    ])
                counts[name] = (len(source_rows), destination_connection.execute(select(destination_table)).fetchall().__len__())

            for name in TABLE_ORDER:
                if name not in source_tables:
                    continue
                destination_connection.execute(text(
                    "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                    "COALESCE((SELECT MAX(id) FROM " + name + "), 1), "
                    "COALESCE((SELECT MAX(id) FROM " + name + "), 0) > 0)"
                ), {"table_name": name})

            orphan_locations = destination_connection.execute(text(
                "SELECT count(*) FROM user_locations l LEFT JOIN users u ON u.id = l.user_id "
                "WHERE l.user_id IS NOT NULL AND u.id IS NULL"
            )).scalar_one()
            orphan_solutions = destination_connection.execute(text(
                "SELECT count(*) FROM solar_solutions s LEFT JOIN solar_providers p ON p.id = s.provider_id "
                "WHERE p.id IS NULL"
            )).scalar_one()
            if orphan_locations or orphan_solutions:
                raise SystemExit(f"Relationship verification failed: locations={orphan_locations}, solutions={orphan_solutions}")

    print("Migration verification")
    for name, (source_count, destination_count) in counts.items():
        print(f"{name}: SQLite={source_count} PostgreSQL={destination_count}")
        if source_count != destination_count:
            raise SystemExit(f"Count mismatch in {name}")
    print("Relationships: OK")


if __name__ == "__main__":
    main()
