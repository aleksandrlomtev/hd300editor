"""
hd300_sysex_utils.py — SysEx utility functions for POD HD300

7-to-8 packing/unpacking and Fletcher checksum.
Reverse-engineered from Line 6 HD300 Edit via IDA Pro:
  - sub_40A3B0 = Fletcher checksum
  - sub_40B290 = 7-to-8 packing + SysEx assembly
"""


def unpack_7to8(packed):
    """Unpack 7-to-8 encoded MIDI data.

    Each group: 1 MSB byte + up to 7 data bytes.
    MSB byte bit layout: bit6=data[0].msb, bit5=data[1].msb, ..., bit0=data[6].msb

    184 packed bytes → 161 raw bytes (23 full groups × 7)
    """
    raw = []
    i = 0
    while i < len(packed):
        msb_byte = packed[i]
        i += 1
        group_len = min(7, len(packed) - i)
        for j in range(group_len):
            msb_bit = (msb_byte >> (6 - j)) & 1
            raw.append(packed[i + j] | (msb_bit << 7))
        i += group_len
    return raw


def pack_7to8(raw):
    """Pack raw data into 7-to-8 MIDI format.

    Every 7 raw bytes → 1 MSB byte + 7 data bytes (8 packed bytes).

    161 raw bytes → 184 packed bytes (23 groups × 8)
    """
    packed = []
    for g in range(0, len(raw), 7):
        group = raw[g:g + 7]
        msb_byte = 0
        for j, b in enumerate(group):
            msb_byte |= ((b >> 7) & 1) << (6 - j)
        packed.append(msb_byte)
        for b in group:
            packed.append(b & 0x7F)
    return packed


def compute_checksum(data_158):
    """Modified Fletcher checksum (IDA: sub_40A3B0).

    - Input:  first 158 bytes of the raw 160-byte preset buffer
    - Init:   A = 255, B = 255
    - Chunks: 21 bytes max per chunk
    - Inner:  A += byte, B += A
    - Fold:   after each chunk, A = hi(A) + lo(A), B = hi(B) + lo(B)
    - Final:  one more fold, return (A << 8) | B
    - Result: stored as WORD at raw[158..159] (little-endian: [158]=B, [159]=A)
    """
    A = 255
    B = 255
    idx = 0
    remaining = 158

    while remaining > 0:
        chunk = min(21, remaining)
        remaining -= chunk
        for _ in range(chunk):
            A += data_158[idx]
            B += A
            idx += 1
        A = ((A >> 8) & 0xFF) + (A & 0xFF)
        B = ((B >> 8) & 0xFF) + (B & 0xFF)

    A = ((A >> 8) & 0xFF) + (A & 0xFF)
    B = ((B >> 8) & 0xFF) + (B & 0xFF)
    return (A << 8) | B


def get_preset_name(sysex_raw):
    """Extract preset name from a full SysEx dump (197 bytes, F0..F7).

    Unpacks 7to8 and reads raw bytes 0-14 as the name.
    Returns the name string (stripped of trailing spaces).
    """
    packed = sysex_raw[12:-1]  # skip 12-byte header and F7
    raw = unpack_7to8(packed)
    name = ''.join(chr(b) if 32 <= b < 127 else '' for b in raw[0:15]).strip()
    return name


def make_save_sysex(edit_buffer_raw, preset_num, new_name=None):
    """Build a 'write' SysEx message from an edit buffer dump.

    Args:
        edit_buffer_raw: full SysEx bytes (list of int, F0..F7, 197 bytes)
        preset_num:      target slot number (0-127)
        new_name:        new preset name (str, max 15 chars) or None to keep current

    Returns:
        list of int — complete SysEx message ready to send (197 bytes, F0..F7)
    """
    header = list(edit_buffer_raw[0:12])
    packed = list(edit_buffer_raw[12:-1])  # 184 bytes

    # Unpack 7to8 → 161 raw bytes
    raw = unpack_7to8(packed)

    # Inject name if provided
    if new_name is not None:
        name_bytes = list(new_name.encode('ascii', errors='replace')[:15])
        while len(name_bytes) < 15:
            name_bytes.append(0x20)  # pad with spaces
        raw[0:15] = name_bytes

    # Recompute Fletcher checksum over bytes 0-157
    chk = compute_checksum(raw[:158])
    raw[158] = chk & 0xFF           # B (low byte)
    raw[159] = (chk >> 8) & 0xFF    # A (high byte)

    # Repack 7to8
    packed_out = pack_7to8(raw)

    # Fix header for 'write' mode: bytes 8-10 = 00 00 XX
    header[8] = 0x00
    header[9] = 0x00
    header[10] = preset_num & 0x7F

    return header + packed_out + [0xF7]


