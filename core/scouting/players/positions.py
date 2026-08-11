"""Turn raw Football Manager position ratings into the strings the game exports."""

POSITION_GROUPS = ("GK", "SW", "D", "WB", "DM", "M", "AM", "ST")
CENTRAL_ONLY_GROUPS = ("GK", "SW", "DM")
SIDE_ORDER = "RLC"
PLAYABLE_RATING = 18  # ratings at or above this show up in the exported Position column
MAX_GROUP_MERGE_DISTANCE = 2  # FM writes "WB/M/AM (L)" but never merges across a bigger gap


def format_player_positions(ratings, playable_rating=PLAYABLE_RATING):
    """Build a Position string such as "D/WB (R)" or "M (C), AM (RC)" from {position: rating}."""
    playable = {position for position, rating in ratings.items() if rating is not None and rating >= playable_rating}
    sides_by_group = {}

    for group in POSITION_GROUPS:
        if group in CENTRAL_ONLY_GROUPS:
            if group in playable:
                sides_by_group[group] = ""
        elif group == "ST":
            if group in playable:
                sides_by_group[group] = "C"
        else:
            sides = "".join(side for side in SIDE_ORDER if f"{group} {side}" in playable)
            if sides:
                sides_by_group[group] = sides

    groups = [group for group in POSITION_GROUPS if group in sides_by_group]
    parts = []
    start = 0

    while start < len(groups):
        end = start
        while (
            end + 1 < len(groups)
            and sides_by_group[groups[end + 1]] == sides_by_group[groups[start]]
            and POSITION_GROUPS.index(groups[end + 1]) - POSITION_GROUPS.index(groups[end]) <= MAX_GROUP_MERGE_DISTANCE
        ):
            end += 1

        sides = sides_by_group[groups[start]]
        label = "/".join(groups[start : end + 1])
        parts.append(f"{label} ({sides})" if sides else label)
        start = end + 1

    return ", ".join(parts)
