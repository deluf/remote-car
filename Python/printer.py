
import sys
import threading

COLOR_RED = "\033[91m"
COLOR_RESET = "\033[0m"

def perror(error, prefix=None):
    """
    Prints an error message to standard error in red color, optionally 
    prefixed by a given string.

    Args:
        error (str): The error message to print.
        prefix (str, optional): A string prefix to prepend to the error message.
                                If None, no prefix is added.

    Returns:
        None
    """
    print(f"{COLOR_RED}{f"[{prefix}] " if prefix is not None else ""}{error}{COLOR_RESET}", file=sys.stderr)

def _prefix_stderr(process, prefix):
    with process.stderr:
        for line in process.stderr:
            error = line.strip()
            print(f"{COLOR_RED}[{prefix}] {error}{COLOR_RESET}", file=sys.stderr)

def monitor_stderr(process, prefix):
    """
    Spawns a thread that continuously reads lines from the standard error 
     stream of the given process, prefixes each line with the specified prefix,
     and prints it in red to the standard error output. 
    The process must be launched with stderr=subprocess.PIPE, text=True

    Args:
        process: A subprocess.Popen object (or similar) with a stderr attribute.
        prefix: A string to prepend to each stderr line.
    
    Returns:
        None
    """
    threading.Thread(
        target=_prefix_stderr,
        args=(process, prefix),
        daemon=True
    ).start()
