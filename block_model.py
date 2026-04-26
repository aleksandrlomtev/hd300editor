"""
Data model for a signal chain block (FX, AMP, CAB, Gate, Vol, Wah).
"""

from constants import (
    AMP_NAMES, CAB_NAMES, WAH_NAMES, FX_NAMES,
    CATEGORY_COLOR, CATEGORY_ICON,
)

# slot_ids for FX blocks (for MIDI command sending)
SLOT_IDS = {
    "FX1": 0x10, "FX2": 0x11, "FX3": 0x12, "REV": 0x13,
    "AMP": 0x02, "CAB": 0x02, "GATE": 0x02,
    "VOL": 0x02, "WAH": 0x02,
}


class BlockState:
    def __init__(self, block_id, name, category, slot_id=0x00, model_id=0x00, movable=True):
        self.block_id  = block_id
        self.category  = category
        self.slot_id   = slot_id
        self.model_id  = model_id
        self.movable   = movable
        self.is_on     = True
        self.pre_post  = 0       # 0=PRE, 1=POST
        self.params    = []      # list of float (%)
        self.extra     = {}      # additional fields (amp_id, cab_id, etc)
        self.update_name()

    def update_name(self):
        if self.block_id == "AMP":
            self.name = AMP_NAMES.get(self.model_id, f"Amp 0x{self.model_id:02X}")
        elif self.block_id == "CAB":
            self.name = CAB_NAMES.get(self.model_id, f"Cab 0x{self.model_id:02X}")
        elif self.block_id == "WAH":
            self.name = WAH_NAMES.get(self.model_id, f"Wah 0x{self.model_id:02X}")
        elif self.block_id in ["FX1", "FX2", "FX3", "REV"]:
            self.name = FX_NAMES.get(self.model_id, f"FX 0x{self.model_id:02X}")
        elif self.block_id == "VOL":
            self.name = "Volume Pedal"
        elif self.block_id == "GATE":
            self.name = "Noise Gate"
        else:
            self.name = "Unknown"

    def color(self):
        return CATEGORY_COLOR.get(self.category, "#3a3a3a")

    def icon(self):
        return CATEGORY_ICON.get(self.category, "◼")