H3E_HEADER = bytes([
    0x48, 0x33, 0x45, 0x50, 0x00, 0x00, 0x00, 0x01,
    0x7D, 0x01, 0x00, 0x25, 0x02, 0x02, 0x00, 0x00,
    0x00, 0x14, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
])


# True if the byte at this index should be swapped with its pair (even-odd) in .h3e format
# This is due to PC (Little-Endian) struct packing vs Processor (Big-Endian) MIDI format.
H3E_SWAP_MASK = (
    [False] * 16 +          # 0x00 - 0x0F (Name, 16 bytes)
    [True] * 18 +           # 0x10 - 0x21 (18 bytes)
    [False] * 4 +           # 0x22 - 0x25 (4 bytes)
    [True] * 30 +           # 0x26 - 0x43 (30 bytes)
    [False] * 32 +          # 0x44 - 0x63 (32 bytes)
    [True] * 58 +           # 0x64 - 0x9D (58 bytes)
    [False] * 2             # 0x9E - 0x9F (Checksum, 2 bytes)
)


def _apply_h3e_endian_swap(data_160):
    """Swap even/odd byte pairs according to the struct endianness difference."""
    out = list(data_160)
    for i in range(0, 158, 2):
        if H3E_SWAP_MASK[i]:
            out[i], out[i+1] = data_160[i+1], data_160[i]
    return out


def h3e_to_sysex(h3e_bytes, preset_num=None, new_name=None):
    """Convert an .h3e file content to a SysEx message.

    Args:
        h3e_bytes: raw bytes of the .h3e file (expected 200 bytes)
        preset_num: target slot number (0-127). If None, generates an Edit Buffer dump.
        new_name: optional new name for the preset.

    Returns:
        list of int — complete SysEx message ready to send (197 bytes, F0..F7)
    """
    if len(h3e_bytes) < 200 or not h3e_bytes.startswith(b'H3EP'):
        raise ValueError("Invalid .h3e file format")

    h3e_data = list(h3e_bytes[40:200])  # 160 bytes
    
    # Reverse the endian swap from h3e format to get the true raw processor data
    raw = _apply_h3e_endian_swap(h3e_data)

    # Inject name if provided
    if new_name is not None:
        name_bytes = list(new_name.encode('ascii', errors='replace')[:15])
        while len(name_bytes) < 15:
            name_bytes.append(0x20)
        raw[0:15] = name_bytes

    # Compute Fletcher checksum and write to bytes 158, 159
    chk = compute_checksum(raw[:158])
    raw[158] = chk & 0xFF
    raw[159] = (chk >> 8) & 0xFF

    # Pack to 7to8
    packed_out = pack_7to8(raw)

    # Base SysEx Header for Preset Dump
    header = [0xF0, 0x00, 0x01, 0x0C, 0x14, 0x00, 0x7B, 0x00, 0x00, 0x00, 0x00, 0x00]

    # Set Mode bytes (8-10)
    if preset_num is not None:
        # Slot write
        header[8] = 0x00
        header[9] = 0x00
        header[10] = preset_num & 0x7F
    else:
        # Edit Buffer mode
        header[8] = 0x7F
        header[9] = 0x7F
        header[10] = 0x00

    return header + packed_out + [0xF7]


def sysex_to_h3e(sysex_raw):
    """Convert a SysEx dump to the .h3e file format.

    Args:
        sysex_raw: full SysEx bytes (list of int, F0..F7, 197 bytes)

    Returns:
        bytes: 200 bytes containing the .h3e file content.
    """
    packed = list(sysex_raw[12:-1])  # 184 bytes
    
    # Unpack 7to8 → 161 raw bytes
    raw = unpack_7to8(packed)
    
    # We only need the first 160 bytes
    preset_data = raw[:160]
    
    # Zero out checksum
    preset_data[158] = 0x00
    preset_data[159] = 0x00
    
    # Apply endian swap for .h3e format output
    h3e_data = _apply_h3e_endian_swap(preset_data)
    
    return H3E_HEADER + bytes(h3e_data)
