"""Build an HTML scouting report for a staff shortlist export."""

import pandas as pd

from core.memory.process import open_fm_process
from core.scouting.html import build_sortable_table_html
from core.scouting.money import format_currency, parse_money_text
from core.scouting.staff.roles import COACHING_AREA_COLUMNS, StaffArea
from core.scouting.staff.shortlist import DEFAULT_STAFF_SHORTLIST_PATH, append_current_club_staff, load_staff_shortlist_dataframe

SHORTLIST_PATH = DEFAULT_STAFF_SHORTLIST_PATH
OUTPUT_PATH = "staff_table.html"
INCLUDE_CURRENT_CLUB_STAFF = True  # add the current manager's club staff from memory even if they are not in the shortlist export
MIN_ANY_CATEGORY_STARS = 4  # set to e.g. 4 or 4.5 to keep only coaches with at least one category at this star rating


def main():
    process = open_fm_process()
    staff_df = load_staff_shortlist_dataframe(SHORTLIST_PATH, process)
    if INCLUDE_CURRENT_CLUB_STAFF:
        staff_df, _added_uids = append_current_club_staff(staff_df, process)

    if MIN_ANY_CATEGORY_STARS:
        qualifying_mask = staff_df[COACHING_AREA_COLUMNS].fillna(0).ge(MIN_ANY_CATEGORY_STARS).any(axis=1)
        staff_df = staff_df.loc[qualifying_mask].reset_index(drop=True)

    score_columns = COACHING_AREA_COLUMNS
    wage_sort_values = staff_df["Wage"].apply(parse_money_text).tolist() if "Wage" in staff_df.columns else None
    if "Wage" in staff_df.columns and pd.api.types.is_numeric_dtype(staff_df["Wage"]):
        staff_df["Wage"] = staff_df["Wage"].apply(format_currency)

    column_sort_values = {"Best Stars": staff_df["Best Stars Raw"].tolist(), **{role: staff_df[f"{role} Raw"].tolist() for role in score_columns}}
    if wage_sort_values is not None:
        column_sort_values["Wage"] = wage_sort_values

    display_columns = [
        column
        for column in [
            "Nationality",
            "Club",
            "Wage",
            "Age",
            "Name",
            "Qualification",
            "Studying",
            "CA",
            "PA",
            "Full Qual CA",
            "Best Role",
            "Best Stars",
            *COACHING_AREA_COLUMNS,
        ]
        if column in staff_df.columns
    ]
    staff_df = staff_df[display_columns]

    for column in ["Age", "CA", "PA", "Full Qual CA"]:
        if column in staff_df.columns:
            staff_df[column] = staff_df[column].astype("Int64")

    html = build_sortable_table_html(
        staff_df,
        title="FM Staff Scan",
        subtitle=f"{len(staff_df):,} shortlisted staff scored across {len(score_columns)} coaching areas.",
        roles=[StaffArea(column) for column in score_columns],
        score_columns=score_columns,
        default_sort_column="Best Stars",
        column_sort_values=column_sort_values,
        score_style_min=0,
        score_style_max=300,
        score_colour_min=0,
        score_colour_max=300,
    )
    with open(OUTPUT_PATH, "w", encoding="utf-8") as output_file:
        output_file.write(html)


if __name__ == "__main__":
    main()
