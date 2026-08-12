"""Build an HTML scouting report for a player shortlist export."""

import pandas as pd

from core.memory.players import build_shortlist_player_table
from core.memory.process import open_fm_process
from core.scouting.html import build_sortable_table_html
from core.scouting.money import format_currency, parse_money_text
from core.scouting.players.role_scoring import filter_players_for_roles, score_players_for_roles
from core.scouting.players.roles import ROLE
from core.scouting.players.shortlist import append_current_squad_players, fill_columns_from_memory, normalise_shortlist_export
from core.scouting.shortlists import coalesce_columns, load_shortlist_table

SHORTLIST_PATH = "player_shortlist.html"
OUTPUT_PATH = SHORTLIST_PATH.replace("shortlist", "table")  # point SHORTLIST_PATH at any export and its report lands beside it
EXTRA_COLUMNS = ["Value", "CA", "PA"]  # memory-only columns, shown only when listed here
DISPLAY_COLUMN_ORDER = ["Nat", "Club", "Wage", "Age", "Name", "Position"]
INCLUDE_CURRENT_SQUAD_PLAYERS = False  # add all current club players from memory even if they are not in the shortlist export
ROLES = [
    ROLE.SWEEPER_KEEPER.DEFEND,
    ROLE.FULL_BACK.ATTACK,
    ROLE.INVERTED_WING_BACK.ATTACK,
    ROLE.BALL_PLAYING_DEFENDER.DEFEND,
    ROLE.DEFENSIVE_MIDFIELDER.SUPPORT,
    ROLE.SEGUNDO_VOLANTE.ATTACK,
    ROLE.WINGER.SUPPORT,
    ROLE.INSIDE_FORWARD.SUPPORT,
    ROLE.PRESSING_FORWARD.SUPPORT,
    ROLE.ADVANCED_FORWARD.ATTACK,
]
TARGET_PLAYER_COUNT = 2000
UID_ERROR = "player shortlist HTML must include a UID column; add it to the exported view and export again"


def main():
    process = open_fm_process()
    shortlist_df = normalise_shortlist_export(load_shortlist_table(SHORTLIST_PATH, uid_error=UID_ERROR))

    players_df = shortlist_df.merge(build_shortlist_player_table(shortlist_df, process), on="UID")
    players_df = coalesce_columns(players_df, "Name", "Name", "Memory Name")
    players_df = fill_columns_from_memory(players_df, shortlist_df.columns, process)
    if INCLUDE_CURRENT_SQUAD_PLAYERS:
        players_df, _added_uids = append_current_squad_players(players_df, process)

    players_df = score_players_for_roles(players_df, ROLES)
    players_df = filter_players_for_roles(players_df, ROLES, target_n=TARGET_PLAYER_COUNT, filter_type="roles")

    role_columns = [role.short_label for role in ROLES]
    players_df = players_df.rename(columns={role.code: role.short_label for role in ROLES})

    base_columns = [column for column in DISPLAY_COLUMN_ORDER if column in players_df.columns]
    extra_columns = [column for column in EXTRA_COLUMNS if column in players_df.columns]
    players_df = players_df[base_columns + extra_columns + role_columns]

    sort_values = {}
    if "Wage" in players_df.columns:
        sort_values["Wage"] = players_df["Wage"].apply(parse_money_text).tolist()
    if "Value" in players_df.columns:
        sort_values["Value"] = players_df["Value"].astype("Int64").tolist()
        players_df["Value"] = players_df["Value"].apply(format_currency)

    for column in ["Age", "CA", "PA"]:
        if column in players_df.columns:
            players_df[column] = pd.to_numeric(players_df[column], errors="coerce").astype("Int64")

    html = build_sortable_table_html(
        players_df,
        title="FM Player Scan",
        subtitle=f"{len(players_df):,} players scored across {len(ROLES)} selected roles.",
        roles=ROLES,
        score_columns=role_columns,
        default_sort_column="Value" if "Value" in players_df.columns else None,
        column_sort_values=sort_values,
    )
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
