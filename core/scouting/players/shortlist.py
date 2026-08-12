"""Helpers for preparing player shortlist exports and combining them with memory data."""

import pandas as pd

from core.memory.players import EMPTY_PLAYER_PROFILE, build_shortlist_player_profile_table
from core.memory.squad import SQUAD_TYPES, build_current_squad_player_table
from core.scouting.shortlists import coalesce_columns

# Columns the report always shows, filling them from memory when the exported view left them out.
# Any other column shows only when the export carried it.
REQUIRED_COLUMNS = ("Name", "Age", "Club", "Position")

# Memory is the authority for these, so an exported view must never shadow them during a merge.
MEMORY_OWNED_COLUMNS = ("CA", "PA", "Value")

# The export is the only authority for these: a blank cell stays blank rather than being filled from memory.
# Our own squad players are the exception - see append_current_squad_players.
EXPORT_ONLY_COLUMNS = ("Wage",)

# FM writes a dash rather than an empty cell when it has no value to show, e.g. 306 of this export's wages.
PLACEHOLDER_VALUE_PATTERN = r"[-\s]*"
NAME_NOISE_SUFFIX = " - Pick Player"

# Some views append a qualifier: "Hatem Saleh - Saudi", "Al-Ittihad - Saudi Professional League".
# Real names and clubs contain the same separator ("Lyon - La Duchère"), so only strip it when the
# whole column looks that way rather than row by row.
COMBINED_VALUE_SEPARATOR = " - "
COMBINED_COLUMN_RATIO = 0.5


def _placeholders_to_na(series):
    if series.dtype != object and series.dtype != "string":
        return series

    stripped = series.astype("string").str.strip()
    return stripped.mask(stripped.str.fullmatch(PLACEHOLDER_VALUE_PATTERN).fillna(False))


def _strip_combined_qualifier(series):
    values = series.dropna().astype("string")
    if values.empty or values.str.contains(COMBINED_VALUE_SEPARATOR, regex=False).mean() < COMBINED_COLUMN_RATIO:
        return series

    return series.astype("string").str.split(COMBINED_VALUE_SEPARATOR).str[0].str.strip()


def normalise_shortlist_export(shortlist_df):
    """Extract everything the exported file can give, whatever set of columns the view happened to include."""
    shortlist_df = shortlist_df.drop(columns=list(MEMORY_OWNED_COLUMNS), errors="ignore")

    for column in shortlist_df.columns:
        shortlist_df[column] = _placeholders_to_na(shortlist_df[column])

    if "Name" not in shortlist_df.columns and "Player" in shortlist_df.columns:
        shortlist_df = shortlist_df.rename(columns={"Player": "Name"})
    if "Name" in shortlist_df.columns:
        shortlist_df["Name"] = shortlist_df["Name"].astype("string").str.replace(NAME_NOISE_SUFFIX, "", regex=False)
        shortlist_df["Name"] = _strip_combined_qualifier(shortlist_df["Name"])
    if "Club" in shortlist_df.columns:
        shortlist_df["Club"] = _strip_combined_qualifier(shortlist_df["Club"])
    if "Age" in shortlist_df.columns:
        shortlist_df["Age"] = pd.to_numeric(shortlist_df["Age"], errors="coerce").astype("Int64")

    return shortlist_df


def fill_columns_from_memory(players_df, exported_columns, process):
    """Fill only the cells the export could not supply, so the exported file stays the primary source."""
    candidates = dict.fromkeys([*REQUIRED_COLUMNS, *exported_columns])
    fillable_columns = [column for column in candidates if column in EMPTY_PLAYER_PROFILE and column not in EXPORT_ONLY_COLUMNS]
    if not fillable_columns:
        return players_df

    missing_mask = players_df.reindex(columns=fillable_columns).isna().any(axis=1)
    missing_uids = players_df.loc[missing_mask, "UID"].dropna().astype(int).unique().tolist()
    if not missing_uids:
        return players_df

    profile_df = build_shortlist_player_profile_table(missing_uids, process).drop_duplicates(subset=["UID"], keep="first").set_index("UID")
    players_df = players_df.copy()

    for column in fillable_columns:
        memory_values = players_df["UID"].map(profile_df[column])
        if column in players_df.columns:
            players_df[column] = players_df[column].where(players_df[column].notna(), memory_values)
        else:
            players_df[column] = memory_values

    return players_df


def append_current_squad_players(players_df, process, target_teams=SQUAD_TYPES):
    current_squad_df = build_current_squad_player_table(target_teams=target_teams, process=process)
    all_columns = list(dict.fromkeys([*players_df.columns, *current_squad_df.columns]))
    existing_by_uid = players_df.reindex(columns=all_columns).drop_duplicates(subset=["UID"], keep="first").set_index("UID")
    current_squad_by_uid = current_squad_df.reindex(columns=all_columns).drop_duplicates(subset=["UID"], keep="first").set_index("UID")
    existing_uids = set(existing_by_uid.index.dropna().astype(int))
    added_uids = sorted(set(current_squad_by_uid.index.dropna().astype(int)) - existing_uids)
    combined_by_uid = existing_by_uid.combine_first(current_squad_by_uid)  # keep exported values, fill the gaps from memory

    # Memory outranks the export for our own players: their wages are live in the save, whereas an
    # exported view shows whatever the scouting screen last knew, which for our own squad is often blank.
    for column in EXPORT_ONLY_COLUMNS:
        if column in current_squad_by_uid.columns:
            squad_values = current_squad_by_uid[column].reindex(combined_by_uid.index)
            combined_by_uid[column] = squad_values.where(squad_values.notna(), combined_by_uid.get(column))

    uid_order = list(existing_by_uid.index) + [uid for uid in current_squad_by_uid.index if uid not in existing_by_uid.index]
    combined_df = combined_by_uid.loc[uid_order].reset_index()

    return coalesce_columns(combined_df, "Name", "Name", "Player", "Memory Name"), added_uids
