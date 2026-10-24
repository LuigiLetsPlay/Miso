"""Title-based NSFW detection.

Steam sets no age ratings for this workshop, but uploaders usually say it in
the title ("18+", "NSFW", "hentai" …), so that's what we look at.
"""
from __future__ import annotations

import re

WORDS = (
    "nsfw", "nswf", "nsfm", "r18", "r-18", "r34", "rule34", "rule 34", "hentai", "xxx", "porn", "porno",
    "nude", "nudes", "nudity", "naked", "boobs", "boob", "bobs", "tits", "titty", "titties", "lewd", "ecchi",
    "sexy", "sex", "horny", "oppai", "onlyfans", "uncensored", "nipple", "nipples", "milf", "futa", "18+",
)

_word = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(w) for w in WORDS if w != "18+") + r")(?![a-z0-9])")
_age = re.compile(r"(?<!\d)(\+\s?18|18\s?\+|18\s?plus)(?!\d)")


def is_nsfw(title: str) -> bool:
    t = title.lower().replace("_", " ")
    return bool(_word.search(t) or _age.search(t))
