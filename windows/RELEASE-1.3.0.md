# HDR Ultimate 1.3.0 (Windows)

Windows changes only; the Linux build is unchanged.

## Fixed

- **HDR shown as on when it wasn't.** On Windows 11 24H2 and later with
  "Automatically manage colour for apps" on, the tray read your stored HDR
  preference instead of the live display mode, so a panel sitting in SDR or
  wide colour gamut was listed as HDR. The state now comes from the colour mode
  Windows reports as active, which matches Settings.
- **A switch that reports success without switching.** HDR on or off is now
  read back after the change instead of assuming that a successful call changed
  the display, so a failed switch says so rather than leaving the tray wrong.

## Known limits

- **Windows 10 cannot tell HDR from wide colour gamut.** Its version of the
  display API reports both as one "advanced colour" flag, so "no HDR" and
  "HDR" can each be wrong on a panel that supports only one of the two. There is
  no better signal before Windows 11 24H2.
- **A policy-blocked monitor** is recorded in the dev log
  (`blocked by policy=true`) instead of looking like a random toggle failure.
  It is not yet shown in the tray.
