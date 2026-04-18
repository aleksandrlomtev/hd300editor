"""
routing.py — логика свободной маршрутизации FX-блоков.

Три публичных функции соответствуют трём сценариям из pain.md:
  flip_prepost   — Сценарий 1 (только смена PRE/POST)
  swap_blocks    — Сценарий 2/4 (чистый свап содержимого, флаги не трогаем)
  combo_swap     — Сценарий 3 (свап + новые pre/post для обоих)

Никаких зависимостей от Qt или mido. Только мутация BlockState-объектов.
Вызывающий код сам отвечает за отправку MIDI команд после.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from block_model import BlockState


# ── Swappable полей BlockState ────────────────────────────────────
# Всё кроме block_id и slot_id — они привязаны к физическому слоту.
# pre_post тоже НЕ входит в список — его трогаем отдельно через параметры.
_SWAP_FIELDS = (
    "model_id",
    "name",
    "category",
    "is_on",
    "params",
    "extra",
)


def _swap_content(a: "BlockState", b: "BlockState") -> None:
    """Обменивает содержимое двух блоков (модель, имя, параметры и т.д.).
    pre_post и slot_id — физические атрибуты слота — не трогаем.
    """
    for field in _SWAP_FIELDS:
        val_a = getattr(a, field)
        val_b = getattr(b, field)
        # Параметры и extra — копируем (list/dict), чтобы не иметь общих ссылок
        if isinstance(val_a, list):
            setattr(a, field, list(val_b))
            setattr(b, field, list(val_a))
        elif isinstance(val_a, dict):
            setattr(a, field, dict(val_b))
            setattr(b, field, dict(val_a))
        else:
            setattr(a, field, val_b)
            setattr(b, field, val_a)


# ── Публичный API ─────────────────────────────────────────────────

def flip_prepost(bid: str, new_pp: int, blocks: dict) -> None:
    """Сценарий 1: просто меняет флаг PRE/POST у блока.
    Вызывается когда юзер дропает блок в зону 1 (открытое пространство панели).

    Args:
        bid:    ID блока ('FX1', 'FX2', 'FX3', 'REV', 'VOL')
        new_pp: 0=PRE, 1=POST
        blocks: dict[str, BlockState] — всё состояние
    """
    b = blocks.get(bid)
    if b is None:
        return
    b.pre_post = new_pp


def swap_blocks(bid_a: str, bid_b: str, blocks: dict) -> None:
    """Сценарий 2 / 4: чистый обмен содержимым двух слотов.
    pre_post каждого слота остаётся прежним.
    Вызывается для:
      - Зона 3 (drop прямо на блок) — безусловный свап
      - Зона 2 внутри одной зоны (оба PRE или оба POST)

    Args:
        bid_a, bid_b: ID блоков для свапа
        blocks:       dict[str, BlockState]
    """
    a = blocks.get(bid_a)
    b = blocks.get(bid_b)
    if a is None or b is None:
        return
    _swap_content(a, b)


def combo_swap(bid_a: str, bid_b: str, new_pp_a: int, new_pp_b: int, blocks: dict) -> None:
    """Сценарий 3: обмен содержимым + установка новых pre/post флагов.
    Вызывается для Зоны 2 при кросс-зонном дропе (PRE ↔ POST через AMP).

    Блок A получает новый pre/post = new_pp_a,
    Блок B получает новый pre/post = new_pp_b.
    Обычно это «блоки меняются флагами» (A берёт флаг B, B берёт флаг A).

    Args:
        bid_a, bid_b:       ID блоков
        new_pp_a, new_pp_b: новые значения pre_post (0=PRE, 1=POST)
        blocks:             dict[str, BlockState]
    """
    a = blocks.get(bid_a)
    b = blocks.get(bid_b)
    if a is None or b is None:
        return
    _swap_content(a, b)
    a.pre_post = new_pp_a
    b.pre_post = new_pp_b


# ── Утилита для детектирования зоны ──────────────────────────────

def determine_swap_type(bid_src: str, bid_tgt: str, blocks: dict) -> tuple[str, int, int]:
    """Определяет тип свапа для Зоны 2 по текущим pre_post флагам.

    Returns:
        (swap_type, new_pp_src, new_pp_tgt)
        swap_type: 'clean' — тот же pre_post у обоих, флаги не меняем
                   'combo' — разные pre_post, меняем флаги местами
        new_pp_src/tgt: новые значения (для 'clean' это текущие значения)
    """
    src = blocks[bid_src]
    tgt = blocks[bid_tgt]

    if src.pre_post == tgt.pre_post:
        # Внутри одной зоны — чистый свап без изменения флагов
        return ("clean", src.pre_post, tgt.pre_post)
    else:
        # Кросс-зонный — меняемся флагами
        return ("combo", tgt.pre_post, src.pre_post)
