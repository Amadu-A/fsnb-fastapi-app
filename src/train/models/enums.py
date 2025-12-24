# path: src/train/models/enums.py
from __future__ import annotations

from enum import Enum


class FeedbackLabel(str, Enum):
    """
    Метка пользователя по строке спецификации.

    Значения:
    - gold:        пользователь выбрал корректный items.id (истина/эталон)
    - negative:    пользователь указывает, что предложенный(е) кандидаты неверны (штраф/негативы)
    - skip:        пользователь пропустил (не участвует в обучении)
    - ambiguous:   неоднозначно (не участвует в обучении; можно анализировать отдельно)
    - none_match:  ни один из кандидатов не подходит (важно, но чаще не учим как gold)
    """

    GOLD = "gold"
    NEGATIVE = "negative"
    SKIP = "skip"
    AMBIGUOUS = "ambiguous"
    NONE_MATCH = "none_match"
