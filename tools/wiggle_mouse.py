# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Prevent screen lock by periodically wiggling the mouse (WSL-friendly).

Each cycle calls a short-lived PowerShell process that:
1. Calls SetThreadExecutionState to tell Windows the display is required.
2. Wiggles the mouse via SendInput.

Python owns the sleep loop so Ctrl+C works normally.
"""

import subprocess
import textwrap
import time

# PowerShell preamble: compile the C# helper once per invocation.
_PS_PREAMBLE = textwrap.dedent("""\
    Add-Type -TypeDefinition @"
    using System;
    using System.Runtime.InteropServices;
    public class KeepAlive {
        const uint ES_CONTINUOUS       = 0x80000000;
        const uint ES_SYSTEM_REQUIRED  = 0x00000001;
        const uint ES_DISPLAY_REQUIRED = 0x00000002;
        [DllImport("kernel32.dll")]
        static extern uint SetThreadExecutionState(uint esFlags);
        [StructLayout(LayoutKind.Sequential)]
        public struct MOUSEINPUT {
            public int dx; public int dy;
            public uint mouseData; public uint dwFlags;
            public uint time; public IntPtr dwExtraInfo;
        }
        [StructLayout(LayoutKind.Sequential)]
        public struct INPUT { public uint type; public MOUSEINPUT mi; }
        [DllImport("user32.dll", SetLastError = true)]
        static extern uint SendInput(uint n, INPUT[] inputs, int size);
        public static void PreventSleep() {
            SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED);
        }
        public static void MoveMouse(int dx, int dy) {
            var inp = new INPUT();
            inp.type = 0;
            inp.mi.dx = dx; inp.mi.dy = dy;
            inp.mi.dwFlags = 0x0001;
            SendInput(1, new INPUT[] { inp },
                      Marshal.SizeOf(typeof(INPUT)));
        }
    }
"@
""")


def _ps_script(amplitude: int | None) -> str:
    """Return a PowerShell snippet that prevents sleep (and optionally wiggles)."""
    script = _PS_PREAMBLE + "[KeepAlive]::PreventSleep()\n"
    if amplitude is not None:
        script += (
            f"[KeepAlive]::MoveMouse({amplitude}, 0)\n"
            f"Start-Sleep -Milliseconds 100\n"
            f"[KeepAlive]::MoveMouse(-{amplitude}, 0)\n"
        )
    return script


def _ping(script: str) -> None:
    """Run one keep-alive ping via PowerShell."""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        timeout=30,
    )


def keep_alive(
    interval: float = 60.0, amplitude: int | None = None
) -> None:
    """Prevent screen lock. Runs until Ctrl+C."""
    script = _ps_script(amplitude)
    wiggle_msg = f", wiggle {amplitude}px" if amplitude else ""
    print(
        f"Keeping alive (every {interval}s{wiggle_msg}). Ctrl+C to stop.",
        flush=True,
    )
    try:
        while True:
            _ping(script)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


def keep_alive_for_command(
    command: list[str],
    interval: float = 60.0,
    amplitude: int | None = None,
) -> int:
    """Run command, keeping screen alive until it exits. Returns exit code."""
    script = _ps_script(amplitude)
    wiggle_msg = f", wiggle {amplitude}px" if amplitude else ""
    print(
        f"Running: {' '.join(command)}",
        flush=True,
    )
    print(
        f"Keeping alive (every {interval}s{wiggle_msg}) until process exits.",
        flush=True,
    )
    proc = subprocess.Popen(command)
    try:
        while True:
            _ping(script)
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
        "-w", "--wiggle", action="store_true", help="Also wiggle the mouse"
    )
    parser.add_argument(
        "-a", "--amplitude", type=int, default=20, help="Pixel amplitude (with --wiggle)"
    )
    parser.add_argument(
        "command", nargs=argparse.REMAINDER, help="Command to run (after --)"
    )
    args = parser.parse_args()
    amp = args.amplitude if args.wiggle else None

    # Strip leading "--" from command if present
    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if cmd:
        sys.exit(keep_alive_for_command(cmd, args.interval, amp))
    else:
        keep_alive(args.interval, amp)
