"""Helpers for loading shortlist exports and normalising shortlist columns."""

import lxml.html
import pandas as pd
from pandas._libs.parsers import STR_NA_VALUES

from core.uids import normalise_uid

IGNORED_SHORTLIST_COLUMNS = ["Rec", "Inf"]  # FM's recommendation and information columns


def _cell_text(cell):
    """Match how pandas.read_html reads a cell: collapse whitespace, and treat its blank spellings as missing."""
    text = " ".join(cell.text_content().split())
    return None if text in STR_NA_VALUES else text


def _read_export_table(path):
    """Parse the export ourselves.

    pandas.read_html spends most of its time inferring column types, which is wasted here: an export is
    all text, and the columns we care about get converted deliberately further down.
    """
    tree = lxml.html.parse(path, parser=lxml.html.HTMLParser(encoding="utf-8"))
    rows = [[_cell_text(cell) for cell in row.iterchildren("td", "th")] for row in tree.iter("tr")]
    if not rows:
        return pd.DataFrame()

    header, *body = rows
    frame = pd.DataFrame([row[: len(header)] + [None] * (len(header) - len(row)) for row in body], columns=header)

    # Callers expect the numeric columns pandas.read_html would have inferred, e.g. a bare .astype("Int64") on Age.
    for position in range(frame.shape[1]):
        try:
            frame.isetitem(position, pd.to_numeric(frame.iloc[:, position]))
        except (TypeError, ValueError):
            continue

    return frame


def load_shortlist_table(path, *, uid_error):
    shortlist_df = _read_export_table(path).dropna(how="all")
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
