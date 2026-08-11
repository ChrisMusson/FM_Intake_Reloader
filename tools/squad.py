"""Example script for printing Name, CA, and PA from selected squad buckets."""

from core.memory.squad import SQUAD_TYPES, load_squad_table


def main():
    squad_ids = SQUAD_TYPES
    players = load_squad_table(target_teams=squad_ids).reset_index(drop=True)
    print(players.head(20))


if __name__ == "__main__":
    main()
