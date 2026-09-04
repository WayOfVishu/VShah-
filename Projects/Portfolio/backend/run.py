#!/usr/bin/env python3
"""Entry point — mirrors hwcheck.py's role in the diagnostics project.

    py run.py                    API only, reload on, for use with the Vite dev server
    py run.py --serve-static     one process serving API + built frontend
    py run.py --port 9000        override the port (or set PORT, which hosts inject)
"""

import argparse
import os
import sys

import uvicorn


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the portfolio backend.")
    parser.add_argument(
        "--serve-static",
        action="store_true",
        help="also serve frontend/dist from this process (production single-process mode)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="port to bind (default: $PORT or 8000)",
    )
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--no-reload", action="store_true", help="disable autoreload")
    args = parser.parse_args()

    from app.main import app, mount_static

    if args.serve_static:
        mount_static()

    # Autoreload and static serving do not mix well: reload needs an import
    # string, and mounting happens on the already-constructed app.
    reload = not args.no_reload and not args.serve_static

    print(f"  api    http://{args.host}:{args.port}/api/health")
    print(f"  docs   http://{args.host}:{args.port}/docs")
    if args.serve_static:
        print(f"  site   http://{args.host}:{args.port}/")
    else:
        print("  site   http://localhost:5173  (start it with: cd ../frontend && npm run dev)")

    uvicorn.run(
        "app.main:app" if reload else app,
        host=args.host,
        port=args.port,
        reload=reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
