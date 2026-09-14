from pathlib import Path

MIGRATION_DIR = Path("database/migrations")


def test_sql_migrations_are_utf8_without_bom_or_nul():
    migrations = sorted(MIGRATION_DIR.glob("*.sql"))

    assert migrations, "No SQL migrations were found"

    for migration in migrations:
        raw = migration.read_bytes()

        assert not raw.startswith(
            b"\xef\xbb\xbf"
        ), f"{migration.name} contains a UTF-8 BOM"

        assert b"\x00" not in raw, (
            f"{migration.name} contains a NUL byte"
        )

        raw.decode("utf-8")
