"""Create a PostgreSQL custom-format backup; optionally prove restore in a temporary DB.

Uses docker compose without shell interpolation. Never restores over workspace data.
"""
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="Restore into a disposable test database")
    args = parser.parse_args()
    config = dotenv_values(ROOT / ".env")
    user = config.get("POSTGRES_USER") or "relationships"
    database = config.get("POSTGRES_DB") or "relationships"
    folder = ROOT / "backups"
    folder.mkdir(exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    target = folder / (name + ".dump")
    command = ["docker", "compose", "exec", "-T", "db"]
    try:
        with target.open("xb") as output:
            subprocess.run(command + ["pg_dump", "-U", user, "-d", database, "-Fc"], cwd=ROOT, stdout=output, check=True)
        with target.open("rb") as source:
            subprocess.run(command + ["pg_restore", "--list"], cwd=ROOT, stdin=source, stdout=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, OSError):
        # Never leave an empty or unreadable file that looks like a valid backup.
        target.unlink(missing_ok=True)
        raise SystemExit("Backup failed: is the db container running? (docker compose up -d db)")
    print(f"Backup created: {target.name} ({target.stat().st_size} bytes)")
    if args.verify:
        temporary_database = "rip_restore_check_" + uuid4().hex
        subprocess.run(command + ["createdb", "-U", user, temporary_database], cwd=ROOT, check=True)
        try:
            with target.open("rb") as source:
                subprocess.run(command + ["pg_restore", "-U", user, "-d", temporary_database, "--exit-on-error", "--no-owner"], cwd=ROOT, stdin=source, check=True)
            result = subprocess.run(command + ["psql", "-U", user, "-d", temporary_database, "-At", "-c",
                "SELECT version_num FROM alembic_version; SELECT count(*) FROM users; SELECT count(*) FROM research_requests;"],
                cwd=ROOT, capture_output=True, text=True, check=True)
            lines = result.stdout.strip().splitlines()
            if len(lines) != 3 or int(lines[1]) < 1:
                raise RuntimeError("Restored workspace validation failed")
            print(f"Restore verified: schema {lines[0]}, {lines[1]} users, {lines[2]} research requests")
        finally:
            subprocess.run(command + ["dropdb", "-U", user, temporary_database], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
