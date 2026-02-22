import os
import subprocess
import sys


def main() -> int:
    port = os.getenv("PORT", "8000")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    print("Starting server:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
