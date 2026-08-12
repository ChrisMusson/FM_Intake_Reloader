"""Helpers for loading shortlist exports and normalising shortlist columns."""

import pandas as pd

from core.uids import normalise_uid

IGNORED_SHORTLIST_COLUMNS = ["Rec", "Inf"]  # FM's recommendation and information columns


def load_shortlist_table(path, *, uid_error):
    shortlist_df = pd.read_html(path, encoding="utf-8")[0].dropna(how="all")
    shortlist_df = shortlist_df.drop(columns=IGNORED_SHORTLIST_COLUMNS, errors="ignore")
    if "UID" not in shortlist_df.columns:
        raise ValueError(uid_error)

    shortlist_df["UID"] = shortlist_df["UID"].map(normalise_uid).astype("Int64")
    return shortlist_df


def coalesce_columns(dataframe, target, *candidates):
    present = [candidate for candidate in candidates if candidate in dataframe.columns]
    if not present:
        return dataframe

    dataframe[target] = dataframe[present].bfill(axis=1).iloc[:, 0]
    columns_to_drop = [candidate for candidate in present if candidate != target]
    if columns_to_drop:
        dataframe = dataframe.drop(columns=columns_to_drop)
    return dataframe


def approved_shortlist_columns(dataframe, approved):
    return {target: next((candidate for candidate in candidates if candidate in dataframe.columns), None) for target, candidates in approved.items()}
