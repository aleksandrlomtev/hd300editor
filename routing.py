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


def apply_visual_order(desired_order: list[str], blocks: dict) -> None:
    """Safely assigns contents of the desired_order blocks to the physical slots.
    
    The physical slots are strictly: FX1, FX2, FX3, REV.
    desired_order is a list of 4 block IDs (e.g., ["FX3", "FX1", "FX2", "REV"]).
    This means the slot FX1 will receive the contents of the old FX3,
    slot FX2 will receive FX1, etc.
    pre_post and slot_id of each physical slot are untouched during the content copy,
    but pre_post might be changed later by the caller if needed.
    """
    physical_slots = ["FX1", "FX2", "FX3", "REV"]
    if len(desired_order) != len(physical_slots):
        return

    # First, make a deep copy of the contents of the blocks in their current state
    # so we don't accidentally overwrite data we still need to move.
    contents = {}
    for bid in physical_slots:
        b = blocks.get(bid)
        if b is None: continue
        
        c = {}
        for field in _SWAP_FIELDS:
            val = getattr(b, field)
            if isinstance(val, list): c[field] = list(val)
            elif isinstance(val, dict): c[field] = dict(val)
            else: c[field] = val
        contents[bid] = c

    # Now, write the contents into the physical slots based on desired_order
    for phys_slot, src_bid in zip(physical_slots, desired_order):
        tgt_b = blocks.get(phys_slot)
        if tgt_b is None: continue
        
        c = contents.get(src_bid)
        if not c: continue
        
        for field in _SWAP_FIELDS:
            setattr(tgt_b, field, c[field])


