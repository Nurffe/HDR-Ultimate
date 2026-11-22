# HDR Ultimate for Windows

Per-monitor HDR control with hotkeys, game detection, prompts, banners, OLED care, per-game display mode and light/dark themes. Windows 10 and 11.

## HDR games

The **HDR games** tab lists one row per game, with a column each for the **Game**, its **Exe**, the **Monitors** it applies to, its **Display mode** and what happens **On launch**. Double-click a cell to change it; the **Game** and **Exe** cells open their action menu instead, since one of those actions removes the game.

- **Monitors** — a tick per monitor; only monitors that report HDR support can be ticked.
- **Display mode** — the resolution and refresh rate to use while playing, either applied to the desktop or written into the game's own settings file (for the five games the app knows, or a file you pick).
- **On launch** — **Ask me first** or **Turn HDR on automatically**. A game you open while a prompt is on screen gets an **Always for this game** button, so you can stop being asked about it.

## Needs

- Windows 10 or 11
- Nothing to install: the release is a single `.exe`. It is a .NET Framework 4.x WinForms app, and that runtime ships with Windows.

## Install

Download `HDRUltimate<version>.exe` and run it. There is no installer. Look for the icon in the system tray; open **Settings** from its menu to add games and set hotkeys.

On first run it offers to start with Windows, which it registers as a Task Scheduler logon task (falling back to the usual `Run` key if the task can't be created). The exe can be moved afterwards, and the entry is repaired at startup.

## Updating

HDR Ultimate tells you when a new version is out (you can turn this off under Settings > General). Close it and run the new `.exe`: on startup it closes any older copy still running and moves that old exe to the Recycle Bin, so a folder full of previous downloads stays tidy.

## Tray

The tray menu lists each monitor with its HDR state, marked **— no HDR** when the monitor doesn't support it; clicking a monitor switches HDR for it. Below that: any game currently detected, an update notice when there is one, **Settings** and **Exit**.

HDR changes made anywhere — the tray, a hotkey, a game starting, or Windows Settings itself — are reflected in the tray icon, the menu and now and then an on-screen confirmation. None of those windows ever take focus away from the game.

## Hotkeys

Settings > **Monitor hotkeys** assigns a global hotkey per monitor (or to all monitors at once). Click **Add hotkey** and press the combination in the box. These are real system-wide hotkeys, so they work while a game has focus.

## OLED care

Settings > **OLED care** turns HDR off once you have been tabbed out of a game for a set number of minutes (5 by default) and back on when you return, so a paused game doesn't leave a static HDR image on the panel. It works for every game the app detects, including ones running with an anti-cheat.

## Differences from Linux

- **VRR:** not supported. Variable refresh rate control is Linux/KDE only; there is no equivalent here, and the tray shows no VRR rows.
- **Hotkeys:** real global hotkeys, registered with the OS and captured in-app. On Linux/Wayland the app can't grab keys, so it hands you a command to add as a desktop shortcut instead.
- **OLED care:** sees every game, because the foreground window and its process can be read directly. The Linux build only sees games running through XWayland (Proton), and stays inactive for native Wayland games.
- **Game settings files:** found under `%LOCALAPPDATA%`, `Documents`, `My Games`, `Saved Games` and `LocalLow`. There is no Steam/Proton prefix to search, so the Linux-only Proton path handling has no counterpart here.
- **Updating:** the old exe is moved to the Recycle Bin. Linux replaces the installed copy from the tarball and only asks the old process to quit.
- **Other builds:** `build.cmd dev` adds a console log, a **Dev** tab with event triggers, and `--dev-game`. Each build has its own settings folder and startup entry.

## Troubleshooting

Run `HDRUltimate.exe --list` to print the monitors the app detects, their HDR support and their current state, then exits. The dev build (`build.cmd dev`) writes a console log of every HDR switch, display-mode change and its own startup state, which is what to send with a bug report.

**A monitor says "no HDR".** The app asks Windows whether the display supports advanced colour. On Windows 10 that answer also covers wide colour gamut, so a wide-gamut-only panel can be listed as capable while switching on does nothing visible; on Windows 11 24H2 and later the two are reported separately and the state matches Windows Settings exactly.

**HDR won't switch while "Automatically manage colour for apps" is on.** That Windows feature (Settings > System > Display > Colour management) sits between the app and the display. Turn it off to control HDR from the tray.

**HDR stops working on a monitor for the rest of the session.** Windows had trouble switching that monitor's display mode, so the app stops changing it and says so once. HDR is not affected. Restarting the app clears it.

## Build from source

No SDK needed. `build.cmd` uses the C# compiler that ships with Windows (.NET Framework 4.x).

```
cd windows
build.cmd            :: release build
build.cmd dev        :: console log and a Dev tab with event triggers
build.cmd playtest   :: log file and crash reports
build.cmd all        :: all three
```

Each build has its own settings folder and startup entry, so they never touch each other's data.
