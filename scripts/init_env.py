"""Create a local configuration once; never overwrite existing credentials."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; left unchanged.")
else:
    db_password = secrets.token_hex(20)
    values = {
        "POSTGRES_PASSWORD": db_password,
        "DATABASE_URL": f"postgresql+psycopg://relationships:{db_password}@localhost:55432/relationships",
        "SECRET_KEY": secrets.token_hex(32),
        "N8N_API_KEY": secrets.token_urlsafe(32),
        "ADMIN_PASSWORD": secrets.token_urlsafe(18),
    }
    lines = (root / ".env.example").read_text(encoding="utf-8").splitlines()
    content = (
        "\n".join(
            f"{line.split('=', 1)[0]}={values[line.split('=', 1)[0]]}"
            if "=" in line and line.split("=", 1)[0] in values
            else line
            for line in lines
        )
        + "\n"
    )
    # Owner-only permissions: the file holds the signing key, API key and admin password.
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(
        "Created .env with generated local credentials. Read ADMIN_EMAIL and ADMIN_PASSWORD there to sign in."
    )
