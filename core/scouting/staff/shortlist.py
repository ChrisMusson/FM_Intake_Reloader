"""Helpers for building normalised staff scouting tables from shortlist exports."""

from core.memory.staff import build_current_club_staff_table, build_staff_shortlist_table
from core.scouting.shortlists import approved_shortlist_columns, coalesce_columns, load_shortlist_table

DEFAULT_STAFF_SHORTLIST_PATH = "staff_shortlist.html"
APPROVED_STAFF_SHORTLIST_COLUMNS = {
    "Name": ("Name", "Staff"),
    "Nationality": ("Nationality", "Nat"),
    "Age": ("Age",),
    "Club": ("Club",),
    "Wage": ("Wage",),
    "Qualification": ("Qualification", "Current Licence", "Current License", "Coaching Licence", "Coaching License"),
}
DEFAULT_STAFF_UID_ERROR = "coach shortlist HTML must include a UID column"


def build_staff_shortlist_dataframe(shortlist_df, process):
    staff_df = shortlist_df.merge(build_staff_shortlist_table(shortlist_df, process), on="UID")
    shortlist_columns = approved_shortlist_columns(shortlist_df, APPROVED_STAFF_SHORTLIST_COLUMNS)
    staff_df = coalesce_columns(staff_df, "Name", *(column for column in [shortlist_columns["Name"], "Memory Name"] if column))
    staff_df = coalesce_columns(staff_df, "Nationality", *(column for column in [shortlist_columns["Nationality"], "Nationality"] if column))
    staff_df = coalesce_columns(staff_df, "Age", *(column for column in [shortlist_columns["Age"], "Age_x", "Age_y", "Age"] if column))
    staff_df = coalesce_columns(staff_df, "Club", *(column for column in [shortlist_columns["Club"], "Club_x", "Club_y", "Club"] if column))
    staff_df = coalesce_columns(staff_df, "Wage", *(column for column in [shortlist_columns["Wage"], "Wage_x", "Wage_y", "Wage"] if column))
    staff_df = coalesce_columns(staff_df, "Qualification", *(column for column in [shortlist_columns["Qualification"], "Qualification"] if column))

    return staff_df


def load_staff_shortlist_dataframe(shortlist_path, process, uid_error=DEFAULT_STAFF_UID_ERROR):
    shortlist_df = load_shortlist_table(shortlist_path, uid_error=uid_error)
    return build_staff_shortlist_dataframe(shortlist_df, process)


def append_current_club_staff(staff_df, process):
    current_club_staff_df = build_current_club_staff_table(process)
    if current_club_staff_df.empty:
        return staff_df.reset_index(drop=True), []

    current_club_staff_df = current_club_staff_df.copy()
    current_club_staff_df["Name"] = current_club_staff_df["Memory Name"]
    all_columns = list(dict.fromkeys([*staff_df.columns, *current_club_staff_df.columns]))
    existing_by_uid = staff_df.reindex(columns=all_columns).drop_duplicates(subset=["UID"], keep="first").set_index("UID")
    current_club_by_uid = current_club_staff_df.reindex(columns=all_columns).drop_duplicates(subset=["UID"], keep="first").set_index("UID")
    existing_uids = set(existing_by_uid.index.dropna().astype(int))
    added_uids = sorted(set(current_club_by_uid.index.dropna().astype(int)) - existing_uids)
    combined_by_uid = current_club_by_uid.combine_first(existing_by_uid)
    uid_order = list(existing_by_uid.index) + [uid for uid in current_club_by_uid.index if uid not in existing_by_uid.index]
    combined_df = combined_by_uid.loc[uid_order].reset_index()

    return combined_df, added_uids
