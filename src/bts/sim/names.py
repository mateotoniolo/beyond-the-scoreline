"""Invented names for clubs, venues and players. Nothing here refers to a real entity."""

import random

CLUBS: list[tuple[str, str, tuple[str, str], str]] = [
    ("Northbridge Athletic", "NTH", ("#1d4ed8", "#f8fafc"), "Ironworks Park"),
    ("Saltmarsh Rovers", "SMR", ("#b91c1c", "#fde68a"), "The Tidal Ground"),
    ("Kestrel Park FC", "KPF", ("#047857", "#ecfdf5"), "Kestrel Park"),
    ("Elderwick Wanderers", "ELD", ("#7c3aed", "#fef3c7"), "Elderwick Meadow"),
]

_FIRST_ONSETS = [
    "Ar",
    "Be",
    "Cal",
    "Dar",
    "El",
    "Fen",
    "Gal",
    "Hal",
    "Id",
    "Jor",
    "Kel",
    "Lor",
    "Mar",
    "Nik",
    "Or",
    "Per",
    "Quin",
    "Ren",
    "Sol",
    "Tar",
    "Ul",
    "Var",
    "Wil",
    "Yan",
]
_FIRST_CODAS = ["an", "en", "in", "on", "us", "o", "io", "ian", "el", "ar", "is", "ek"]
_LAST_ONSETS = [
    "Ash",
    "Bar",
    "Cor",
    "Dun",
    "Esk",
    "Fair",
    "Gran",
    "Hol",
    "Ing",
    "Kirk",
    "Lang",
    "Mor",
    "Nor",
    "Ox",
    "Pen",
    "Rad",
    "Stan",
    "Thorn",
    "Und",
    "Vane",
    "Wes",
    "Yor",
]
_LAST_CODAS = ["ley", "wick", "ford", "ton", "by", "dale", "field", "more", "worth", "shaw", "well"]


def make_name(rng: random.Random) -> str:
    """Return a two-word invented name built from syllable tables."""
    first = rng.choice(_FIRST_ONSETS) + rng.choice(_FIRST_CODAS)
    last = rng.choice(_LAST_ONSETS) + rng.choice(_LAST_CODAS)
    return f"{first} {last}"
