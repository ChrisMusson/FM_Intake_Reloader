"""Apply role scoring rules to FM players."""

import pandas as pd

from core.scouting.players.role_definitions import ROLE_DEFINITIONS
from core.scouting.players.roles import parse_role

KEY_WEIGHT = 5
GREEN_WEIGHT = 3
BLUE_WEIGHT = 1


def _weighted_attribute_total(players_df, attributes, weight):
    if not attributes:
        return pd.Series(0, index=players_df.index, dtype=float)
    return players_df[[attribute.value for attribute in attributes]].sum(axis=1) * weight


def score_players_for_roles(players_df, roles, role_definitions=None):
    role_definitions = role_definitions or ROLE_DEFINITIONS
    roles = [parse_role(role) for role in roles]
    players_df = players_df.copy()

    for role in roles:
        definition = role_definitions[role]
        divisor = len(definition.key) * KEY_WEIGHT + len(definition.green) * GREEN_WEIGHT + len(definition.blue) * BLUE_WEIGHT
        players_df[role.code] = (
            _weighted_attribute_total(players_df, definition.key, KEY_WEIGHT)
            + _weighted_attribute_total(players_df, definition.green, GREEN_WEIGHT)
            + _weighted_attribute_total(players_df, definition.blue, BLUE_WEIGHT)
        ) / divisor
        players_df[role.code] = players_df[role.code].round(1)

    return players_df.dropna(subset=[role.code for role in roles])


def filter_players_for_roles(players_df, roles, target_n=5000, filter_type="roles"):
    roles = [parse_role(role) for role in roles]
    if len(players_df) <= target_n:
        return players_df

    if filter_type == "roles":
        shortlist_uids = []
        top_pct = target_n * 100 / len(players_df) / len(roles)
        for role in roles:
            shortlist_uids += players_df.sort_values(role.code, ascending=False).head(int(players_df.shape[0] * top_pct / 100))["UID"].to_list()
        return players_df[players_df["UID"].isin(shortlist_uids)]

    if filter_type == "potential":
        return players_df.sort_values("PA", ascending=False).head(target_n)

    raise ValueError(f"Unknown role filter type: {filter_type!r}")
