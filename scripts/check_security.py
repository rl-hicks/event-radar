"""Bounded tracked-source / frontend-artifact checks; never echo matched values.

Not a general secret detector or a historical/hosted exposure guarantee.
"""

import argparse
import base64
import json
import re
import subprocess
from pathlib import Path

PUBLIC_ENV = {"VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY", "VITE_API_URL"}
LOCAL_URLS = {
    "postgresql+psycopg://event_radar:event_radar_local@127.0.0.1:5432/event_radar",
    "postgresql+psycopg://event_radar_test:event_radar_test_local@127.0.0.1:55432/event_radar_test",
}
PATTERNS = {
    "Supabase privileged key": r"sb_secret_[A-Za-z0-9_-]{20,}",
    "OpenAI key": r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}",
    "Telegram token": r"\b\d{8,12}:[A-Za-z0-9_-]{35}\b",
    "GitHub token": r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "private signing key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
}
PRIVATE_NAMES = {
    "user_context.json",
    "personal_experience_preference_context.md",
    "telegram_offset.json",
    "permanent_directions.json",
    "temporary_directions.json",
}


def findings(text: str, *, artifact: bool = False) -> set[str]:
    result = {kind for kind, pattern in PATTERNS.items() if re.search(pattern, text)}
    for match in re.finditer(r"postgres(?:ql)?(?:\+psycopg)?://[^\s\"'<>`]+", text):
        url = match.group().rstrip("),;")
        if artifact or ("@" in url and url not in LOCAL_URLS):
            result.add("PostgreSQL connection URL")
    for match in re.finditer(r"eyJ[A-Za-z0-9_-]+\.([A-Za-z0-9_-]+)\.[A-Za-z0-9_-]+", text):
        try:
            payload = json.loads(base64.urlsafe_b64decode(match[1] + "=" * (-len(match[1]) % 4)))
        except (ValueError, UnicodeError):
            continue
        if isinstance(payload, dict) and payload.get("role") == "service_role":
            result.add("service-role JWT")
    if artifact and any(name in text for name in PRIVATE_NAMES):
        result.add("personal runtime file reference")
    return result


def private_path(path: str) -> bool:
    parts = Path(path).parts
    return (
        any(part in {".vercel", ".private-state", "state", "output", "audit"} for part in parts)
        or Path(path).name in PRIVATE_NAMES
        or (Path(path).name.startswith(".env") and Path(path).name != ".env.example")
    )


def browser_env_findings(text: str) -> set[str]:
    result = set()
    for match in re.finditer(r"import\.meta\.env", text):
        tail = text[match.end() :]
        access = re.match(r"\.([A-Za-z_][A-Za-z_0-9]*)", tail)
        if access is None or access[1] not in PUBLIC_ENV | {
            "MODE",
            "DEV",
            "PROD",
            "BASE_URL",
            "SSR",
        }:
            result.add("unapproved or dynamic browser environment access")
    if re.search(r"\bprocess\.env\b|\benvPrefix\s*:|\bloadEnv\s*\(", text):
        result.add("custom environment exposure requires review")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist", type=Path, help="Scan built web artifacts instead of tracked sources"
    )
    args = parser.parse_args()
    errors = []
    if args.dist:
        if not args.dist.is_dir() or not (args.dist / "index.html").is_file():
            parser.error("Expected built web directory with index.html")
        paths = sorted(p for p in args.dist.rglob("*") if p.is_file())
    else:
        paths = [
            Path(p)
            for p in subprocess.check_output(["git", "ls-files", "-z"], text=True).split("\0")
            if p
        ]
    for path in paths:
        if path.is_symlink():
            errors.append((str(path), "symlink requires review"))
            continue
        if not path.is_file():
            continue
        if private_path(str(path.relative_to(args.dist) if args.dist else path)):
            errors.append((str(path), "private/provider/environment path"))
            continue  # Never inspect private file contents, even if accidentally tracked.
        text = path.read_text(encoding="utf-8", errors="replace")
        categories = findings(text, artifact=bool(args.dist))
        if not args.dist and path == Path("web/.env.example"):
            for line in text.splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                key, separator, value = line.partition("=")
                if key.strip() not in PUBLIC_ENV or not separator or value.strip():
                    categories.add("browser example must contain allowed names and empty values")
        if not args.dist and str(path).startswith("web/") and path.suffix in {".ts", ".tsx", ".js"}:
            categories |= browser_env_findings(text)
        for category in sorted(categories):
            errors.append((str(path), category))
    for path, category in errors:
        print(f"SECURITY: {category}: {path}")
    if errors:
        return 1
    print(f"Security baseline passed: {len(paths)} files; no matching prohibited indicators.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
