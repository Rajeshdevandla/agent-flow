"""Seed harmless CI fixtures, then verify they were excluded from the image."""

import argparse
from pathlib import Path

FIXTURES = (
    ".env",
    ".env.production",
    "config/.env.local",
    ".aws/credentials",
    ".ssh/id_rsa",
    ".streamlit/secrets.toml",
    "config/context-test.pem",
    "config/context-test.key",
    ".venv/context-test.txt",
    "venv/context-test.txt",
    "config/.venv/context-test.txt",
    "config/__pycache__/context-test.txt",
    "logs/decisions/context-test.txt",
)
REQUIRED = (".env.example", "requirements.txt", "api/main.py", "frontend/app.py")


def seed(root):
    # Never overwrite local configuration, even when invoked outside CI.
    existing = [path for path in FIXTURES if (root / path).exists()]
    if existing:
        raise RuntimeError(f"Refusing to overwrite existing fixture paths: {existing}")
    for path in FIXTURES:
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x") as file:
            file.write("docker-context-test-only-not-a-credential\n")


def check(root):
    leaked = [path for path in (".git", *FIXTURES) if (root / path).exists()]
    missing = [path for path in REQUIRED if not (root / path).is_file()]
    if leaked or missing:
        raise RuntimeError(
            f"Image context check failed: leaked={leaked}, missing={missing}"
        )
    print(
        "Image excludes private/local fixtures and Git metadata; runtime files remain"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seed", "check"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    (seed if args.mode == "seed" else check)(root)
