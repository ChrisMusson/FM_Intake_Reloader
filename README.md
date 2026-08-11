# FM_Tools

Cross-platform Football Manager toolkit for:

- youth intake reloading
- shortlist-based player scanning
- shortlist-based coach scanning
- coach assignment optimisation

The scripts you are meant to run live at the repo root. Everything in `core/` is shared support code, and `tools/` contains calibration/debug helpers.

## Setup

1. Install `uv`.
2. Run `uv sync` from the repo root.
3. Keep Football Manager open while using any script that reads memory.
4. Before you run `preview_day.py` or `intake_day.py`, calibrate your screen once. See the "Preview / Intake Reloading" section below. The values committed in `core/ui/screen_config.py` are for one specific display and will not match yours.

On Linux, install `spectacle` for screenshots:

- Debian/Ubuntu: `sudo apt install kde-spectacle`
- Fedora: `sudo dnf install spectacle`
- Arch: `sudo pacman -S spectacle`

## Main Scripts

- `preview_day.py`
  Reloads the intake preview day until the star/grade preview matches your thresholds.
- `intake_day.py`
  Reloads the actual intake day until a player hits your CA/PA targets.
- `scan_players.py`
  Builds `player_table.html` from a player shortlist export.
- `scan_coaches.py`
  Builds `staff_table.html` from a staff shortlist export.
- `optimise_coaches.py`
  Finds the best one-coach-per-area training setup from a staff shortlist export.

## Coach Scan

Use `scan_coaches.py` when you want a sortable staff report in the browser.

1. In Football Manager, open the staff search screen.
2. Add `UID` to the view.
3. Export the results as a web page and save it as `staff_shortlist.html` in the repo root.
4. Open `scan_coaches.py` and edit the config block if needed:
   - `INCLUDE_CURRENT_CLUB_STAFF` to add the current manager's club staff from memory
   - `MIN_ANY_CATEGORY_STARS` to keep only coaches with at least one coaching category at or above a given star rating
5. Run `uv run scan_coaches.py`.
6. Open `staff_table.html`.

Useful extra columns in the FM view are `Name`, `Club`, `Age`, `Wage`, and licence/qualification columns, but `UID` is the only required one.

The generated report includes each shortlisted coach's scores across the training categories and can be sorted/filtered in the browser.

## Coach Optimisation

Use `optimise_coaches.py` when you want the best unique assignment of coaches to training areas.

1. Export `staff_shortlist.html` as above.
2. Open `optimise_coaches.py`.
3. Edit the config block at the top if needed:
   - `ALLOWED_CLUBS`
   - `EXCLUDED_AREAS`
   - `INCLUDE_CURRENT_CLUB_STAFF`
   - `MIN_ANY_CATEGORY_STARS`
   - `EXTRA_UIDS`
   - `INCLUDED_UIDS`
   - `EXCLUDED_UIDS`
4. Run `uv run optimise_coaches.py`.
5. Read the assignment table printed in the terminal.

What it does:

- reads the shortlisted staff from `staff_shortlist.html`
- adds the current manager automatically
- optionally adds the current manager's club staff from memory
- optionally adds extra staff by UID even if they are not in the shortlist export
- assigns at most one training area to each coach
- maximises total raw coaching role score across the active training areas

Notes:

- `ALLOWED_CLUBS = []` means do not filter by club.
- `None` inside `ALLOWED_CLUBS` means unemployed / no club.
- `EXCLUDED_AREAS = [TRAINING_AREAS.SET_PIECES]` is useful if you do not care about set pieces.

## Player Scan

Use `scan_players.py` when you want a sortable player report for specific roles. The attribute weighting for each role/duty can be found in `core/scouting/players/role_definitions.py`

1. In Football Manager, open player search.
2. Add `UID` to the view.
3. Export the results as a web page and save it as `player_shortlist.html` in the repo root.
4. Open `scan_players.py` and edit the config block if needed:
   - `INCLUDE_CURRENT_SQUAD_PLAYERS` to add every player found in the current club's known squad buckets from memory
   - `ROLES`
5. Run `uv run scan_players.py`.
6. Open `player_table.html`.

## Preview / Intake Reloading

Before using `preview_day.py` or `intake_day.py`, calibrate your screen positions once:

1. Run `uv run -m tools.calibration`.
2. Follow the prompts.
3. Do this on a layout/zoom/skin you actually use in game.

Typical preview/intake workflow:

1. Make a save just before the intake preview day or intake day.
2. Open the relevant script and change the threshold values at the top.
3. Bring Football Manager to the foreground.
4. Run either `uv run preview_day.py` or `uv run intake_day.py`.

## Tools

The helper tools are intended to be run as modules:

- `uv run -m tools.calibration`
- `uv run -m tools.squad`

## Notes

- The automation scripts assume Football Manager is visible, focused, and using the same layout you calibrated for.
- You should not need to run anything inside `core/` directly.
