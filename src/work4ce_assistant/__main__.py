"""CLI routes protected operations through the authenticated API."""
import argparse
import json
import os
import sys

import httpx

from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="work4ce", description="Work4ce Assistant synthetic SOC foundation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version")
    commands.add_parser("doctor")
    commands.add_parser("health")
    database = commands.add_parser("database")
    database.add_argument("action", choices=["migrate"])
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    demo = commands.add_parser("demo")
    demo_sub = demo.add_subparsers(dest="action", required=True)
    investigate = demo_sub.add_parser("investigate")
    investigate.add_argument("--query", default="PowerShell")
    for name in ("connectors", "capabilities"):
        sub = commands.add_parser(name)
        sub.add_argument("action", choices=["list"])
    args = parser.parse_args()
    if args.command == "version":
        print(__version__)
        return
    if args.command == "database":
        from .storage import migrate
        try:
            migrate(os.environ.get("WORK4CE_DB", ".local/work4ce.db"))
        except Exception:
            parser.exit(1, "Database migration failed; verify connectivity, permissions and schema. Credentials are not logged.\n")
        print("Database schema is current.")
        return
    if args.command == "serve":
        import uvicorn
        from .api import Settings, create_app
        uvicorn.run(create_app(Settings.from_environment()), host="127.0.0.1", port=args.port, access_log=False)
        return
    if args.command == "doctor":
        from .api import Settings
        try:
            Settings.from_environment()
        except ValueError as error:
            parser.exit(1, str(error) + "\n")
        print("Demo settings valid. Production disabled. Use health for API connectivity.")
        return
    # Fixed local demo API; tokens never forwarded to a user-specified URL.
    token = os.environ.get("WORK4CE_ACCESS_TOKEN", "") if os.environ.get("WORK4CE_AUTH_MODE") == "oidc" else os.environ.get("WORK4CE_DEMO_TOKEN", "")
    headers = {"Authorization": "Bearer " + token} if token else {}
    try:
        with httpx.Client(base_url="http://127.0.0.1:8765", trust_env=False, timeout=30) as client:
            if args.command == "demo":
                response = client.post("/investigations", json={"query": args.query}, headers=headers)
            else:
                response = client.get("/" + args.command, headers=headers)
            response.raise_for_status()
            print(json.dumps(response.json(), indent=2))
    except (httpx.HTTPError, ValueError):
        print("API request failed; check local services, authentication, and audit events.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
