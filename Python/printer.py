
import sys
import threading

COLOR_RED = "\033[91m"
COLOR_RESET = "\033[0m"

def perror(error, prefix=None):
    print(f"{COLOR_RED}{f"[{prefix}] " if prefix is not None else ""}{error}{COLOR_RESET}", file=sys.stderr)

def _prefix_stderr(process, prefix):
    with process.stderr:
        for line in process.stderr:
            error = line.strip()
            print(f"{COLOR_RED}[{prefix}] {error}{COLOR_RESET}", file=sys.stderr)

def monitor_stderr(process, prefix):
    threading.Thread(
        target=_prefix_stderr,
        args=(process, prefix),
        daemon=True
    ).start()
