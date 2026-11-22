# HDR Ultimate for Linux

Per-monitor HDR control with game detection, prompts, banners, OLED care, per-game resolution, refresh rate and VRR, and light/dark themes.

## Needs

- Wayland with **KDE Plasma 6** or **GNOME 48+**
- Python 3.9+ (the installer fetches Qt if it's missing)
- GNOME: `python3-gi`, and the AppIndicator extension if your distro doesn't include it, for the tray icon
- OLED care: `xprop` (`x11-utils` or `xorg-xprop`)

## Install

```bash
tar xzf HDRUltimate-Linux.tar.gz
cd HDRUltimate-Linux
sh install.sh
```

Remove it with `sh install.sh --uninstall`.

## Updating

HDR Ultimate tells you when a new version is out (you can turn this off under Settings > General). Download it and run `sh install.sh` again: it replaces the installed copy, and the next launch closes the old version if it's still running.

## Differences from Windows

- **Hotkeys:** Wayland doesn't let apps grab keys. Copy a command from Settings > Monitor hotkeys and add it as a custom shortcut in your desktop's keyboard settings.
- **OLED care:** only sees games running through XWayland, which covers Proton games. For native Wayland games it stays inactive rather than risk turning HDR off mid-game.
- **Game detection:** matches the exe file name, including inside Proton's process arguments.
- **Other builds:** `--dev` adds event triggers and `--playtest` keeps a log. Each has its own settings folder.

## VRR (variable refresh rate)

VRR control needs KDE Plasma. On GNOME the app reads no VRR policy and shows nothing about it; per-game VRR says "VRR management needs KDE Plasma".

Plasma has three VRR policies per monitor:

- **Always**: adaptive sync all the time, windowed and borderless games included.
- **Automatic**: adaptive sync only for fullscreen windows. This is Plasma's default.
- **Never**: off.

The tray's VRR box is a plain on/off switch: ticked is **Always**, unticked is **Never**. A monitor on Automatic shows unticked. If you want Automatic, turn on "Let the system manage VRR" and pick it in System Settings > Display.

The tray menu lists each monitor, marked with a monitor icon (click it for Settings). Under each name sit its HDR and VRR rows, indented and marked with a ticked box when on and an empty box when off. A greyed row says why: **(N/A)** when the monitor doesn't support it, **(system)** while the system manages VRR (the box still shows the real state), **(paused)** when the desktop had display-mode trouble with that monitor this session.

Per-game VRR is different: the app turns the monitor to Always when the game starts and puts back the exact policy that was there, Automatic included, when the game closes or the app exits. A monitor that was already Always before a game started is not touched and is not turned off afterwards: it wasn't the app's change to undo.

**"Let the system manage VRR" (Settings > General)** is on by default. While it is on, the app writes no VRR policy at all: no tray switch, no hotkey, no per-game setting. It is the safe default because a policy change makes the desktop reconfigure the output, exactly like a resolution change. Turn it off — or pick "Let HDR Ultimate manage VRR" from the tray — to control VRR from the app.

**A blocked monitor.** If the desktop had trouble switching a monitor's display mode during this session, the app leaves that monitor's VRR alone as well and says so once. HDR still works there. Restarting the app clears it. Handing a policy back (a game closing, quitting, turning management back on) is always allowed, because leaving a policy the app wrote in place is worse.

**OLED care ignores VRR.** OLED care turns HDR off for a game it loses focus on; it does not touch the VRR policy, so your refresh rate behaviour doesn't change while a game is tabbed out.

**Doing it by hand.** Policies are per monitor and take the connector name from `kscreen-doctor -o`:

```bash
kscreen-doctor output.DP-1.vrrpolicy.always
kscreen-doctor output.DP-1.vrrpolicy.automatic
```

**Downgrading.** Settings written by a version with VRR are read by an older one without complaint; it ignores the `vrr_*` keys and leaves them in the file. If an old build is left holding a monitor on Always, set it back with the command above.

## Troubleshooting

Run `hdr-ultimate --list` to see what the app detects. To test the interface without HDR hardware, run `hdr-ultimate --dev --fake`.

**KDE lists no monitors, or "Pick monitors" is empty.** Compare `kscreen-doctor -o` with `QT_QPA_PLATFORM=xcb kscreen-doctor -o`: if the first prints your outputs and the second prints nothing, that is the cause. From libkscreen 6.8 (Plasma 6.8) the XRandR backend is gone, so `kscreen-doctor` only ever loads its Wayland backend, and that one finds outputs solely through the Wayland connection of its own process. Started under X/Wayland (`QT_QPA_PLATFORM=xcb`) it therefore reports no outputs and still exits successfully. HDR Ultimate runs its own windows through XWayland and drops that variable from every `kscreen-doctor` it starts for this reason; if you set it yourself, use a `wayland` value. Run `hdr-ultimate --dev` to see the monitor list the app works from.
