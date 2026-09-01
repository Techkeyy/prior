from __future__ import annotations

import argparse

import uvicorn

from prior.settings import host, port


def main() -> None:
    parser = argparse.ArgumentParser(description="PRIOR")
    parser.add_argument("--host", default=host())
    parser.add_argument("--port", type=int, default=port())
    args = parser.parse_args()
    uvicorn.run("prior.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
