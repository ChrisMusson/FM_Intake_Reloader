"""Read squad and squad-player data directly from Football Manager's process memory."""

import pandas as pd

from core.memory.person import PERSON_UID_OFFSET, read_person_name
from core.memory.players import PERSON_OBJECT_OFFSET, PLAYER_OBJECT_VTABLE, read_player_profile, read_player_snapshot
from core.memory.process import get_fm_base_address, open_fm_process, read_uint
from core.memory.session import get_current_club_address

SQUAD_TYPE_NAMES = {
    0: "First Team",
    1: "Reserves",
    2: "A",
    3: "B",
    4: "Superdraft A",
    5: "Superdraft B",
    6: "Superdraft C",
    7: "Superdraft D",
    8: "Waivers",
    9: "U23",
    10: "U21",
    11: "U19",
    12: "U18",
    13: "C",
    14: "Amateur",
    15: "II",
    16: "Team 2",
    17: "Team 3",
    18: "U20",
    22: "Youth Evaluation",
    30: "Dutch Reserves",
    44: "Second Team",
}
SQUAD_TYPES = tuple(SQUAD_TYPE_NAMES)

CURRENT_CLUB_TEAM_LIST_START_OFFSET = 0x18
CURRENT_CLUB_TEAM_LIST_END_OFFSET = 0x20
TEAM_BUCKET_ID_OFFSET = 0x28
TEAM_PLAYER_LIST_START_OFFSET = 0x38
TEAM_PLAYER_LIST_END_OFFSET = 0x40


def iter_squad_player_addresses(target_teams=(22,), process=None):
    process = process or open_fm_process()
    target_teams = {target_teams} if isinstance(target_teams, int) else set(target_teams)

    club_address = get_current_club_address(process)
    team_list_start = read_uint(process, club_address + CURRENT_CLUB_TEAM_LIST_START_OFFSET)
    team_list_end = read_uint(process, club_address + CURRENT_CLUB_TEAM_LIST_END_OFFSET)
    if not team_list_start or team_list_end < team_list_start:
        return

    for team_slot in range(team_list_start, team_list_end, 8):
        team_address = read_uint(process, team_slot)
        if not team_address or read_uint(process, team_address + TEAM_BUCKET_ID_OFFSET, 1) not in target_teams:
            continue

        player_list_start = read_uint(process, team_address + TEAM_PLAYER_LIST_START_OFFSET)
        player_list_end = read_uint(process, team_address + TEAM_PLAYER_LIST_END_OFFSET)
        if not player_list_start or player_list_end < player_list_start:
            continue

        for player_slot in range(player_list_start, player_list_end, 8):
            player_address = read_uint(process, player_slot)
            if player_address and read_uint(process, player_address) == PLAYER_OBJECT_VTABLE:
                yield player_address


def load_squad_table(target_teams=(22,), process=None):
    process = process or open_fm_process()
    rows = []

    for player_address in iter_squad_player_addresses(target_teams=target_teams, process=process):
        rows.append(
            [
                read_person_name(process, player_address + PERSON_OBJECT_OFFSET),
                read_uint(process, player_address + 0x200, 2),
                read_uint(process, player_address + 0x202, 2),
            ]
        )

    if not rows:
        return pd.DataFrame(columns=["Name", "CA", "PA"])

    df = pd.DataFrame(rows, columns=["Name", "CA", "PA"])
    return df.sort_values(by=["PA", "CA"], ascending=[False, False]).reset_index(drop=True)


def build_current_squad_player_table(target_teams=SQUAD_TYPES, process=None):
    process = process or open_fm_process()
    fm_base_address = get_fm_base_address(process)
    rows = []

    for player_address in iter_squad_player_addresses(target_teams=target_teams, process=process):
        person_address = player_address + PERSON_OBJECT_OFFSET
        uid = read_uint(process, person_address + PERSON_UID_OFFSET, 4)
        if uid <= 0:
            continue
        rows.append({"UID": uid, **read_player_snapshot(process, person_address), **read_player_profile(process, person_address, fm_base_address)})

    if not rows:
        return pd.DataFrame(columns=["UID"]).astype({"UID": "Int64"})

    players_df = pd.DataFrame(rows).astype({"UID": "Int64"})
    players_df = players_df.loc[players_df["Memory Name"].notna()]
    return players_df.drop_duplicates(subset=["UID"], keep="first").reset_index(drop=True)
