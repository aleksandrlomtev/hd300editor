"""
MidiEngineMixin — вся MIDI-логика (connect, send, receive, parse) для POD HD300.
Используется как mixin для MainWindow, поэтому self.* ссылки работают напрямую.
"""

import time
import threading

try:
    import mido
    MIDO_OK = True
except ImportError:
    MIDO_OK = False

from PyQt6.QtCore import QTimer

from constants import FX_NAMES, AMP_NAMES, CAB_NAMES, MATCHED_CABS
from sysex_parser import parse_full_dump, unpack_sysex


class MidiEngineMixin:
    """Mixin-класс, подмешиваемый в MainWindow. Весь MIDI I/O."""

    # ══ Подключение ══════════════════════════════

    def _auto_connect(self):
        if not MIDO_OK:
            self._log("⚠️ mido не найден. MIDI недоступен.")
            return
        try:
            ins  = mido.get_input_names()
            outs = mido.get_output_names()
            hin  = next((n for n in ins  if "POD HD300" in n or "HD300" in n), None)
            hout = next((n for n in outs if "POD HD300" in n or "HD300" in n), None)
            if hin and hout:
                self.midi_in  = mido.open_input(hin, callback=self._midi_cb)
                self.midi_out = mido.open_output(hout)
                self.conn_lbl.setText("● CONNECTED")
                self.conn_lbl.setStyleSheet("background: transparent; color: #4caf50; font-weight:bold; font-size:9pt;")
                self._log(f"✅ MIDI: {hin}")
                # Шаг 1: запрашиваем номер текущего пресета
                self._request_preset_no()
            else:
                self.conn_lbl.setText("○ NOT FOUND")
                self.conn_lbl.setStyleSheet("background: transparent; color: #e74c3c; font-weight:bold; font-size:9pt;")
                self._log(f"MIDI: устройство не найдено. Доступно: {ins}")
        except Exception as e:
            self._log(f"❌ MIDI ошибка: {e}")

    def _midi_cb(self, msg):
        self._sig_midi_led.emit("rx")
        
        # DEBUG LOGGING (Level 2)
        if getattr(self, "log_level", 1) >= 2:
            if msg.type == 'sysex':
                hex_str = " ".join(f"{b:02X}" for b in [0xF0] + list(msg.data) + [0xF7])
                print(f"[MIDI-RX] {hex_str}")
            elif msg.type == 'program_change':
                print(f"[MIDI-RX] Program Change: {msg.program}")
            elif msg.type == 'control_change':
                print(f"[MIDI-RX] CC: {msg.control:02X} = {msg.value:02X}")

        if msg.type == 'sysex':
            raw = [0xF0] + list(msg.data) + [0xF7]
            if len(raw) > 7 and raw[6] == 0x7B:
                self._sig_dump_raw.emit(raw)
            else:
                self._sig_sysex.emit(raw)
        elif msg.type == 'program_change':
            self._sig_prog_chg.emit(msg.program)
        elif msg.type == 'control_change':
            if msg.control == 0x04:  # CC#04 (Foot Controller) - WAH Pos
                if hasattr(self, '_sig_cc'):
                    self._sig_cc.emit(msg.value)

    def _on_cc_pedal(self, val):
        """Обработка CC#04 (Педаль экспрессии) - обновление WAH Pos."""
        pct = (val / 127.0) * 100.0
        b_wah = self.blocks.get("WAH")
        if b_wah:
            # Обновляем значение, даже если блок выключен, чтобы ползунок всегда реагировал
            if not b_wah.params:
                b_wah.params = [pct]
            else:
                b_wah.params[0] = pct
                
            if self.selected_id == "WAH":
                self._update_slider(0x08, pct)
            self._log(f"[LIVE] WAH Pos (via CC#4) = {pct:.1f}%")

    # ══ Приём SysEx ══════════════════════════════

    def _on_sysex(self, raw):
        if getattr(self, "_is_warming_up", False):
            return # Игнорируем эхо при "прогреве", чтобы не ломать UI
            
        if len(raw) < 8 or raw[0] != 0xF0:
            return
        cmd = raw[6]
        # УБРАН ТЯЖЕЛЫЙ PRINT КОТОРЫЙ ТРОТЛИЛ БУФЕР
        
        if cmd == 0x7B:   
            return # Теперь обрабатывается через _on_dump_raw напрямую
            
        elif cmd in [0x5C, 0x5D, 0x5E]:
            # Обработка состояния On/Off или Pre/Post (CMD 5D/5E)
            self._parse_state(raw)
        elif cmd == 0x62:
            # Ответ с номером текущего пресета ТОЛЬКО если sub-type 04:07
            if len(raw) >= 13 and raw[8] == 0x04 and raw[9] == 0x07:
                preset_no = raw[12]
                self._on_got_preset_no(preset_no)
            else:
                self._parse_live(raw)
        elif cmd == 0x63:
            self._parse_live(raw)

    # ══ Парсинг состояний ════════════════════════

    def _parse_state(self, raw):
        """Парсинг сообщений о байпасе или роутинге (CMD 0x5C/5D/5E).
        F0 00 01 0C 14 00 [CMD] 00 [SLOT] [VAL] F7
        """
        if len(raw) < 10: return
        slot_raw = raw[8]
        
        # Запрашиваем дамп для 100% синхронизации, так как тут может быть и роутинг, и bypass
        self._log(f"[STATE] Hardware state changed (CMD {raw[6]:02X}, Slot {slot_raw:02X}). Syncing...")
        self._trigger_live_sync()

    def _normalize_slot(self, slot_raw):
        """Приводит сырой слот с железки к внутреннему стандарту (0x10-0x13 для FX, 0x02 для системных)."""
        if 0x30 <= slot_raw <= 0x33:
            return 0x10 + (slot_raw - 0x30)
            
        # Специальный случай для системных блоков (AMP/GATE) на 0x22
        if slot_raw == 0x22:
            return 0x02
            
        if 0x20 <= slot_raw <= 0x23:
            return 0x10 + (slot_raw - 0x20)
        return slot_raw

    def _parse_live(self, raw):
        """Обработка живого обновления параметра от крутилок и ответов на запросы."""
        if len(raw) < 13: return
        cmd   = raw[6]
        slot_raw = raw[8]
        param = raw[9]
        v1, v2, v3 = raw[10], raw[11], raw[12] if len(raw) > 12 else (raw[10], raw[11], 0)
        # 21-битное значение
        val = (v1 << 14) | (v2 << 7) | v3

        # 1. Learn Mode (в сервисном режиме)
        if self._learning_row:
            # СОХРАНЯЕМ НОРМАЛИЗОВАННЫЙ ID, чтобы больше не было коллизий raw/norm
            norm_id = self._normalize_slot(slot_raw)
            self._learning_row.cfg["hw_idx"] = param
            self._learning_row.idx_spin.setValue(param)
            self._learning_row.cfg["slot_id"] = norm_id # Теперь тут всегда 0x10-0x13
            if self.selected_id in self.blocks:
                self.blocks[self.selected_id].slot_id = norm_id
            self._learning_row.btn_learn.setChecked(False)
            self._learning_row.setStyleSheet("") 
            self._learning_row = None
            self._log(f"✅ Learn: Привязано к Slot {norm_id:02X} (Raw: {slot_raw:02X}), Param {param:02X}")
            return

        # 2. НОРМАЛИЗАЦИЯ И ОПРЕДЕЛЕНИЕ БЛОКА
        target_bid = None
        slot = self._normalize_slot(slot_raw)

        # --- ПРОВЕРКА НА ИЗМЕНЕНИЕ МОДЕЛИ ИЛИ ОСОБЫХ СОСТОЯНИЙ (Pre/Post, On/Off) ---
        if (0x10 <= slot_raw <= 0x13 and param == 0x00) or \
           (slot_raw == 0x00 and param == 0x0A) or \
           (slot_raw == 0x02 and param == 0x13):
            self._log(f"[LIVE] Important State/Model Changed (Slot {slot_raw:02X}, Param {param:02X}). Syncing...")
            self._trigger_live_sync()
            return
        
        # Ищем блок по slot_id (в blocks)
        potential_bids = [bid for bid, b in self.blocks.items() if b.slot_id == slot]
        if not potential_bids:
            # Специфичный fallback для некоторых команд AMP на слоте 0x02
            if slot == 0x02: target_bid = "AMP" 
        elif len(potential_bids) == 1:
            target_bid = potential_bids[0]
        
        # Спец-эвристики
        if slot_raw == 0x20 and param <= 0x05:
            # Ручки усилка Drive/Bass/Mid... всегда прилетают в 0x20
            target_bid = "AMP"
        elif slot_raw == 0x02:
            if param in [0x0A, 0x0B, 0x0C]:   target_bid = "GATE"
            elif param in [0x07, 0x08, 0x09]: target_bid = "VOL"
            elif param == 0x12:               target_bid = "WAH"
            else:                             target_bid = "AMP"
        
        if not target_bid: return

        # 2. ПАРСИНГ ПАРАМЕТРОВ (CMD 0x63 / 0x62)
        if cmd in [0x62, 0x63]:
            # Спец-обработка для головы (AMP) On/Off через параметр 14
            if target_bid == "AMP" and param == 0x14:
                b = self.blocks.get("AMP")
                if b:
                    b.is_on = bool(val & 0x01)
                    self._update_block_state_ui("AMP")
                    self._refresh_chain()
                return

            b = self.blocks.get(target_bid)
            if not b: return
            
            mapping = self._get_mapping(target_bid)
            
            # РАЗДЕЛЕНИЕ ПО СЛОТАМ: 0x1x - СТЕЙТ (Routing/OnOff), 0x2x/0x3x - КРУТИЛКИ
            is_state_slot = (0x10 <= slot_raw <= 0x13)
            
            if is_state_slot:
                if param == 0x01:
                    b.pre_post = 1 if val > 0 else 0
                    self._update_block_state_ui(target_bid)
                    self._log(f"[LIVE-S] {target_bid} ({b.name}) ROUTING={'POST' if b.pre_post else 'PRE'}")
                    self._refresh_chain()
                    return
                elif param == 0x03:
                    b.is_on = (val > 0)
                    self._update_block_state_ui(target_bid)
                    self._log(f"[LIVE-S] {target_bid} ({b.name}) ON={b.is_on}")
                    self._refresh_chain()
                    return
                return
            
            # Для VOL (Pre/Post) на слоте 02
            if slot_raw == 0x02 and param == 0x07:
                self.blocks["VOL"].pre_post = 1 if val > 0 else 0
                self._update_block_state_ui("VOL")
                self._log(f"[LIVE-S] VOL ROUTING={'POST' if self.blocks['VOL'].pre_post else 'PRE'}")
                self._refresh_chain()
                return
            
            # Поиск параметра в маппинге
            p_cfg = None
            p_idx = -1
            search_param = param
            for i, cfg in enumerate(mapping):
                if cfg.get("hw_idx") == search_param:
                    p_cfg = cfg
                    p_idx = p_cfg.get("cache_idx", i)
                    break
            
            # Режим сдвига для FX2/3/REV
            if p_idx == -1 and target_bid in ("FX2", "FX3", "REV"):
                search_param = param + 1
                for i, cfg in enumerate(mapping):
                    if cfg.get("hw_idx") == search_param:
                        p_cfg = cfg
                        p_idx = p_cfg.get("cache_idx", i)
                        break
            
            if p_idx == -1: return

            pct = 0.0
            hi_res = p_cfg.get("hi_res", True)
            
            if p_cfg.get("type") == "steps_24":
                if val >= 1048576: steps = -(val - 1048576) / 1000.0
                else: steps = val / 1000.0
                pct = ((steps + 24.0) / 48.0) * 100.0
            elif p_cfg.get("scaling") == "gate_thresh":
                if val >= 1048576:
                    db = -(val - 1048576) / 1000.0
                    pct = ((db + 96.0) / 96.0) * 100.0
                else: pct = 100.0
            elif hi_res:
                hw_max = p_cfg.get("hw_max", 2097151)
                raw_pct = (val / float(hw_max)) * 100.0 if hw_max > 0 else 0.0
                pct = 100.0 - raw_pct if p_cfg.get("reverse", False) else raw_pct
            else:
                vals = p_cfg.get("values", [])
                if vals:
                    pct = (val / (len(vals) - 1)) * 100.0
                else:
                    pct = (val / 127.0) * 100.0

            pct = max(0.0, min(100.0, pct))
            if p_idx < len(b.params):
                b.params[p_idx] = pct
                if target_bid == self.selected_id:
                    self._update_slider(param, pct)
                self._log(f"[LIVE] {target_bid} ({b.name}) P{param:02X} = {pct:.1f}%")

    # ══ Построение и отправка SysEx ══════════════

    def _make_sysex(self, slot_id, param_idx, val_int, hi_res=True, cmd=0x63):
        header = [0x00, 0x01, 0x0C, 0x14, 0x00, cmd, 0x00, slot_id, param_idx]
        if hi_res:
            v1 = (val_int >> 14) & 0x7F
            v2 = (val_int >> 7)  & 0x7F
            v3 =  val_int        & 0x7F
        else:
            v1, v2, v3 = 0x00, 0x00, val_int & 0x7F
        return header + [v1, v2, v3]

    def _send_raw(self, data):
        if self.midi_out:
            try:
                if getattr(self, "log_level", 1) >= 2:
                    hex_str = " ".join(f"{b:02X}" for b in ([0xF0] + data + [0xF7] if data[0] != 0xF0 else data))
                    print(f"[MIDI-TX] {hex_str}")
                
                self.midi_out.send(mido.Message('sysex', data=data))
                self._sig_midi_led.emit("tx")
            except Exception as e:
                self._log(f"❌ Send error: {e}")

    def _send_usb_mute(self, is_muted):
        val = 0 if is_muted else 2097151 
        data = self._make_sysex(0x04, 0x19, val, hi_res=True)
        self._send_raw(data)

    def _send_fx_type(self, bid):
        b = self.blocks[bid]
        slot = b.slot_id
        param = 0x00
        val = b.model_id
        if bid == "AMP":
            slot = 0x00
            param = 0x0A 
            val = b.model_id + 1 
        elif bid == "CAB":
            slot = 0x02
            param = 0x13 
            val = b.model_id 
        elif bid == "WAH":
            slot = 0x02
            param = 0x12
            val = b.model_id
            
        data = self._make_sysex(slot, param, val, hi_res=False, cmd=0x63)
        self._send_raw(data)
        self._log(f"→ {bid} TYPE: 0x{val:02X} (Slot {slot:02X}, P{param:02X})")

    def _send_on_off(self, bid):
        """Прослойка для вызова корректного метода включения/выключения."""
        b = self.blocks.get(bid)
        if b:
            self.set_block_on(bid, b.is_on)

    def _send_pre_post(self, bid):
        """Отправляет PRE/POST позицию блока."""
        b = self.blocks[bid]
        # Для VOL роутинг на Slot 02, Param 07. Для остальных - Param 01 на основном слоте.
        slot = 0x02 if bid == "VOL" else b.slot_id
        param = 0x07 if bid == "VOL" else 0x01
        
        data = self._make_sysex(slot, param, b.pre_post, hi_res=False)
        self._send_raw(data)
        self._log(f"→ PRE/POST {bid}: {'POST' if b.pre_post else 'PRE'} (Slot {slot:02X}, P={param:02X})")

    def _send_param(self, bid, cfg, pct):
        """Отправляет значение параметра в % (0-100)."""
        b    = self.blocks[bid]
        send_slot = cfg.get("slot_id", b.slot_id)
        
        # Список слотов, куда слать команду (для FX блоков нужно слать в два диапазона для апдейта edit buffer)
        target_slots = []
        
        if bid in ["FX1", "FX2", "FX3", "REV"] and not cfg.get("no_offset"):
            # Оба слота нужны для живого звука
            base = b.slot_id
            target_slots = [base + 0x10, base + 0x20]
        elif send_slot == 0x00 and not cfg.get("no_offset"):
            # Слот 0x00 (базовые AMP-шные крутилки Drive/Bass/Mid/Treble/ChVol) → офсет +0x20
            target_slots = [0x20]
        else:
            # Для всех остальных (GATE, VOL, WAH или если no_offset) шлём как есть
            target_slots = [send_slot]
            
        hw_idx = cfg.get("hw_idx", 0)
        hi_res = cfg.get("hi_res", True)
        hw_max = cfg.get("hw_max", 2097151)
        is_reverse = cfg.get("reverse", False)
        scaling   = cfg.get("scaling")
        
        if scaling == "gate_thresh":
            db_val = -96.0 + (pct / 100.0) * 96.0
            if db_val >= 0.0:
                val = 0
            else:
                val = int(1048576 + (-db_val) * 1000)
        elif cfg.get("type") == "steps_24":
            steps = round((pct / 100.0) * 48.0 - 24.0)
            if steps == 0:
                val = 0
            elif steps < 0:
                val = 1048576 + int(abs(steps) * 1000)
            else:
                val = int(steps * 1000)
        elif hi_res:
            raw_pct = 100.0 - pct if is_reverse else pct
            val = int((raw_pct / 100.0) * hw_max)
        else:
            vals = cfg.get("values", [])
            if vals:
                val = int(round((pct / 100.0) * (len(vals) - 1)))
            else:
                val = int(round((pct / 100.0) * 127))

        for s in target_slots:
            # Только 0x63 (живой звук) — коммит пойдёт отложенно через _commit_param
            data_63 = self._make_sysex(s, hw_idx, val, hi_res=hi_res, cmd=0x63)
            self._send_raw(data_63)

        self._log(f"→ PARAM {bid} P{hw_idx:02X} = {val} ({'HI' if hi_res else 'LO'}) [63 live]")
        
        # Запоминаем для отложенного коммита
        self._last_commit_info = {
            "slots": target_slots, "hw_idx": hw_idx, "val": val,
            "hi_res": hi_res, "bid": bid,
        }

    def set_block_on(self, bid, is_on):
        """Включает или выключает блок. Для головы (AMP) шлет 0x63 на 02:14."""
        b = self.blocks.get(bid)
        if not b: return
        
        # Для головы (AMP) статус шлется как параметр в слоте 02
        if bid == "AMP":
            slot = 0x02
            param = 0x14
            val = 1 if is_on else 0
            data = self._make_sysex(slot, param, val, hi_res=False, cmd=0x63)
        elif bid == "WAH":
            slot = 0x00
            param = 0x09
            val = 1 if is_on else 0
            data = self._make_sysex(slot, param, val, hi_res=False, cmd=0x63)
        else:
            # Стандартный On/Off для FX блоков
            slot = b.slot_id
            val = 1 if is_on else 0
            # У CMD 0x5C параметр всегда 0x01 для FX
            data = self._make_sysex(slot, 0x01, val, hi_res=False, cmd=0x5C)
        
        self._send_raw(data)
        b.is_on = is_on
        self._update_block_state_ui(bid)
        self._refresh_chain()
        self._log(f"→ ON/OFF {bid}: {'ON' if is_on else 'OFF'}")

    # ══ Запросы к процессору ══════════════════════

    def _request_preset_no(self):
        """Шаг 1: запросить номер текущего пресета.
        F0 00 01 0C 14 00 60 00 04 07 F7
        """
        data = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x60, 0x00, 0x04, 0x07]
        self._send_raw(data)
        self._log("→ Запрос номера пресета...")

    def _request_preset_dump(self, preset_no):
        """Шаг 2: запросить дамп конкретного пресета.
        F0 00 01 0C 14 00 7C 00 b1 b2 b3 F7
        """
        b1 = (preset_no >> 14) & 0x7F
        b2 = (preset_no >> 7) & 0x7F
        b3 = preset_no & 0x7F
        data = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x7C, 0x00, b1, b2, b3]
        self._send_raw(data)
        if preset_no == 0x1FFFFF:
            self._log("→ Запрос дампа (Edit Buffer)...")
        else:
            self._log(f"→ Запрос дампа пресета #{preset_no}...")

    def _query_block_params(self, bid):
        """Запрашивает текущие значения ручек для указанного блока (в фоновом потоке)."""
        if getattr(self, "_midi_survey_lock", None) is None:
            self._midi_survey_lock = threading.Lock()
            
        def _worker():
            with self._midi_survey_lock:
                self._do_query_block_sync(bid)

        threading.Thread(target=_worker, daemon=True).start()

    def _do_query_block_sync(self, bid):
        """Внутренний синхронный метод опроса одного блока. Должен вызываться из потока."""
        mapping = self._get_mapping(bid)
        b = self.blocks[bid]
        
        self._log(f"→ Опрос {bid} ({b.name})...")

        # Расчитываем базовые ID для запросов
        base_slot = b.slot_id # Для стейта (0x10-0x13)
        # q_id для КРУТИЛОК (обычно base_slot + 0x20)
        # ИСКЛЮЧАЕМ 0x02 (GATE/VOL/WAH), так как они опрашиваются по прямому адресу
        q_id = base_slot + 0x20 if base_slot in [0x00, 0x10, 0x11, 0x12, 0x13] else base_slot

        # 1. ЗАПРОС СОСТОЯНИЯ (On/Off и Pre/Post)
        # Шлём в базовый слот (0x1x)
        if base_slot in [0x10, 0x11, 0x12, 0x13]:
            for s_param in [0x01, 0x03]:
                if not self.midi_out: return
                s_data = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x60, 0x00, base_slot, s_param]
                self._send_raw(s_data)
                time.sleep(0.008)
        elif bid == "WAH":
            # Спец-запрос статуса WAH On/Off
            if not self.midi_out: return
            s_data = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x60, 0x00, 0x00, 0x09]
            self._send_raw(s_data)
            time.sleep(0.008)

        # 2. ЗАПРОС КРУТИЛОК
        # Шлём в q_id (обычно 0x3x)
        for cfg in mapping:
            if not self.midi_out: return
            p_idx = cfg.get("hw_idx")
            if p_idx is None:
                continue
            
            # ВАЖНО: Если у параметра задан свой slot_id, шлём туда! (например, WAH Pos -> 0x00)
            target_slot = cfg.get("slot_id", q_id)
            data = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x60, 0x00, target_slot, p_idx]
            self._send_raw(data)
            time.sleep(0.008)

    def _request_dump(self):
        """Публичный метод кнопки Dump — запускает двухшаговый процесс."""
        self._request_preset_no()

    def _debounced_dump(self):
        """Выполняется после дебаунс-таймера при быстром листании пресетов."""
        if hasattr(self, '_pending_preset'):
            target = 0x1FFFFF if getattr(self, "load_edit_buffer", True) else self._pending_preset
            self._request_preset_dump(target)

    def _trigger_live_sync(self):
        """Запускает фоновый запрос дампа с задержкой, чтобы не спамить (debounce)"""
        if not hasattr(self, '_live_dump_debounce'):
            self._live_dump_debounce = QTimer(self)
            self._live_dump_debounce.setSingleShot(True)
            self._live_dump_debounce.timeout.connect(lambda: self._request_preset_dump(0x1FFFFF))
        self._live_dump_debounce.start(600)

    # ══ DI Mode ══════════════════════════════════

    def _toggle_di_mode(self):
        """Переключает проц в DI режим (пресет 32А + Mute USB + сохранение буфера)."""
        is_in_di = (self.current_preset_num >= 124)
        
        if not is_in_di:
            self.saved_preset_for_di = self.current_preset_num
            self._log(f"[DI] Вход в DI Mode. Запрашиваю Edit Buffer для сохранения...")
            self._waiting_for_di_dump = True
            # Запрашиваем дамп Edit Buffer
            self._request_preset_dump(0x1FFFFF)
            # Остальная логика (Mute/PC) сработает в _on_sysex при получении дампа
        else:
            restore_to = self.saved_preset_for_di if self.saved_preset_for_di is not None else 0
            self._log(f"[DI] Выход из DI Mode. Возвращаюсь на #{restore_to} и восстанавливаю буфер...")
            if self.midi_out:
                # 1. Возвращаем пресет
                self.midi_out.send(mido.Message('program_change', program=restore_to))
                # 2. Если есть сохраненный дамп — кидаем его в проц
                if self.saved_edit_buffer_for_di:
                    sysex_body = self.saved_edit_buffer_for_di[1:-1]
                    self.midi_out.send(mido.Message('sysex', data=sysex_body))
                    self._log("[DI] Сохраненный Edit Buffer отправлен в процессор.")
                
                # 3. Размьючиваем USB
                self._send_usb_mute(False)
            
            self.saved_edit_buffer_for_di = None

    def _force_unmute_usb(self):
        """Аварийный размьют USB по правому клику."""
        self._log("[DI] Принудительный размьют USB Monitoring.")
        self._send_usb_mute(False)

    # ══ LED индикатор ════════════════════════════

    def _midi_led(self, direction):
        """HDD-LED индикатор MIDI активности. TX=жёлтый, RX=синий."""
        if not hasattr(self, 'conn_lbl'): return
        if direction == "tx":
            self.conn_lbl.setText("● TX")
            self.conn_lbl.setStyleSheet("background: transparent; color: #f1c40f; font-weight:bold; font-size:9pt;")
        elif direction == "rx":
            self.conn_lbl.setText("● RX")
            self.conn_lbl.setStyleSheet("background: transparent; color: #3498db; font-weight:bold; font-size:9pt;")
        if not hasattr(self, '_led_timer'):
            self._led_timer = QTimer(self)
            self._led_timer.setSingleShot(True)
            self._led_timer.timeout.connect(self._midi_led_reset)
        self._led_timer.start(150)

    def _midi_led_reset(self):
        if hasattr(self, 'conn_lbl') and self.midi_out:
            self.conn_lbl.setText("● CONNECTED")
            self.conn_lbl.setStyleSheet("background: transparent; color: #4caf50; font-weight:bold; font-size:9pt;")
