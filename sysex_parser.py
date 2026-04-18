"""
SysEx парсер для POD HD300: распаковка и разбор полного дампа пресета.
"""

from constants import FX_NAMES, WAH_NAMES


def unpack_sysex(data):
    unpacked = []
    i = 0
    while i < len(data):
        flags = data[i]; i += 1
        for bit in range(7):
            if i < len(data):
                val = data[i]; i += 1
                if flags & (1 << bit): val |= 0x80
                unpacked.append(val)
    return unpacked


def parse_full_dump(raw):
    """raw = полные байты дампа включая F0...F7"""
    if len(raw) < 30 or raw[0] != 0xF0:
        return None
    # HD300 preset dump = 197 байт, edit buffer dump = 192 байта.
    # Если длина отличается, скорее всего произошла потеря байта в MIDI потоке.
    VALID_LENS = {192, 197}
    if len(raw) not in VALID_LENS:
        print(f"[PARSE] ⚠️ Неожиданная длина дампа: {len(raw)} (допустимо: {VALID_LENS}). Дамп отброшен!")
        return None
    result = {}
    # пробуем найти имя пресета (может быть смещение)
    preset_name = "".join(
        chr(c) for c in raw[12:28] if 32 <= c <= 126
    ).strip()
    # попробуем другой диапазон если имя не нашли
    if not preset_name:
        preset_name = "".join(
            chr(c) for c in raw[10:26] if 32 <= c <= 126
        ).strip()
    result["preset_name"] = preset_name
    # Пробуем разные стартовые позиции для unpack
    # HD300: данные начинаются с raw[28] (проверено test_decode.py)
    u = unpack_sysex(raw[28:-1])
    if len(u) < 100:
        # попробуем с raw[26]
        u = unpack_sysex(raw[26:-1])
    if len(u) < 100:
        print(f"[PARSE] Слишком мало данных после unpack: {len(u)}")
        return None
    print(f"[PARSE] Распакованы {len(u)} байт, имя: '{preset_name}'")
    result["_u"] = u

    def r8(hex_addr):
        idx = int(hex_addr, 16) - 54
        return u[idx] if 0 <= idx < len(u) else 0

    def r16_pct(hex_addr):
        idx = int(hex_addr, 16) - 54
        if 0 <= idx < len(u) - 1:
            val = (u[idx] | (u[idx+1] << 8)) & 0x7FFF
            return round((val / 32767.0) * 100.0, 1)
        return 0.0

    def r16_gate_thresh(hex_addr):
        idx = int(hex_addr, 16) - 54
        if 0 <= idx < len(u) - 1:
            val = (u[idx] | (u[idx+1] << 8))
            if val == 0: val = 32768
            db_val = (val - 32768.0) / 100.0
            return max(0.0, min(100.0, ((db_val + 96.0) / 96.0) * 100.0))
        return 0.0

    def pct_from_u(idx):
        if idx + 1 < len(u):
            val = (u[idx] | (u[idx+1] << 8)) & 0x7FFF
            return round((val / 32767.0) * 100.0, 1)
        return 0.0


    s2 = u[2]
    result["gate_mode"]  = s2 & 0x03          # 0=OFF,1=Gate,2=NR,3=Gate+NR
    result["vol_post"]   = bool(s2 & 0x04)
    result["rev_post"]   = bool(s2 & 0x08)
    result["rev_on"]     = bool(s2 & 0x10)
    result["wah_on"]     = bool(s2 & 0x40)

    result["gate_thresh"] = r16_gate_thresh("58")
    result["gate_decay"]  = r16_pct("5A")
    result["vol_min"]     = r16_pct("54")
    result["vol_max"]     = r16_pct("56")

    result["amp_id"]  = (u[4] & 0x7F) + 1
    result["cab_id"]  = u[6] & 0x7F
    result["mic_id"]  = u[22] & 0x7F
    result["er_level"]= r16_pct("4E")
    result["preamp"]  = (u[23] & 0x7F) == 0x01
    result["amp_params"] = {
        "Drive":    r16_pct("3E"), "Bass":     r16_pct("40"),
        "Mid":      r16_pct("42"), "Treble":   r16_pct("44"),
        "Presence": r16_pct("48"), "Chan Vol": r16_pct("46"),
        "Master":   r16_pct("64"), "Sag":      r16_pct("5E"),
        "Hum":      r16_pct("5C"), "Bias":     r16_pct("60"),
        "Bias X":   r16_pct("62"),
        "Amp Mode": 100.0 if (u[23] & 0x7F) == 0x01 else 0.0,
    }

    wah_id = r8("6D") & 0x7F
    result["wah_id"]   = wah_id
    result["wah_name"] = WAH_NAMES.get(wah_id, f"Wah 0x{wah_id:02X}")
    result["wah_pos"]  = round(((r8("BA") & 0x7F) / 127.0) * 100.0, 1)

    fx_specs = {
        "FX1": {"model_addr": "6E", "state_addr": "72", "param_indices": [86,88,90,92,94]},
        "FX2": {"model_addr": "6F", "state_addr": "7A", "param_indices": [96,98,100,102,104,106]},
        "FX3": {"model_addr": "70", "state_addr": "82", "param_indices": [108,110,112,114,116,118]},
    }
    result["fx"] = {}
    for slot, spec in fx_specs.items():
        model_id  = r8(spec["model_addr"]) & 0x7F
        state_b   = r8(spec["state_addr"])
        is_on     = bool(state_b & 0x04)
        is_post   = bool(state_b & 0x02)
        params    = [pct_from_u(p_idx) for p_idx in spec["param_indices"]]

        result["fx"][slot] = {
            "model_id": model_id,
            "name":     FX_NAMES.get(model_id, f"0x{model_id:02X}"),
            "is_on":    is_on,
            "is_post":  is_post,
            "params":   params,
        }
    rev_id = r8("6C") & 0x7F
    rev_params = [pct_from_u(p) for p in [120, 122, 124, 126, 128, 130]]
    result["fx"]["REV"] = {
        "model_id": rev_id,
        "name":     FX_NAMES.get(rev_id, f"0x{rev_id:02X}"),
        "is_on":    result["rev_on"],
        "is_post":  result["rev_post"],
        "params":   rev_params,
    }
    return result
