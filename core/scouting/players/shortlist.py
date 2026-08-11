"""Helpers for combining player shortlist exports with current squad data."""

from core.memory.squad import SQUAD_TYPES, build_current_squad_player_table


def append_current_squad_players(players_df, process, target_teams=SQUAD_TYPES):
    current_squad_df = build_current_squad_player_table(target_teams=target_teams, process=process)
    all_columns = list(dict.fromkeys([*players_df.columns, *current_squad_df.columns]))
    existing_by_uid = players_df.reindex(columns=all_columns).drop_duplicates(subset=["UID"], keep="first").set_index("UID")
    current_squad_by_uid = current_squad_df.reindex(columns=all_columns).drop_duplicates(subset=["UID"], keep="first").set_index("UID")
    existing_uids = set(existing_by_uid.index.dropna().astype(int))
    added_uids = sorted(set(current_squad_by_uid.index.dropna().astype(int)) - existing_uids)
    combined_by_uid = existing_by_uid.combine_first(current_squad_by_uid)  # keep exported values, fill the gaps from memory
    uid_order = list(existing_by_uid.index) + [uid for uid in current_squad_by_uid.index if uid not in existing_by_uid.index]
    combined_df = combined_by_uid.loc[uid_order].reset_index()

    name_columns = [column for column in ["Name", "Player", "Memory Name"] if column in combined_df.columns]
    if name_columns:
        combined_df["Name"] = combined_df[name_columns].bfill(axis=1).iloc[:, 0]

    return combined_df, added_uids
