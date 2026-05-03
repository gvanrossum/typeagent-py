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
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", script],
                timeout=30,
            )
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Prevent screen lock by wiggling the mouse (WSL)."
    )
    parser.add_argument(
        "-i", "--interval", type=float, default=60.0, help="Seconds between wiggles"
    )
    parser.add_argument(
        "-w", "--wiggle", action="store_true", help="Also wiggle the mouse"
    )
    parser.add_argument(
        "-a", "--amplitude", type=int, default=20, help="Pixel amplitude (with --wiggle)"
    )
    args = parser.parse_args()
    keep_alive(args.interval, args.amplitude if args.wiggle else None)
