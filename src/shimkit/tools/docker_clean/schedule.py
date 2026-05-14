"""Generate scheduling snippets (do NOT install them).

``shimkit docker-clean schedule --interval=weekly`` prints a launchd
plist (macOS) or systemd timer (Linux) or cron line. The user is the
one who installs it — we never modify their crontab or load a launchd
unit on their behalf.
"""

from __future__ import annotations

from shimkit.core import Platform

_LAUNCHD_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyLists-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.simtabi.shimkit.docker-clean.{interval}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string><string>shimkit</string>
        <string>docker-clean</string><string>quick</string><string>--yes</string>
    </array>
    <key>StartCalendarInterval</key>
    {calendar}
    <key>RunAtLoad</key><false/>
</dict>
</plist>
"""

_SYSTEMD_TIMER = """\
[Unit]
Description=shimkit docker-clean ({interval})

[Timer]
OnCalendar={oncalendar}
Persistent=true

[Install]
WantedBy=timers.target
"""

_SYSTEMD_SERVICE = """\
[Unit]
Description=shimkit docker-clean ({interval})

[Service]
Type=oneshot
ExecStart=/usr/bin/env shimkit docker-clean quick --yes
"""

_CRON_LINE = "# shimkit docker-clean — {interval}\n{cron} shimkit docker-clean quick --yes\n"


def _macos_calendar(interval: str) -> str:
    # Run weekly Mondays 03:00; daily 03:00 if --daily.
    if interval == "daily":
        return "<dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>"
    return (
        "<dict><key>Weekday</key><integer>1</integer>"
        "<key>Hour</key><integer>3</integer>"
        "<key>Minute</key><integer>0</integer></dict>"
    )


def _systemd_oncalendar(interval: str) -> str:
    return "*-*-* 03:00:00" if interval == "daily" else "Mon *-*-* 03:00:00"


def _cron(interval: str) -> str:
    return "0 3 * * *" if interval == "daily" else "0 3 * * 1"


def emit(interval: str = "weekly", platform: Platform | None = None) -> str:
    """Return the scheduling snippet for the current platform."""
    plat = platform or Platform.detect()
    if plat.is_macos:
        return _LAUNCHD_TEMPLATE.format(
            interval=interval, calendar=_macos_calendar(interval)
        )
    if plat.is_linux:
        return (
            f"# Save the following two files as:\n"
            f"#   ~/.config/systemd/user/shimkit-docker-clean.timer\n"
            f"#   ~/.config/systemd/user/shimkit-docker-clean.service\n"
            f"# Then: systemctl --user daemon-reload && "
            f"systemctl --user enable --now shimkit-docker-clean.timer\n\n"
            f"--- shimkit-docker-clean.timer ---\n"
            f"{_SYSTEMD_TIMER.format(interval=interval, oncalendar=_systemd_oncalendar(interval))}\n"
            f"--- shimkit-docker-clean.service ---\n"
            f"{_SYSTEMD_SERVICE.format(interval=interval)}"
        )
    return _CRON_LINE.format(interval=interval, cron=_cron(interval))
