"""Helpers for working with Football Manager UID values."""


def normalise_uid(uid):
    text = str(uid).strip()
    if text[:2].lower() == "r-":
        text = text[2:]
    # FM sprinkles blank spacer rows through an export, which makes pandas read the whole
    # UID column as floats, so a UID can arrive as "2002722150.0" rather than "2002722150".
    return int(float(text)) if "." in text else int(text)
