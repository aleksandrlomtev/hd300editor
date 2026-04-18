"""
routing.py — free routing logic for FX blocks.

Public functions:
  flip_prepost   — Scenario 1 (pre/post flag change only)
  swap_blocks    — Scenario 2/4 (clean content swap, flags untouched)
  combo_swap     — Scenario 3 (swap + new pre/post for both)

No dependencies on Qt or mido. Only mutations of BlockState objects.
The calling code is responsible for sending MIDI commands afterwards.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from block_model import BlockState


# ── Swappable fields of BlockState ────────────────────────────────────
# Everything except block_id and slot_id — they are tied to physical slots.
# pre_post is ALSO NOT in the list — it is handled separately.
_SWAP_FIELDS = (
    "model_id",
    "name",
    "category",
    "is_on",
    "params",
    "extra",
)


def _swap_content(a: "BlockState", b: "BlockState") -> None:
    """Exchanges content of two blocks (model, name, parameters, etc.).
    pre_post and slot_id — physical slot attributes — are untouched.
    """
    for field in _SWAP_FIELDS:
        val_a = getattr(a, field)
        val_b = getattr(b, field)
        # Parameters and extra — copy (list/dict) to avoid shared references
        if isinstance(val_a, list):
            setattr(a, field, list(val_b))
            setattr(b, field, list(val_a))
        elif isinstance(val_a, dict):
            setattr(a, field, dict(val_b))
            setattr(b, field, dict(val_a))
        else:
            setattr(a, field, val_b)
            setattr(b, field, val_a)


# ── Public API ─────────────────────────────────────────────────

def flip_prepost(bid: str, new_pp: int, blocks: dict) -> None:
    """Scenario 1: simply changes the PRE/POST flag of a block.
    Called when user drops a block into Zone 1 (empty panel space).

    Args:
        bid:    Block ID ('FX1', 'FX2', 'FX3', 'REV', 'VOL')
        new_pp: 0=PRE, 1=POST
        blocks: dict[str, BlockState] — entire state
    """
    b = blocks.get(bid)
    if b is None:
        return
    b.pre_post = new_pp


def swap_blocks(bid_a: str, bid_b: str, blocks: dict) -> None:
    """Scenario 2 / 4: clean exchange of content between two slots.
    pre_post of each slot remains unchanged.
    Called for:
      - Zone 3 (drop directly on block) — unconditional swap
      - Zone 2 inside same zone (both PRE or both POST)

    Args:
        bid_a, bid_b: Block IDs for swap
        blocks:       dict[str, BlockState]
    """
    a = blocks.get(bid_a)
    b = blocks.get(bid_b)
    if a is None or b is None:
        return
    _swap_content(a, b)


def combo_swap(bid_a: str, bid_b: str, new_pp_a: int, new_pp_b: int, blocks: dict) -> None:
    """Scenario 3: content exchange + setting new pre/post flags.
    Called for Zone 2 cross-zone drops (PRE ↔ POST via AMP).

    Block A gets new pre/post = new_pp_a,
    Block B gets new pre/post = new_pp_b.
    Usually blocks "swap flags" (A takes B's flag, B takes A's flag).

    Args:
        bid_a, bid_b:       Block IDs
        new_pp_a, new_pp_b: new pre_post values (0=PRE, 1=POST)
        blocks:             dict[str, BlockState]
    """
    a = blocks.get(bid_a)
    b = blocks.get(bid_b)
    if a is None or b is None:
        return
    _swap_content(a, b)
    a.pre_post = new_pp_a
    b.pre_post = new_pp_b


# ── Zone Detection Utility ──────────────────────────────

def determine_swap_type(bid_src: str, bid_tgt: str, blocks: dict) -> tuple[str, int, int]:
    """Determines swap type for Zone 2 based on current pre_post flags.

    Returns:
        (swap_type, new_pp_src, new_pp_tgt)
        swap_type: 'clean' — same pre_post for both, flags unchanged
                   'combo' — different pre_post, swap flags
        new_pp_src/tgt: new values (for 'clean' these are current values)
    """
    src = blocks[bid_src]
    tgt = blocks[bid_tgt]

    if src.pre_post == tgt.pre_post:
        # Same zone — clean swap without changing flags
        return ("clean", src.pre_post, tgt.pre_post)
    else:
        # Cross-zone — swap flags
        return ("combo", tgt.pre_post, src.pre_post)
