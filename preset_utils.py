"""
Utility for converting POD HD300 presets between .h3e and raw SysEx formats.
Consolidates logic from h3e_to_sysex.py and sysex_to_h3e.py.
"""
import struct

SWAP_INDICES = set(
    list(range(8, 17)) +
    [19, 20, 21, 22, 23, 24, 25,
     26, 27, 28, 29, 30, 31,
     32, 33] +
    list(range(49, 73)) +
    [74, 75, 76, 79]
)

# ── H3E Header Constants ──
H3E_MAGIC = b'H3EP'
H3E_VERSION = 0x00000001

def byteswap_h3e(data: bytearray) -> bytearray:
    """Apply big->little endian conversion (sub_407FC0)."""
    out = bytearray(data)
    for idx in SWAP_INDICES:
        b = idx * 2
        if b + 1 < len(out):
            out[b], out[b+1] = out[b+1], out[b]
    # Three bytes at offset 155: >>= 7 (boolean flags in MSB)
    for i in range(3):
        if 155 + i < len(out):
            out[155 + i] >>= 7
    return out

def byteswap_reverse(data: bytearray) -> bytearray:
    """Reverse byteswap from SysEx 8-bit back to H3E format."""
    out = bytearray(data)
    for i in range(3):
        pos = 155 + i
        if pos < len(out):
            out[pos] = (out[pos] & 0x01) << 7
    for idx in SWAP_INDICES:
        b = idx * 2
        if b + 1 < len(out):
            out[b], out[b + 1] = out[b + 1], out[b]
    return out

def compute_checksum(data) -> int:
    """Modified Fletcher checksum (sub_40A3B0). Input: 158 bytes."""
    A, B = 255, 255
    idx = 0
    remaining = 158
    while remaining > 0:
        chunk = min(21, remaining)
        remaining -= chunk
        for _ in range(chunk):
            A += data[idx]; B += A; idx += 1
        A = ((A >> 8) & 0xFF) + (A & 0xFF)
        B = ((B >> 8) & 0xFF) + (B & 0xFF)
    A = ((A >> 8) & 0xFF) + (A & 0xFF)
    B = ((B >> 8) & 0xFF) + (B & 0xFF)
    return (A << 8) | B

def pack_7to8(raw) -> list:
    """Pack raw bytes into MIDI 7-bit format (sub_40B290)."""
    packed = []
    for g in range(0, len(raw), 7):
        group = raw[g:g+7]
        msb_byte = 0
        for j, b in enumerate(group):
            msb_byte |= ((b >> 7) & 1) << (6 - j)
        packed.append(msb_byte)
        for b in group:
            packed.append(b & 0x7F)
    return packed

def unpack_7to8(packed: list) -> bytearray:
    """Unpack MIDI 7-bit format to raw bytes."""
    raw = []
    i = 0
    while i < len(packed):
        msb_byte = packed[i]; i += 1
        for j in range(7):
            if i >= len(packed):
                break
            b = packed[i]; i += 1
            msb_bit = (msb_byte >> (6 - j)) & 1
            raw.append(b | (msb_bit << 7))
    return bytearray(raw)

def build_h3e_header(params: bytearray) -> bytes:
    """Build the 40-byte .h3e header."""
    fixed = bytes([
        0x7D, 0x01, 0x00, 0x25, 0x02, 0x02, 0x00, 0x00,  # 0x08
        0x00, 0x14, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00,  # 0x10
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # 0x18
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # 0x20
    ])
    header = H3E_MAGIC + struct.pack('>I', H3E_VERSION) + fixed
    return header

def h3e_to_sysex_bytes(h3e: bytes, channel: int = 0) -> bytes:
    """Convert .h3e file content to a 0x7B SysEx edit buffer dump."""
    magic = h3e[0:4]
    if magic != b'H3EP':
        raise ValueError(f"Invalid magic: {magic} (expected H3EP)")

    params = bytearray(h3e[40:40+160])
    if len(h3e) < 200:
        raise ValueError(f"File too short: {len(h3e)} bytes, need at least 200")

    raw = byteswap_h3e(params)
    chk = compute_checksum(raw)
    raw[158] = chk & 0xFF
    raw[159] = (chk >> 8) & 0xFF

    packed = pack_7to8(raw)
    header = [0xF0, 0x00, 0x01, 0x0C, 0x14, channel & 0x7F,
              0x7B, 0x00, 0x7F, 0x7F, 0x00, 0x00]
    return bytes(header + packed + [0xF7])

def syx_bytes_to_h3e(syx: bytes) -> bytes:
    """Convert a 0x7B SysEx patch dump to .h3e format."""
    if syx[0] != 0xF0:
        raise ValueError(f"Not SysEx (first byte: 0x{syx[0]:02X}, expected 0xF0)")
    if syx[-1] != 0xF7:
        raise ValueError(f"SysEx not closed (last byte: 0x{syx[-1]:02X}, expected 0xF7)")
    if syx[1:5] != bytes([0x00, 0x01, 0x0C, 0x14]):
        raise ValueError(f"Invalid manufacturer ID: {syx[1:5].hex()} (expected 00 01 0C 14)")

    cmd = syx[6]
    if cmd != 0x7B:
        raise ValueError(f"Invalid command 0x{cmd:02X} (expected 0x7B patch dump)")

    packed = list(syx[12:-1])
    raw = unpack_7to8(packed)

    if len(raw) < 160:
        raise ValueError(f"Not enough data: {len(raw)} unpacked bytes, need 160")

    # Clear checksum bytes for .h3e
    raw[158] = 0x00
    raw[159] = 0x00

    params = byteswap_reverse(raw[:160])
    header = build_h3e_header(params)
    h3e = header + bytes(params)

    return h3e
