"""Clipboard writing that prefers a native CLI tool, falling back to the
terminal's OSC 52 escape sequence.

Textual's own ``App.copy_to_clipboard`` only ever emits OSC 52. Several
terminal emulators and multiplexers (tmux without ``set-clipboard``, some
Linux terminal defaults) strip or ignore that sequence, which makes copying
silently do nothing. Shelling out to a clipboard tool when one is installed
sidesteps that entirely.
"""
from __future__ import annotations

import shutil
import subprocess


def _tool_command() -> list[str] | None:
    if shutil.which("wl-copy"):
        return ["wl-copy"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel"):
        return ["xsel", "--clipboard", "--input"]
    return None


def copy_via_external_tool(text: str) -> bool:
    """Write ``text`` to the system clipboard via an external CLI tool.
    Returns False (never raises) if none is available or it fails, so the
    caller can fall back to another method."""
    command = _tool_command()
    if command is None:
        return False
    try:
        subprocess.run(command, input=text.encode("utf-8"), check=True, timeout=2)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
