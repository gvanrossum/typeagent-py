# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Prevent screen lock (WSL-friendly).

Each cycle calls a short-lived PowerShell process that calls
SetThreadExecutionState to tell Windows the display is required.

Python owns the sleep loop so Ctrl+C works normally.
"""

import subprocess
import textwrap
import time

# PowerShell snippet: tell Windows the display is required.
_PS_SCRIPT = textwrap.dedent("""\
    Add-Type -TypeDefinition @"
    using System;
    using System.Runtime.InteropServices;
    public class KeepAlive {
        const uint ES_CONTINUOUS       = 0x80000000;
        const uint ES_SYSTEM_REQUIRED  = 0x00000001;
        const uint ES_DISPLAY_REQUIRED = 0x00000002;
        [DllImport("kernel32.dll")]
        static extern uint SetThreadExecutionState(uint esFlags);
        public static void PreventSleep() {
            SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED);
        }
    }
"@
    [KeepAlive]::PreventSleep()
""")


def _ping() -> None:
    """Run one keep-alive ping via PowerShell."""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", _PS_SCRIPT],
        timeout=30,
    )


def keep_alive(interval: float = 60.0) -> None:
    """Prevent screen lock. Runs until Ctrl+C."""
    print(
        f"Keeping alive (every {interval}s). Ctrl+C to stop.",
        flush=True,
    )
    try:
        while True:
            _ping()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


def keep_alive_for_command(
    command: list[str],
    interval: float = 60.0,
) -> int:
    """Run command, keeping screen alive until it exits. Returns exit code."""
    print(
        f"Running: {' '.join(command)}",
        flush=True,
    )
    print(
        f"Keeping alive (every {interval}s) until process exits.",
        flush=True,
    )
    proc = subprocess.Popen(command)
    try:
        while True:
            _ping()
            try:
                proc.wait(timeout=interval)
                break
            except subprocess.TimeoutExpired:
                pass
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        print("\nInterrupted.", flush=True)
    return proc.returncode or 0


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Prevent screen lock (WSL). Optionally wraps a command.",
        usage="%(prog)s [options] [-- command ...]",
    )
    parser.add_argument(
        "-i", "--interval", type=float, default=60.0, help="Seconds between pings"
    )
    parser.add_argument(
        "command", nargs=argparse.REMAINDER, help="Command to run (after --)"
    )
    args = parser.parse_args()

    # Strip leading "--" from command if present
    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if cmd:
        sys.exit(keep_alive_for_command(cmd, args.interval))
    else:
        keep_alive(args.interval)
