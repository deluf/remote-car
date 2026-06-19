import sys
import threading

COLOR_RED = "\033[91m"
COLOR_RESET = "\033[0m"

def perror(error, prefix=None):
    # Print error message in red to stderr
    prefix_str = f"[{prefix}] " if prefix is not None else ""
    print(f"{COLOR_RED}{prefix_str}{error}{COLOR_RESET}", file=sys.stderr)

def _prefix_stderr(process, prefix):
    # Read process stderr line by line and print with prefix
    with process.stderr:
        for line in process.stderr:
            print(f"{COLOR_RED}[{prefix}] {line.strip()}{COLOR_RESET}", file=sys.stderr)

def monitor_stderr(process, prefix):
    # Start a daemon thread to monitor stderr of a process
    threading.Thread(
        target=_prefix_stderr,
        args=(process, prefix),
        daemon=True
    ).start()
