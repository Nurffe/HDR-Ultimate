# HDR games table: cell dropdowns — implementation note

Branch: `feature/hdr-games-dropdowns` (off `feature/vrr-toggle`)
Scope: **Linux only.** `linux/hdr_ultimate.py`, `linux/test_hdr_ultimate.py`, `linux/test_flow.py`, `linux/README.md`.

## What changed

- The last column is **HDR** (was "On launch"). Values are `Ask` / `On`, matching the dropdown's
  "Ask me first" / "Turn HDR on automatically".
- **Monitors, Display mode, VRR and HDR** cells are dropdowns. A single click opens one
  (`Settings.cell_click`); the **Game** and **Exe** cells keep double-click, because one of their
  actions removes the game (`Settings.cell_double`). Enter/Space/F2/menu key open any cell
  (`Settings.table_key`, replacing `cellActivated` so a dropdown is not opened twice).
- Dropdown cells carry a trailing `▾` in `refill`, and the hint above the table reads
  "Click a cell and pick an option from the dropdown".
- Every dropdown ends with **More options…**, which opens the full `GameDialog`.

## Decisions (from the user's answers)

1. **HDR column values:** `Ask` / `On`.
2. **VRR is tri-state:** `always` ("Turn VRR on while playing"), `never` ("Turn VRR off while
   playing"), `""` ("No change"). `Game.vrr` changed from `bool` to `str`; `Config.load` migrates a
   stored boolean (`true` → `"always"`, `false` → `""`) and clamps anything else to `""`.
3. **Display mode** is one menu with three submenus — **Monitor**, **Resolution**, **Refresh rate** —
   plus a mutually exclusive pair for where the setting applies (desktop / the game's own settings
   file). It no longer opens the full dialog as its only option.

## Data model

- `VrrHolds.held` entries gained `"after"`: the policy the game asked for. Hand-backs (stop, release,
  restart recovery) only write when the monitor still reads that policy, so a mid-game manual change
  is still kept. Holds written by older versions default to `"after": "always"`.
- `forget_games` now returns `(monitor_id, before, after)`; `TrayApp.check_games` filters on
  `mons[mid].vrr_policy == after`.
- `start_vrr` passes `g.vrr` to `VrrHolds.start(key, usable, word)` and logs the word.

## Pure helpers (unit-testable without Qt)

- `hdr_summary(game)` → `Ask` / `On`
- `vrr_summary(game)` → `On` / `Off` / `No change`
- `monitor_choices(selected, connected)` → `[(id, label, checked, enabled)]`; the last checked
  monitor is disabled so a game always keeps one.
- `mode_choices(game, connected)` → `{"monitor": [...], "resolution": [...], "refresh": [...],
  "in_game": bool}`; each list is `[(value, label, checked, enabled)]`. The refresh list carries every
  rate the monitor offers, because the menu is built once: picking a new resolution pulls the stored rate
  down to one that resolution offers (`fallback_rate`), and the full dialog still offers the common
  480→60 fallback list.

`MonitorMenu` (the dialog's button) now builds its menu from `monitor_choices`, so the dialog and the
table share one rule set.

## Tests

- `test_hdr_ultimate.py`: new `ChoiceLists` suite; VRR tests updated for the tri-state model plus
  `test_games_can_ask_for_never`, `test_game_vrr_values_survive_a_config_round_trip`,
  `test_old_boolean_vrr_flag_migrates`, `test_vrr_summary`,
  `test_holds_from_before_never_existed_put_always_back`.
- `test_flow.py`: every column opens a dropdown, last column is `HDR`, dropdown cells show `▾`, the
  display-mode dropdown offers the separate submenus and saves a resolution chosen there, and the VRR
  dropdown's "Turn VRR off while playing" is stored as `"never"` and shown as `Off`.

Run:

```bash
cd linux
python3 -m unittest test_hdr_ultimate
python3 test_flow.py "$(mktemp -d)"     # needs PySide6
```

## Settings › General row order

Follow-up request: the version/update rows moved below the VRR switch. `general_page` appends rows in
reading order instead of inserting them at fixed indexes — theme, start at login, on-screen notice,
auto HDR, then "Let the system manage VRR" + its hint, then the anonymous-count row, then
check-for-updates and the version row, then the dev Logs row, and `Desktop: …` last of all.
`test_flow.py` asserts the VRR switch sits below the four behaviour rows and above any version row,
and that `Desktop: …` is the final row.

## Known limits

- The table's VRR cell is hidden on desktops that don't manage VRR (GNOME), as before.
- Refresh rates in the table dropdown are every rate the monitor reports; choosing a size the current
  rate doesn't support falls back to the nearest offered one. The full dialog additionally offers the
  common rates with a fallback note.
- A dropdown cell opens on a single click only after `QApplication.doubleClickInterval()`, so a
  double-click can cancel it instead of the second click landing in the open menu.
