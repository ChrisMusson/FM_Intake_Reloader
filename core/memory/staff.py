"""Helpers for reading staff/coaching data from Football Manager memory."""

from math import floor

import pandas as pd

from core.memory.cache import get_cached_or_compute
from core.memory.person import PERSON_UID_OFFSET, read_person_age, read_person_name
from core.memory.process import get_fm_base_address, iter_pattern_matches, read_chained_string, read_chained_value, read_uint
from core.memory.session import find_manager_address, get_current_club_address
from core.scouting.staff.roles import (
    COACHING_AREA_COLUMNS,
    STAFF_AREA_WEIGHTS,
    STAFF_ATTRIBUTE_OFFSETS,
    Qualification,
    StaffMetric,
    decode_qualification,
)

STAFF_OBJECT_SCAN_PATTERN = b"\xe8\xc2\xa4\x45\x01"
STAFF_PERSON_OBJECT_OFFSET = 0xF8
HUMAN_MANAGER_PERSON_OBJECT_OFFSET = 0x450
CURRENT_CLUB_STAFF_LIST_START_OFFSET = 0x78
CURRENT_CLUB_STAFF_LIST_END_OFFSET = 0x80
STAFF_CA_OFFSET = 0xD6
STAFF_PA_OFFSET = 0xD8
EMPTY_STAFF_SNAPSHOT = {
    "Memory Name": None,
    "Nationality": None,
    "Age": None,
    "Club": None,
    "Wage": None,
    "CA": None,
    "PA": None,
    "Qualification": None,
    "Studying": None,
    "Full Qual CA": None,
    **{column: None for column in COACHING_AREA_COLUMNS},
    **{f"{column} Raw": None for column in COACHING_AREA_COLUMNS},
    "Best Role": None,
    "Best Stars": None,
    "Best Stars Raw": None,
}


_STAFF_PROCESS_CACHE = {}


def _get_staff_process_cache(process):
    process_key = getattr(process, "pid", None) or getattr(process, "process_id", None) or id(process)
    cache = _STAFF_PROCESS_CACHE.get(process_key)
    if cache is None:
        cache = {}
        _STAFF_PROCESS_CACHE[process_key] = cache
    return cache


def get_staff_fm_base_address(process):
    cache = _get_staff_process_cache(process)
    if "fm_base_address" not in cache:
        cache["fm_base_address"] = get_fm_base_address(process)
    return cache["fm_base_address"]


def scan_staff_person_addresses(process, *, refresh=False):
    cache = _get_staff_process_cache(process)
    if not refresh and "person_addresses" in cache:
        return cache["person_addresses"]

    def build_person_addresses():
        people = {}

        for object_address in iter_pattern_matches(process, STAFF_OBJECT_SCAN_PATTERN, writable=True, executable=False, private=True):
            person_address = object_address + 0xF8
            try:
                uid = read_uint(process, person_address + PERSON_UID_OFFSET, 4)
            except Exception:
                continue
            if uid > 0 and uid not in people:
                people[uid] = person_address

        return people

    person_addresses, _cache_hit = get_cached_or_compute(
        process, "staff_person_addresses", key_parts={}, builder=build_person_addresses, refresh=refresh
    )
    cache["person_addresses"] = person_addresses
    return person_addresses


def read_staff_snapshot(process, person_address, fm_base_address, *, person_object_offset=STAFF_PERSON_OBJECT_OFFSET):
    if person_address is None:
        return EMPTY_STAFF_SNAPSHOT.copy()

    staff_address = person_address - person_object_offset
    raw_attributes = {metric: read_uint(process, staff_address + offset, 1) for metric, offset in STAFF_ATTRIBUTE_OFFSETS.items()}
    scaled_attributes = {metric: raw if metric == StaffMetric.DISCIPLINE else int(round(raw / 5)) for metric, raw in raw_attributes.items()}
    scaled_attributes[StaffMetric.DDM] = (
        scaled_attributes[StaffMetric.DETERMINATION] + scaled_attributes[StaffMetric.DISCIPLINE] + scaled_attributes[StaffMetric.MOTIVATING]
    )
    coaching_scores = {
        area.value: sum(weight * scaled_attributes[metric] for weight, metric in weights.items()) for area, weights in STAFF_AREA_WEIGHTS.items()
    }
    star_ratings = {role: floor((score + 30) / 30) / 2 for role, score in coaching_scores.items()}
    qualification, studying = decode_qualification(read_uint(process, person_address + 0x16A, 1))

    ca = read_uint(process, staff_address + STAFF_CA_OFFSET, 2)
    pa = read_uint(process, staff_address + STAFF_PA_OFFSET, 2)
    qualification_level = qualification.value if isinstance(qualification, Qualification) else 0
    full_qual_ca = min(ca + 13 * max(qualification_level - 1, 0), pa)
    best_role = max(coaching_scores, key=coaching_scores.get)

    return {
        "Memory Name": read_person_name(process, person_address),
        "Nationality": read_chained_string(process, person_address, [0x70, 0x30], 0x4, size=255),
        "Age": read_person_age(process, person_address, fm_base_address),
        "Club": read_chained_string(process, person_address, [0xC8, 0x10, 0x30, 0xC8], 0x4, size=64),
        "Wage": read_chained_value(process, person_address, [0xC8], 0x18, size=4),
        "CA": ca,
        "PA": pa,
        "Qualification": qualification.label if qualification else None,
        "Studying": "Yes" if studying else "",
        "Full Qual CA": full_qual_ca,
        **star_ratings,
        **{f"{role} Raw": score for role, score in coaching_scores.items()},
        "Best Role": best_role,
        "Best Stars": star_ratings[best_role],
        "Best Stars Raw": coaching_scores[best_role],
    }


