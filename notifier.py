#!/usr/bin/env python3
"""
Desktop & Audio Notification Specialist
Author: Daniel Suh & Antigravity

Provides cross-platform desktop notifications, audio chimes, and terminal alerts
so the user is immediately alerted when resume generation, email staging, or
pipeline workflows finish—even when working on a different screen or workspace.
"""

import os
import sys
import platform
import subprocess
import shutil
from typing import Optional, Dict, Any

def play_alert_sound(sound_name: str = "Glass") -> bool:
    """
    Plays an audible chime across monitors/spaces.
    On macOS: uses afplay with system sound or osascript beep.
    On Linux: uses paplay / aplay / canberra-gtk-play.
    On Windows: uses winsound or PowerShell beep.
    Also emits a terminal bell '\\a' to bounce terminal/dock icon.
    """
    # Always emit terminal bell for terminal/iTerm/tmux tab bounce
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass

    current_os = platform.system()

    if current_os == "Darwin":
        # macOS: try afplay with standard system sound
        sound_paths = [
            f"/System/Library/Sounds/{sound_name}.aiff",
            f"/System/Library/Sounds/Glass.aiff",
            f"/System/Library/Sounds/Ping.aiff",
            f"/System/Library/Sounds/Hero.aiff"
        ]
        for sp in sound_paths:
            if os.path.exists(sp):
                try:
                    subprocess.Popen(
                        ["afplay", sp],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return True
                except Exception:
                    break
        # Fallback to osascript beep
        try:
            subprocess.Popen(
                ["osascript", "-e", "beep 2"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            return False

    elif current_os == "Linux":
        for player in ["paplay", "aplay", "canberra-gtk-play"]:
            if shutil.which(player):
                sound_file = "/usr/share/sounds/freedesktop/stereo/complete.oga"
                if os.path.exists(sound_file):
                    try:
                        subprocess.Popen(
                            [player, sound_file],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        return True
                    except Exception:
                        pass
        return False

    elif current_os == "Windows":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return True
        except Exception:
            try:
                subprocess.Popen(
                    ["powershell", "-c", "[console]::beep(800, 300)"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                return False

    return False


def send_system_notification(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    sound_name: str = "Glass",
    play_sound: bool = True
) -> bool:
    """
    Displays a native desktop notification banner and plays an alert chime.
    """
    success = False
    current_os = platform.system()

    if current_os == "Darwin":
        # Values are argv data, never executable AppleScript source.
        script = """on run argv
            display notification (item 2 of argv) with title (item 1 of argv) subtitle (item 3 of argv) sound name (item 4 of argv)
        end run"""
        try:
            res = subprocess.run(
                ["osascript", "-e", script, "--", title, message, subtitle or "", sound_name if play_sound else ""],
                capture_output=True,
                text=True,
                timeout=5
            )
            success = (res.returncode == 0)
        except Exception as e:
            success = False

    elif current_os == "Linux":
        if shutil.which("notify-send"):
            try:
                cmd = ["notify-send", title, message]
                if subtitle:
                    cmd = ["notify-send", title, f"{subtitle}\n{message}"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                success = (res.returncode == 0)
            except Exception:
                success = False

    elif current_os == "Windows":
        try:
            ps_script = """
            [reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
            $notify = New-Object System.Windows.Forms.NotifyIcon
            $notify.Icon = [System.Drawing.SystemIcons]::Information
            $notify.BalloonTipTitle = $env:APPLYPILOT_NOTIFICATION_TITLE
            $notify.BalloonTipText = $env:APPLYPILOT_NOTIFICATION_MESSAGE
            $notify.Visible = $True
            $notify.ShowBalloonTip(5000)
            """
            res = subprocess.run(
                ["powershell", "-Command", ps_script],
                env=dict(os.environ, APPLYPILOT_NOTIFICATION_TITLE=title, APPLYPILOT_NOTIFICATION_MESSAGE=message),
                capture_output=True,
                text=True,
                timeout=5
            )
            success = (res.returncode == 0)
        except Exception:
            success = False

    # Audio trigger if requested
    if play_sound:
        play_alert_sound(sound_name=sound_name)

    return success


def notify_pipeline_completion(
    company: str,
    role: str,
    ats_score: Optional[Any] = None,
    contact_name: Optional[str] = None,
    draft_staged: bool = True
) -> bool:
    """
    Sends a tailored high-priority notification specifically formatted for the
    Job Application Co-Pilot pipeline completion.
    """
    title = "👑 Job Application Co-Pilot"
    subtitle = f"Packet Ready: {company}"

    score_str = f"ATS: {ats_score}/100" if ats_score is not None and ats_score != "N/A" else "ATS: Ready"
    stage_str = "Draft Staged in Gmail" if draft_staged else "Resume & Copy Generated"
    contact_str = f" • Contact: {contact_name}" if contact_name else ""

    message = f"{role} ({score_str}) • {stage_str}{contact_str}"

    return send_system_notification(
        title=title,
        message=message,
        subtitle=subtitle,
        sound_name="Glass",
        play_sound=True
    )


def open_in_file_manager(target_path: str, reveal: bool = True) -> bool:
    """
    Opens or reveals a file or folder in the operating system's native file manager.
    On macOS: uses 'open -R <path>' to reveal/highlight the file in Finder, or 'open <path>' for folders/files.
    On Linux: uses 'xdg-open'.
    On Windows: uses 'explorer.exe'.
    """
    if not target_path or not os.path.exists(target_path):
        return False

    current_os = platform.system()
    try:
        if current_os == "Darwin":
            if reveal and os.path.isfile(target_path):
                subprocess.Popen(["open", "-R", str(target_path)])
            else:
                subprocess.Popen(["open", str(target_path)])
            return True
        elif current_os == "Linux":
            subprocess.Popen(["xdg-open", str(target_path)])
            return True
        elif current_os == "Windows":
            if reveal and os.path.isfile(target_path):
                subprocess.Popen(["explorer", f"/select,{target_path}"])
            else:
                subprocess.Popen(["explorer", str(target_path)])
            return True
    except Exception:
        return False
    return False


def get_latest_output_packet(output_base_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Finds the most recently created output folder in Resume/output/.
    Returns dict with directory path, pdf path, and folder name.
    """
    from pathlib import Path
    if output_base_dir:
        base = Path(output_base_dir)
    else:
        base = Path(__file__).resolve().parent / "Resume" / "output"

    if not base.exists():
        return None

    subdirs = [d for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not subdirs:
        return None

    latest_dir = max(subdirs, key=lambda d: d.stat().st_mtime)
    pdfs = list(latest_dir.glob("*.pdf"))
    latest_pdf = pdfs[0] if pdfs else None

    return {
        "dir": str(latest_dir),
        "pdf": str(latest_pdf) if latest_pdf else None,
        "folder_name": latest_dir.name
    }


if __name__ == "__main__":
    print("Testing desktop notification and sound alert...")
    notified = notify_pipeline_completion(
        company="Stripe",
        role="Associate Product Manager",
        ats_score=94,
        contact_name="David Song",
        draft_staged=True
    )
    print(f"Notification triggered: {notified}")
