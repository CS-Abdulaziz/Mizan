"""Grade classification keyword lists (SPEC §8.1, AMENDMENT 5). NEEDS SH SIGN-OFF (pending, DECISIONS D-20).

The sharia reviewer may edit these lists directly. Phrases are matched as whole words on normalized
Arabic (diacritics removed, hamza forms folded, ة -> ه), so «صحيحه» does NOT match «صحيح».
Rules are applied in the order of SPEC §8.1; the first rule that applies wins.
"""

from __future__ import annotations

# Rule 1: the source book is one of the two Sahihs -> accepted (matched as a phrase inside the book name)
SAHIHAYN_BOOKS: list[str] = ["صحيح البخاري", "صحيح مسلم"]

# Rule 3: negations / very weak -> very_weak
VERY_WEAK: list[str] = [
    "موضوع", "باطل", "كذب", "لا أصل له", "منكر", "ضعيف جدا", "ضعيف جداً", "لا يصح", "لم يصح",
    "ليس بصحيح", "لا يثبت", "لم يثبت", "واه", "مكذوب",
]

# Rule 4: chain-level acceptance -> accepted_isnad
ACCEPTED_ISNAD: list[str] = ["إسناده صحيح", "إسناده حسن", "إسناده جيد"]
# ... except these, which stay unclassified (a statement about narrators, not a grading)
ISNAD_UNCLASSIFIED: list[str] = ["رجاله ثقات"]

# Rule 5: weak -> weak
WEAK: list[str] = ["ضعيف", "إسناده ضعيف", "فيه ضعف", "فيه انقطاع", "مرسل"]

# Rule 6: accepted -> accepted
ACCEPTED: list[str] = ["صحيح", "حسن", "صحيح لغيره", "حسن لغيره", "متفق عليه", "حسن صحيح"]