def _build_staff_rows(uids, process):
    ordered_uids = [None if pd.isna(uid) else int(uid) for uid in pd.Series(list(uids), dtype="Int64").drop_duplicates()]

    def build_rows():
        fm_base_address = get_staff_fm_base_address(process)
        person_addresses = scan_staff_person_addresses(process)
        rows = []

        for uid_int in ordered_uids:
            snapshot = read_staff_snapshot(process, person_addresses.get(uid_int), fm_base_address)
            rows.append({"UID": uid_int, **snapshot})

        return rows

    rows, _cache_hit = get_cached_or_compute(process, "staff_rows_by_uid", key_parts={"uids": ordered_uids}, builder=build_rows)
    return rows


def build_staff_shortlist_table(shortlist_df, process):
    rows = _build_staff_rows(shortlist_df["UID"], process)
    return pd.DataFrame(rows).astype({"UID": "Int64"})


def build_staff_table_for_uids(uids, process):
    rows = _build_staff_rows(uids, process)
    return pd.DataFrame(rows).astype({"UID": "Int64"}) if rows else pd.DataFrame(columns=["UID"]).astype({"UID": "Int64"})


def build_staff_table_for_staff_addresses(staff_addresses, process):
    ordered_staff_addresses = [
        int(staff_address) for staff_address in pd.Series(list(staff_addresses), dtype="Int64").drop_duplicates() if not pd.isna(staff_address)
    ]

    def build_rows():
        fm_base_address = get_staff_fm_base_address(process)
        rows = []

        for staff_address in ordered_staff_addresses:
            person_address = staff_address + STAFF_PERSON_OBJECT_OFFSET
            rows.append(
                {"UID": read_uint(process, person_address + PERSON_UID_OFFSET, 4), **read_staff_snapshot(process, person_address, fm_base_address)}
            )

        return rows

    rows, _cache_hit = get_cached_or_compute(
        process, "staff_rows_by_staff_address", key_parts={"staff_addresses": ordered_staff_addresses}, builder=build_rows
    )

    return pd.DataFrame(rows).astype({"UID": "Int64"}) if rows else pd.DataFrame(columns=["UID"]).astype({"UID": "Int64"})


def build_current_club_staff_table(process):
    club_address = get_current_club_address(process)
    list_start = read_uint(process, club_address + CURRENT_CLUB_STAFF_LIST_START_OFFSET)
    list_end = read_uint(process, club_address + CURRENT_CLUB_STAFF_LIST_END_OFFSET)

    if not list_start or list_end < list_start:
        return pd.DataFrame(columns=["UID"]).astype({"UID": "Int64"})

    staff_addresses = [read_uint(process, slot) for slot in range(list_start, list_end, 8)]
    staff_df = build_staff_table_for_staff_addresses(staff_addresses, process)
    return staff_df.loc[staff_df["Memory Name"].notna()].reset_index(drop=True)


def read_current_manager_staff_row(process):
    manager_address = find_manager_address(process)
    fm_base_address = get_staff_fm_base_address(process)
    uid = read_uint(process, manager_address + PERSON_UID_OFFSET, 4)
    snapshot = read_staff_snapshot(process, manager_address, fm_base_address)

    if snapshot["Best Stars Raw"] == 0:
        human_manager_snapshot = read_staff_snapshot(
            process, manager_address, fm_base_address, person_object_offset=HUMAN_MANAGER_PERSON_OBJECT_OFFSET
        )
        if human_manager_snapshot["Best Stars Raw"] > snapshot["Best Stars Raw"]:
            snapshot = human_manager_snapshot

    return {"UID": uid, **snapshot}
