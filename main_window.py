"""
MainWindow — main window of POD HD300 Visual Editor.
Inherits MidiEngineMixin for all MIDI logic.
"""

import sys
import os
import json
import time

try:
    import mido
    MIDO_OK = True
except ImportError:
    MIDO_OK = False

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QEvent, QEasingCurve, QPropertyAnimation
from PyQt6.QtGui import QColor, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QSplitter,
    QListWidget, QListWidgetItem, QLineEdit,
    QGraphicsBlurEffect,
)

from constants import (
    SCRIPT_DIR, FX_NAMES, AMP_NAMES, CAB_NAMES, WAH_NAMES, MATCHED_CABS,
    CATEGORY_COLOR, FX_IMG_MAP,
)
from constants import FX_NAMES, AMP_NAMES, CAB_NAMES, MATCHED_CABS
from block_model import BlockState
from sysex_parser import parse_full_dump, unpack_sysex
from invalid_wheelchair import warmup_4band_eq # Import shameful hacks
from routing import flip_prepost, swap_blocks, combo_swap, determine_swap_type
from midi_engine import MidiEngineMixin, MIDO_OK
from widgets import ParamRow, SignalChainPanel, DiModeButton, SettingsDialog

if sys.platform == "win32":
    import ctypes
    from platform_win import dwmapi


from hd300_sysex_utils import make_save_sysex, get_preset_name


class MainWindow(MidiEngineMixin, QMainWindow):
    _sig_sysex     = pyqtSignal(list)
    _sig_dump_raw  = pyqtSignal(list) # For passing unpacked dump bytes from background to GUI
    _sig_prog_chg  = pyqtSignal(int)
    _sig_midi_led  = pyqtSignal(str)
    _sig_log       = pyqtSignal(str)
    _sig_cc        = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("POD HD300 Visual Editor")
        self.resize(1280, 820)

        # Data
        self.fx_config   = self._load_json("hd300_fx_v2.json")
        self.cats_data   = self._load_json("cats.txt")
        self.ui_mappings = self._load_json("ui_mappings_v2.json") or {}
        self.preset_cache = self._load_json("preset_names_cache.json") or {}

        # MIDI state
        self.midi_in  = None
        self.midi_out = None

        # Block states
        self.blocks = {
            "GATE": BlockState("GATE", "Noise Gate",   "Gate",     0x02,  0x00, movable=False),
            "FX1":  BlockState("FX1",  "NONE",         "None",     0x10,  0x00, movable=True),
            "FX2":  BlockState("FX2",  "NONE",         "None",     0x11,  0x00, movable=True),
            "FX3":  BlockState("FX3",  "NONE",         "None",     0x12,  0x00, movable=True),
            "REV":  BlockState("REV",  "NONE",         "None",     0x13,  0x00, movable=True),
            "AMP":  BlockState("AMP",  "Amplifier",    "Amp",      0x02,  0x01, movable=False),
            "CAB":  BlockState("CAB",  "Cabinet",      "Cabinet",  0x02,  0x01, movable=False),
            "VOL":  BlockState("VOL",  "Vol Pedal",    "Vol",      0x02,  0x00, movable=True),
            "WAH":  BlockState("WAH",  "Wah Pedal",    "Wah",      0x02,  0x00, movable=False),
        }
        self.blocks["GATE"].pre_post = 0  # always PRE
        self.selected_id   = "FX1"
        self.mapping_mode  = False
        self.preset_name   = "---"
        
        self.settings = self._load_json("settings.json")
        self.sync_on_launch = self.settings.get("sync_on_launch", True)
        self.black_mode = self.settings.get("black_mode", False)
        self.remove_borders = self.settings.get("remove_borders", True)
        self.load_edit_buffer = self.settings.get("load_edit_buffer", True)
        self.experimental_free_routing = self.settings.get("experimental_free_routing", False)
        self.di_preset = self.settings.get("di_preset", 124)
        
        self.current_preset_num = 0
        self.saved_preset_for_di = None
        self.saved_edit_buffer_for_di = None
        self._waiting_for_di_dump = False
        self._waiting_for_save_dump = False
        self._pending_rename = None  # str or None

        self._sync_mode = False
        self._syncing_preset_idx = 0
        self._initial_sync_done = False

        # Таймер для дебаунса запроса дампа при быстром переключении пресетов
        self._dump_debounce = QTimer()
        self._dump_debounce.setSingleShot(True)
        self._dump_debounce.timeout.connect(self._debounced_dump)
        self._pending_preset = 0

        # Состояние Learn Mode
        self._learning_row = None
        
        self._last_rendered_bid = None
        self._last_rendered_model = None
        
        # Уровень логирования: 0 - выкл, 1 - инфо (интерфейс), 2 - дебаг (дамп MIDI в консоль)
        self.log_level = 2
        
        self._is_warming_up = False # Флаг для блокировки эха при прогреве блока
        self._sync_start_time = 0   # Для замера времени загрузки пресета
        
        # Таймер для дебаунса полной перерисовки
        self._rebuild_debounce = QTimer()
        self._rebuild_debounce.setSingleShot(True)
        self._rebuild_debounce.timeout.connect(self._render_params)
        
        # Блокировка для MIDI-обстрела (чтобы запросы не накладывались)
        self._midi_survey_lock = __import__('threading').Lock()
        self._is_surveying = False

        self.cats_data["Amp"] = list(AMP_NAMES.values())
        self.cats_data["Cabinet"] = list(CAB_NAMES.values())
        self.cats_data["Wah"] = list(WAH_NAMES.values())

        self._sig_sysex.connect(self._on_sysex)
        self._sig_dump_raw.connect(self._on_dump_raw)
        self._sig_prog_chg.connect(self._on_prog_chg)
        self._sig_midi_led.connect(self._midi_led)
        self._sig_log.connect(self._log_ui)
        self._sig_cc.connect(self._on_cc_pedal)

        self._build_ui()
        self._apply_styles()
        self._refresh_chain()
        self._select_block("FX1")

        QTimer.singleShot(300, self._auto_connect)

    # ── загрузка JSON/txt ──────────────────────────

    def _load_json(self, filename):
        path = os.path.join(SCRIPT_DIR, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[LOAD] {filename}: {e}")
        return {}

    def _save_settings(self):
        self.settings["sync_on_launch"] = getattr(self, "sync_on_launch", True)
        self.settings["black_mode"] = getattr(self, "black_mode", False)
        self.settings["remove_borders"] = getattr(self, "remove_borders", True)
        self.settings["load_edit_buffer"] = getattr(self, "load_edit_buffer", True)
        self.settings["experimental_free_routing"] = getattr(self, "experimental_free_routing", False)
        self.settings["di_preset"] = getattr(self, "di_preset", 124)
        path = os.path.join(SCRIPT_DIR, "settings.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"[SAVE] error: {e}")

    def _save_preset_cache(self):
        path = os.path.join(SCRIPT_DIR, "preset_names_cache.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.preset_cache, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self._log(f"Cache save error: {e}")

    def _clear_preset_cache(self):
        self.preset_cache = {}
        self._save_preset_cache()
        for p in range(128):
            bank = (p // 4) + 1
            sub  = ["A","B","C","D"][p % 4]
            it = self.preset_list.item(p)
            if it: it.setText(f"{bank:02d}{sub}")
        self._log("🗑 Preset cache cleared!")

    # ── сигнальная цепочка ─────────────────────────

    def _get_ordered_chain(self):
        vol  = self.blocks["VOL"]
        pre_fx  = [bid for bid in ["FX1","FX2","FX3","REV"]
                   if self.blocks[bid].pre_post == 0]
        post_fx = [bid for bid in ["FX1","FX2","FX3","REV"]
                   if self.blocks[bid].pre_post == 1]

        order = ["GATE"]
        if vol.pre_post == 0:
            order.append("VOL")
            order.append("WAH")
        else:
            order.append("WAH")
        order.extend(pre_fx)
        order += ["AMP", "CAB"]
        if vol.pre_post == 1:
            order.append("VOL")
        order.extend(post_fx)
        return order

    def _refresh_chain(self):
        order = self._get_ordered_chain()
        self.chain_panel.rebuild(order, self.blocks, self.selected_id)

    # ── выбор блока ────────────────────────────────

    def _select_block(self, bid):
        self.selected_id = bid
        b = self.blocks[bid]
        col = b.color()
        self.block_title.setText(f"  {b.name.upper()}")
        
        # Иконка эффекта из img_converted/
        img_file = FX_IMG_MAP.get(b.name)
        if img_file:
            icon_path = os.path.join(SCRIPT_DIR, "img_converted", img_file)
            if os.path.exists(icon_path):
                pixmap = QPixmap(icon_path).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.block_icon.setPixmap(pixmap)
                self.block_icon.setVisible(True)
            else:
                self.block_icon.setText(b.icon())
                self.block_icon.setVisible(True)
        else:
            self.block_icon.setText(b.icon())
            self.block_icon.setVisible(True)
        
        hm = getattr(self, "black_mode", False)
        # Акцентный цвет применяем всегда для заголовка и кнопок, чтобы панель была "в тему"
        if hm:
            self.block_title.setStyleSheet(f"font-size:13pt; font-weight:bold; color:{col};")
            self.btn_on.setStyleSheet(f"""
                QPushButton {{ background:#1a1c1f; color:{col}; border:1px solid {col}; }}
                QPushButton:checked {{ background:{col}; color: white; font-weight: bold; border:1px solid {col}; }}
                QPushButton:!checked {{ background:#1a1c1f; color:#555; border:1px solid #444; }}
            """)
            self.btn_pp.setStyleSheet(f"""
                QPushButton {{ background:#1a1c1f; color:{col}; border:1px solid {col}; }}
                QPushButton:checked {{ background:{col}; color:white; font-weight: bold; border:1px solid {col}; }}
            """)
        else:
            # В классическом режиме тоже подсвечиваем заголовок цветом категории
            self.block_title.setStyleSheet(f"font-size:13pt; font-weight:bold; color:{col};")
            self.btn_on.setStyleSheet(f"""
                QPushButton {{ background:#1a3a1a; color:#4caf50; border:1px solid #2e7d32; }}
                QPushButton:checked {{ background:{col}; color: white; border:1px solid {col}; }}
                QPushButton:!checked {{ background:#3a1a1a; color:#e53935; border:1px solid #b71c1c; }}
            """)
            self.btn_pp.setStyleSheet(f"""
                QPushButton {{ background:#1a2a3a; color:#2196f3; border:1px solid #1565c0; }}
                QPushButton:checked {{ background:{col}; color:white; border:1px solid {col}; }}
            """)
            
        self.btn_on.blockSignals(True)
        self.btn_on.setChecked(b.is_on)
        self.btn_on.setText("ON" if b.is_on else "OFF")
        self.btn_on.blockSignals(False)
        
        # Убираем кнопку включения у гейта и педали громкости
        self.btn_on.setVisible(bid not in ["GATE", "VOL", "CAB"])

        # Кнопка сохранения видна только в Mapping Mode
        if hasattr(self, "btn_save_cfg"):
            self.btn_save_cfg.setVisible(self.mapping_mode)
        if hasattr(self, "btn_clear_cache"):
            self.btn_clear_cache.setVisible(self.mapping_mode)

        # PRE/POST кнопка: показываем только для movable
        is_movable = bid in ("VOL","FX1","FX2","FX3","REV")
        self.btn_pp.setVisible(is_movable)
        if is_movable:
            self.btn_pp.blockSignals(True)
            self.btn_pp.setChecked(b.pre_post == 1)
            self.btn_pp.setText("POST" if b.pre_post == 1 else "PRE")
            self.btn_pp.blockSignals(False)

        # Динамический цвет выделения в списках
        self._update_list_accent(self.preset_list, col)
        self._update_list_accent(self.cat_list, col)
        self._update_list_accent(self.model_list, col)
        
        self._update_category_filter(bid)
        self._sync_browser_to_block(b)
        self._render_params()
        # Обновляем выделение в цепочке БЕЗ пересборки — чтобы не убивать BlockButton под drag'ом
        if hasattr(self, "chain_panel"):
            self.chain_panel.update_selection(bid)
        
        # Опрашиваем текущие параметры блока при его выборе, чтобы UI был актуальным
        if bid in ("FX1", "FX2", "FX3", "REV", "GATE"):
            QTimer.singleShot(80, lambda: self._query_block_params(bid))

    def _update_category_filter(self, bid):
        """Интеллектуальный фильтр категорий в зависимости от выбранного слота."""
        system_cats = ["Amp", "Cabinet", "Wah"]
        
        allowed = []
        if bid in ["GATE", "VOL"]:
            allowed = []
        elif bid == "AMP":
            allowed = ["Amp"]
        elif bid == "CAB":
            allowed = ["Cabinet"]
        elif bid == "WAH":
            allowed = ["Wah"]
        else:
            # FX слоты: всё кроме системных
            allowed = [c for c in self.cats_data.keys() if c not in system_cats]

        # Обновляем QListWidget
        any_valid_selected = False
        for i in range(self.cat_list.count()):
            item = self.cat_list.item(i)
            cat_name = item.text()
            is_enabled = cat_name in allowed
            
            if is_enabled:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)
                item.setForeground(QColor("#ffffff"))
                if self.cat_list.currentRow() == i:
                    any_valid_selected = True
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setForeground(QColor("#555555"))
        
        # Если текущая категория стала недоступной - сбрасываем список моделей
        if not any_valid_selected:
            self.model_list.clear()
            self.cat_list.clearSelection()
            self.cat_list.setCurrentRow(-1)

    # ── параметры ──────────────────────────────────

    def _get_mapping(self, bid):
        """Получить маппинг параметров для текущего блока. Приоритет UI JSON -> System Fixed -> Auto."""
        b = self.blocks[bid]
        model_hex = f"{b.model_id:02X}"
        
        # 1. ПРИОРИТЕТ: РУЧНОЙ МАППИНГ ИЗ UI JSON
        key = f"{model_hex}_{bid}"
        if key in self.ui_mappings:
            mapping = self.ui_mappings[key]
            for c in mapping:
                if "slot_id" in c:
                    b.slot_id = c["slot_id"]
                    break
            return mapping

        # 2. ДЛЯ СИСТЕМНЫХ БЛОКОВ (FALLBACK)
        fixed = {
            "GATE": [
                {"name":"Mode",     "hw_idx": 0x0C, "enabled":True, "step":1.0, "slot_id": 0x02, "values": ["Off", "Gate", "NR", "Gate+NR"], "hi_res": False},
                {"name":"Thresh",   "hw_idx": 0x0A, "enabled":True, "step":1.0, "slot_id": 0x02, "scaling": "gate_thresh", "unit": "dB", "min_disp": -96.0, "max_disp": 0.0, "decimals": 0},
                {"name":"Decay",    "hw_idx": 0x0B, "enabled":True, "step":1.0, "slot_id": 0x02, "decimals": 0},
            ],
            "VOL": [
                {"name":"Min Vol",  "hw_idx": 0x08, "enabled":True, "step":1.0, "slot_id": 0x02},
                {"name":"Max Vol",  "hw_idx": 0x09, "enabled":True, "step":1.0, "slot_id": 0x02},
            ],
            "WAH": [
                {"name":"Wah Pos",  "hw_idx": 0x08, "enabled":True, "step":1.0, "slot_id": 0x00, "no_offset": True},
            ],
            "AMP": [
                {"name": "Drive",    "hw_idx": 0x01, "enabled": True, "step": 1.0},
                {"name": "Bass",     "hw_idx": 0x02, "enabled": True, "step": 1.0},
                {"name": "Mid",      "hw_idx": 0x03, "enabled": True, "step": 1.0},
                {"name": "Treble",   "hw_idx": 0x04, "enabled": True, "step": 1.0},
                {"name": "Presence", "hw_idx": 0x1D, "enabled": True, "step": 1.0},
                {"name": "Ch Vol",   "hw_idx": 0x05, "enabled": True, "step": 1.0},
                {"name": "Master",   "hw_idx": 0x2A, "enabled": True, "step": 1.0},
                {"name": "PA Sag",   "hw_idx": 0x27, "enabled": True, "step": 1.0},
                {"name": "PA Hum",   "hw_idx": 0x26, "enabled": True, "step": 1.0},
                {"name": "PA Bias",  "hw_idx": 0x28, "enabled": True, "step": 1.0},
                {"name": "PA BiasX", "hw_idx": 0x29, "enabled": True, "step": 1.0},
                {"name": "Amp Mode", "hw_idx": 0x25, "enabled": True, "step": 1.0, "slot_id": 0x02, "values": ["Full", "Preamp"], "hi_res": False},
            ],
            "CAB": [
                {"name": "Microphone", "hw_idx": 0x24, "enabled": True, "step": 1.0, "hi_res": False,
                 "values": ["57 on xs", "57 off xs", "409 dynamic", "421 dynamic", "4038 ribbon", "121 ribbon", "67 cond", "87 cond"]},
                {"name": "E.R. Level", "hw_idx": 0x13, "enabled": True, "step": 1.0, "slot_id": 0x00, "no_offset": True},
            ],
        }
        
        # МАППИНГ HW_IDX -> INDEX IN b.params
        HW_TO_IDX = {
            "AMP": {0x01:0, 0x02:1, 0x03:2, 0x04:3, 0x1D:4, 0x05:5, 0x2A:6, 0x27:7, 0x26:8, 0x28:9, 0x29:10, 0x25:11},
            "CAB": {0x24:0, 0x13:1},
            "GATE": {0x0C:0, 0x0A:1, 0x0B:2}, # 0x0C=Mode, 0x0A=Thresh, 0x0B=Decay
            "VOL": {0x08:0, 0x09:1},
            "WAH": {0x08:0}
        }

        if bid in fixed:
            res = fixed[bid]
            # Добавляем инфо об индексе в кэше для каждой ручки
            if bid in HW_TO_IDX:
                for c in res:
                    h = c.get("hw_idx")
                    if h in HW_TO_IDX[bid]:
                        c["cache_idx"] = HW_TO_IDX[bid][h]
            return res
        
        # 3. ПОИСК В UI MAPPINGS (JSON ИЕРАРХИЯ)
        # {model}_{block} -> {model}_FX_OTHER -> fx_config
        key = f"{model_hex}_{bid}"
        data_list = None
        
        if key in self.ui_mappings:
            data_list = self.ui_mappings[key]
        else:
            gen_key = f"{model_hex}_FX_OTHER"
            if gen_key in self.ui_mappings:
                data_list = self.ui_mappings[gen_key]
            elif model_hex in self.fx_config:
                data_list = self.fx_config[model_hex].get("params", [])

        if not data_list:
            # Полная тишина в конфигах — генерим пустые 5/6 ручек
            n = 5 if bid == "FX1" else 6
            return [{"name":f"Param {i+1}","hw_idx":i,"enabled":True,"step":1.0} for i in range(n)]

        # 4. СБОРКА МАППИНГА С ЗАПОЛНЕНИЕМ ПУСТОТ (ДО 5 ИЛИ 6)
        n = 5 if bid == "FX1" else 6
        mapping = []
        
        for i in range(n):
            if i < len(data_list):
                p = data_list[i]
                p_obj = {
                    "name":    p.get("name", "Param"),
                    "hw_idx":  p.get("hw_idx", i),
                    "enabled": p.get("enabled", True),
                    "step":    p.get("step", 1.0),
                    "type":    p.get("type", "continuous"),
                    "unit":    p.get("unit", "%")
                }
                # Динамически пробрасываем всё остальное (scaling, values, hw_max и т.д.)
                for k, v in p.items():
                    if k not in p_obj:
                        # Тонкая настройка имен для UI компонентов (ParamRow)
                        if k == "disp_min": p_obj["min_disp"] = v
                        elif k == "disp_max": p_obj["max_disp"] = v
                        else: p_obj[k] = v
                
                # Поправка для шаговых параметров
                if p_obj["type"] == "steps_24":
                    p_obj["unit"] = "steps"
                    p_obj.setdefault("min_disp", -24)
                    p_obj.setdefault("max_disp", 24)
                    p_obj.setdefault("decimals", 0)

                mapping.append(p_obj)
            else:
                # Добиваем DUMMY ручками до нужного количества
                mapping.append({
                    "name":    f"Dummy {i+1}",
                    "hw_idx":  i,
                    "enabled": False,
                    "step":    1.0,
                    "type":    "continuous",
                    "unit":    "%"
                })
        
        return mapping

    def _render_params(self):
        """Рендерит или обновляет список параметров. Если модель не изменилась — только обновляет значения."""
        bid = self.selected_id
        b = self.blocks.get(bid)
        if not b: return
        
        # --- SMART UPDATE ---
        # Если мы отрисовываем тот же блок с той же моделью в том же режиме сервиса - НЕ пересоздаем виджеты, а просто плавно двигаем ползунки
        if (getattr(self, "_last_rendered_id", None) == bid 
            and getattr(self, "_last_rendered_model", None) == b.model_id
            and self._last_rendered_mapping == self.mapping_mode):
            for i in range(self.params_layout.count()):
                it = self.params_layout.itemAt(i)
                if it and isinstance(it.widget(), ParamRow):
                    row = it.widget()
                    d_idx = row.cfg.get("cache_idx")
                    if d_idx is None: d_idx = i
                    if 0 <= d_idx < len(b.params):
                        # Плавно подвозим к текущему значению из памяти
                        row.animate_to(b.params[d_idx])
            return

        # Если модель сменилась или другой блок - очищаем старое
        # Перед удалением явно гасим анимации и таймеры (защита от крашей)
        for i in range(self.params_layout.count()):
            it = self.params_layout.itemAt(i)
            if it and it.widget() and hasattr(it.widget(), "prepare_for_deletion"):
                it.widget().prepare_for_deletion()

        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.spacerItem(): pass

        cfg_list = self._get_mapping(self.selected_id)
        
        for i, c in enumerate(cfg_list):
            # В обычном режиме скрываем неактивные параметры
            if not self.mapping_mode and not c.get("enabled", True): continue
            
            d_idx = c.get("cache_idx")
            if d_idx is None: d_idx = i
            
            target_pct = b.params[d_idx] if 0 <= d_idx < len(b.params) else 50.0
            row_color = b.color()
            
            row = ParamRow(c, 50.0 if c.get("type") == "steps_24" else 0.0, mapping_mode=self.mapping_mode, color=row_color)
            row.value_changed.connect(lambda h_idx, val, cfg_obj=c, p_idx=i: self._on_param_changed(cfg_obj, val, p_idx))
            
            self.params_layout.addWidget(row)
            
            delay = i * 25
            row.show_animated(delay)
            QTimer.singleShot(delay + 60, lambda r=row, t=target_pct: self._safe_animate(r, t))

        self.params_layout.addStretch()
        
        # Запоминаем что отрисовали
        self._last_rendered_id = bid
        self._last_rendered_model = b.model_id
        self._last_rendered_mapping = self.mapping_mode

    def _safe_animate(self, row, target_pct):
        """Безопасно запускает анимацию, проверяя не удален ли виджет (защита от крашей)."""
        try:
            if row and row.parent() is not None:
                row.animate_to(target_pct, duration=250)
        except RuntimeError:
            pass # Объект уже удален, ну и хрен с ним

    def _on_param_changed(self, cfg, pct, p_idx):
        b = self.blocks[self.selected_id]
        hw_idx = cfg.get("hw_idx")
        mapping = self._get_mapping(self.selected_id)
        
        # Ищем индекс в текущем маппинге
        d_idx = cfg.get("cache_idx")
        if d_idx is None:
            for i, c in enumerate(mapping):
                if c.get("hw_idx") == hw_idx:
                    d_idx = i
                    break
        if d_idx is None: d_idx = -1
        
        if 0 <= d_idx < len(b.params):
            b.params[d_idx] = pct

        # ── Тротлинг MIDI отправки (живой 0x63) ──
        THROTTLE_MS = 50
        
        if not hasattr(self, '_param_throttle'):
            self._param_throttle = {}  # key -> QTimer
        
        bid = self.selected_id
        throttle_key = f"{bid}_{hw_idx}"
        
        # Сохраняем последнее значение для финальной досылки
        if not hasattr(self, '_param_pending'):
            self._param_pending = {}
        self._param_pending[throttle_key] = (bid, cfg, pct)
        
        if throttle_key in self._param_throttle:
            # Перевзводим таймер коммита (ползунок ещё крутится)
            if hasattr(self, '_commit_timer') and self._commit_timer.isActive():
                self._commit_timer.start(300)
            return
        
        # Первый вызов — шлём сразу и запускаем таймер блокировки
        self._log(f"[UI] {bid} P{hw_idx:02X} → {pct:.1f}% (CacheIdx: {d_idx})")
        self._send_param(bid, cfg, pct)
        
        timer = QTimer(self)
        timer.setSingleShot(True)
        self._param_throttle[throttle_key] = timer
        
        def _on_throttle_expire():
            self._param_throttle.pop(throttle_key, None)
            pending = self._param_pending.pop(throttle_key, None)
            if pending:
                p_bid, p_cfg, p_pct = pending
                self._log(f"[UI] {p_bid} P{p_cfg.get('hw_idx', 0):02X} → {p_pct:.1f}% (throttled)")
                self._send_param(p_bid, p_cfg, p_pct)
        
        timer.timeout.connect(_on_throttle_expire)
        timer.start(THROTTLE_MS)
        
        # ── Отложенный коммит (62→задержка→63) после idle 300мс ──
        if not hasattr(self, '_commit_timer'):
            self._commit_timer = QTimer(self)
            self._commit_timer.setSingleShot(True)
            self._commit_timer.timeout.connect(self._do_deferred_commit)
        self._commit_timer.start(300)

    def _do_deferred_commit(self):
        """Отложенный коммит: 62→250ms→63 на все слоты последнего параметра."""
        info = getattr(self, '_last_commit_info', None)
        if not info or not self.midi_out:
            return
        
        def _commit_thread():
            import time
            slots = info["slots"]
            hw_idx = info["hw_idx"]
            val = info["val"]
            hi_res = info["hi_res"]
            bid = info["bid"]
            
            # Шаг 1: 0x62 на все слоты
            for s in slots:
                data_62 = self._make_sysex(s, hw_idx, val, hi_res=hi_res, cmd=0x62)
                self._send_raw(data_62)
            
            # Пауза 250мс
            time.sleep(0.250)
            
            # Шаг 2: 0x63 на все слоты
            for s in slots:
                data_63 = self._make_sysex(s, hw_idx, val, hi_res=hi_res, cmd=0x63)
                self._send_raw(data_63)
            
            self._log(f"✓ COMMIT {bid} P{hw_idx:02X} = {val} [62→250ms→63]")
        
        __import__('threading').Thread(target=_commit_thread, daemon=True).start()

    def _on_add_param(self):
        self._log("Добавлен новый параметр (не сохранён)")

    def _save_mapping(self):
        b = self.blocks[self.selected_id]
        model_hex = f"{b.model_id:02X}"
        key = f"{model_hex}_{self.selected_id}"
        mapping = []
        for i in range(self.params_layout.count()):
            w = self.params_layout.itemAt(i).widget()
            if isinstance(w, ParamRow):
                mapping.append(w.cfg.copy())
        if mapping:
            self.ui_mappings[key] = mapping
            path = os.path.join(SCRIPT_DIR, "ui_mappings_v2.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.ui_mappings, f, indent=2, ensure_ascii=False)
            self._log(f"✅ Маппинг сохранён: {key}")

    # ── пресеты и дамп ─────────────────────────────

    def _update_preset_ui(self, pc, name=None):
        """Централизованный метод обновления UI пресетов и состояния DI Mode."""
        self.current_preset_num = pc
        if name: self.preset_name = name
        
        bank = (pc // 4) + 1
        sub  = ["A","B","C","D"][pc % 4]
        addr_str = f"{bank:02d}{sub}"
        
        if hasattr(self, "btn_di"):
            if pc == self.di_preset:
                self.btn_di.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; border: 2px solid white; border-radius: 4px;")
                self.btn_di.setText("DI ON")
                display_name = f"{addr_str} - {name} (DI MODE)" if name else f"{addr_str} (DI MODE)"
            else:
                self.btn_di.setStyleSheet("background-color: #333; color: #888; font-weight: bold; border: 1px solid #555; border-radius: 4px;")
                self.btn_di.setText("DI MODE")
                display_name = f"{addr_str} - {name}" if name else addr_str
                
            self.preset_lbl.setText(f"PRESET: {display_name}")

        for i in range(self.preset_list.count()):
            if self.preset_list.item(i).data(Qt.ItemDataRole.UserRole) == pc:
                self.preset_list.blockSignals(True)
                self.preset_list.setCurrentRow(i)
                self.preset_list.blockSignals(False)
                break

    def _on_got_preset_no(self, pc):
        """Получили номер пресета от железки — обновляем UI и ставим в очередь запрос дампа."""
        self._update_preset_ui(pc)
        self._pending_preset = pc
        # Если пришло подтверждение от проца, значит он «очухался»,
        # но дадим ему ещё 300мс на инициализацию эффектов.
        # Это сбросит таймер от _on_prog_chg, если он работал.
        self._dump_debounce.start(300)
        self._log(f"Пресет подтверждён: #{pc}. Дамп через 300мс...")

    def _on_dump_raw(self, raw):
        """Прямой обработчик дампов приходящий из фонового потока."""
        if getattr(self, "_is_warming_up", False):
            return # Игнорируем эхо при "прогреве", чтобы не ломать UI
            
        if len(raw) < 8 or raw[0] != 0xF0:
            return
        cmd = raw[6]
        
        # Обработка ожиданий (Save/DI)
        if getattr(self, "_waiting_for_save_dump", False):
            self._waiting_for_save_dump = False
            self._do_save_to_processor(raw)
            return

        if getattr(self, "_waiting_for_di_dump", False):
            safe_raw = list(raw)
            if len(safe_raw) > 10:
                safe_raw[8], safe_raw[9], safe_raw[10] = 0x7F, 0x7F, 0x00
            self.saved_edit_buffer_for_di = safe_raw
            self._waiting_for_di_dump = False
            self._log("[DI] Safe Edit Buffer получен.")
            if self.midi_out:
                self.midi_out.send(mido.Message('program_change', program=self.di_preset))
                self._send_usb_mute(True)
            return

        self._parse_dump(raw)

    def _on_prog_chg(self, pc):
        """Аппаратная смена пресета (MIDI C0 XX) — обновляем UI и заводим таймер страховки."""
        self._sync_start_time = time.time()
        self._update_preset_ui(pc)
        self._log(f"Пресет изменён: {self.preset_lbl.text().split(': ')[-1]} (#{pc}) [Wait for 0x62 or fallback]")
        self._pending_preset = pc
        self._jump_to_amp_on_dump = True
        
        # Показываем прелоадер на панели параметров
        self._show_params_preloader(True)

        # Заводим таймер на 1 секунду. Если прилетит ответ 0x62 раньше — таймер перевзведётся на 300мс.
        self._dump_debounce.start(1000)

    def _parse_dump(self, raw):
        if getattr(self, "_sync_mode", False):
            preset_name = "".join(chr(c) for c in raw[12:28] if 32 <= c <= 126).strip()
            if not preset_name:
                preset_name = "".join(chr(c) for c in raw[10:26] if 32 <= c <= 126).strip()
            
            idx = self._syncing_preset_idx
            bank = (idx // 4) + 1
            sub  = ["A","B","C","D"][idx % 4]
            it = self.preset_list.item(idx)
            if it:
                it.setText(f"{bank:02d}{sub} - {preset_name}")
            
            self.preset_cache[str(idx)] = preset_name
            
            self._syncing_preset_idx += 1
            self._update_sync_ui()
            
            if self._syncing_preset_idx < 128:
                QTimer.singleShot(20, self._fetch_next_preset_name)
            else:
                self._sync_mode = False
                self._save_preset_cache()
                self._update_sync_ui()
                self._log("✅ Синхронизация пресетов завершена.")
            return

        data = parse_full_dump(raw)
        if not data:
            self._dump_retry_count = getattr(self, "_dump_retry_count", 0) + 1
            if self._dump_retry_count <= 3:
                self._log(f"⚠️ Дамп не распознан (битый), повтор ({self._dump_retry_count}/3) через 500мс...")
                QTimer.singleShot(500, self._debounced_dump)
            else:
                self._log("❌ Дамп безнадёжно битый после 3 попыток. Проц не отвечает нормально.")
                self._dump_retry_count = 0
            return
            
        self._dump_retry_count = 0  # При успешном парсинге сбрасываем счётчик
        self.preset_name = data["preset_name"]
        self._update_preset_ui(self.current_preset_num, name=self.preset_name)
        
        self.preset_cache[str(self.current_preset_num)] = self.preset_name
        self._save_preset_cache()

        # Gate
        gm = data["gate_mode"]
        self.blocks["GATE"].is_on  = True
        self.blocks["GATE"].params = [gm, data["gate_thresh"], data["gate_decay"]]

        # Vol
        self.blocks["VOL"].is_on = True
        self.blocks["VOL"].pre_post = 1 if data["vol_post"] else 0
        self.blocks["VOL"].params   = [data["vol_min"], data["vol_max"]]

        # Wah
        bw = self.blocks["WAH"]
        wah_id = data["wah_id"]
        bw.model_id = wah_id
        bw.is_on = data["wah_on"]
        bw.name  = data["wah_name"]
        self.blocks["WAH"].params = [data["wah_pos"]]

        # FX1-3 + REV
        for bid in ["FX1","FX2","FX3","REV"]:
            fx = data["fx"][bid]
            b  = self.blocks[bid]
            b.model_id = fx["model_id"]
            b.name     = fx["name"] if fx["name"] != "NONE" else "NONE"
            b.is_on    = fx["is_on"]
            b.pre_post = 1 if fx["is_post"] else 0
            b.params   = fx["params"]
            b.category = self._find_cat(b.name)
            if bid == "REV" and b.category == "None":
                b.category = "Reverb"

        # Amp
        ba = self.blocks["AMP"]
        ba.model_id = data["amp_id"]
        ba.extra   = {"amp_id": data["amp_id"]}
        ba.name    = AMP_NAMES.get(data["amp_id"], f"Amp 0x{data['amp_id']:02X}")
        ba.params  = list(data["amp_params"].values())

        # Cab
        bc = self.blocks["CAB"]
        cid = data["cab_id"]
        if cid == 0x00:
            cid = MATCHED_CABS.get(data["amp_id"], 0x00)
            
        bc.model_id = cid
        bc.name   = CAB_NAMES.get(cid, f"Cab 0x{cid:02X}")
        mic_pct = (data["mic_id"] / 7.0) * 100.0 if data["mic_id"] <= 7 else 0.0
        bc.params = [mic_pct, data["er_level"]]

        # Дамп и так читает все параметры из памяти, но Pitch Glide (0x2F) 
        # прячет их из-за связи с педалью экспрессии.
        # Поэтому запускаем "умный" опрос, который дернет данные ТОЛЬКО для Pitch Glide,
        # чтобы избежать DDoS'а процессора.
        if self.midi_out:
            QTimer.singleShot(600, lambda: self._query_all_fx_blocks())

        self._refresh_chain()
        if getattr(self, "_jump_to_amp_on_dump", True):
            self._select_block("AMP")  # При смене пресета AMP — единственный блок, который всегда грузится корректно
            self._jump_to_amp_on_dump = False
        else:
            self._select_block(self.selected_id)
        self._log(f"✅ Dump recognized: {self.preset_name}")
        
        if getattr(self, "sync_on_launch", False) and not getattr(self, "_initial_sync_done", False):
            self._initial_sync_done = True
            QTimer.singleShot(500, self._start_preset_sync)

    def _start_preset_sync(self):
        self._sync_mode = True
        self._syncing_preset_idx = 0
        self._log("⏳ Background sync of 128 presets started...")
        self._update_sync_ui()
        self._fetch_next_preset_name()

    def _fetch_next_preset_name(self):
        if not getattr(self, "_sync_mode", False): return
        self._request_preset_dump(self._syncing_preset_idx)

    def _update_sync_ui(self):
        if hasattr(self, "preset_list"):
            if getattr(self, "_sync_mode", False):
                if not hasattr(self, "list_blur"):
                    self.list_blur = QGraphicsBlurEffect()
                    self.list_blur.setBlurRadius(4)
                    self.preset_list.setGraphicsEffect(self.list_blur)
                self.list_blur.setEnabled(True)
                
                if not hasattr(self, "sync_overlay"):
                    self.sync_overlay = QLabel(self.preset_list.parentWidget())
                    self.sync_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.sync_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                
                pct = int((self._syncing_preset_idx / 128.0) * 100)
                spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                spin = spinners[self._syncing_preset_idx % len(spinners)]
                self.sync_overlay.setText(f"{spin}\nLOAD\n{pct}%")
                self.sync_overlay.setStyleSheet("color: #d6923c; font-size: 14pt; font-weight: bold; background: rgba(0,0,0,120); border-radius: 4px;")
                self.sync_overlay.setGeometry(self.preset_list.geometry())
                self.sync_overlay.raise_()
                self.sync_overlay.show()
                
                if hasattr(self, "lbl_p"):
                    self.lbl_p.setText(f"PRESETS [ {pct}% ]")
                    self.lbl_p.setStyleSheet("color:#d6923c; font-size:8pt; font-weight:bold;")
            else:
                if hasattr(self, "list_blur"):
                    self.list_blur.setEnabled(False)
                if hasattr(self, "sync_overlay"):
                    self.sync_overlay.hide()
                if hasattr(self, "lbl_p"):
                    self.lbl_p.setText("PRESETS")
                    self.lbl_p.setStyleSheet("color:#666; font-size:8pt; font-weight:bold;")

    def _get_cache_idx(self, bid, hw_idx, num_params):
        if hw_idx is None: return 0
        is_6_slot = bid in ("FX2", "FX3", "REV")
        offset = 1 if (is_6_slot and num_params == 5) else 0
        return (hw_idx - 1) + offset

    def _update_slider(self, hw_idx, pct):
        """Обновляет слайдер с нужным hw_idx — плавно, без эмиссии сигнала."""
        for i in range(self.params_layout.count()):
            it = self.params_layout.itemAt(i)
            if it and isinstance(it.widget(), ParamRow):
                row = it.widget()
                if row.cfg.get("hw_idx") == hw_idx:
                    if hasattr(row, 'slider') and row.slider and row.slider.isSliderDown():
                        return
                    if hasattr(row, '_last_user_edit') and (time.time() - row._last_user_edit) < 0.4:
                        return
                        
                    row.animate_to(pct)
                    break

    def _update_block_state_ui(self, bid):
        """Обновляет визуальное состояние кнопок On/Off и Pre/Post для блока."""
        if bid not in self.blocks: return
        b = self.blocks[bid]
        
        if hasattr(b, "btn_on") and b.btn_on:
            b.btn_on.blockSignals(True)
            b.btn_on.setChecked(b.is_on)
            b.btn_on.blockSignals(False)
            
        if hasattr(b, "btn_pre") and b.btn_pre:
            b.btn_pre.blockSignals(True)
            b.btn_pre.setChecked(b.pre_post == 1)
            b.btn_pre.blockSignals(False)
            
        if bid == self.selected_id:
            if hasattr(self, "btn_on"):
                self.btn_on.blockSignals(True)
                self.btn_on.setChecked(b.is_on)
                self.btn_on.setText("ON" if b.is_on else "OFF")
                self.btn_on.blockSignals(False)
            if hasattr(self, "btn_pp"):
                self.btn_pp.blockSignals(True)
                self.btn_pp.setChecked(b.pre_post == 1)
                self.btn_pp.setText("POST" if b.pre_post == 1 else "PRE")
                self.btn_pp.blockSignals(False)

        # Обновляем стиль кнопки в сигнальной цепи (чтобы перерисовывался On/Off стейт)
        if hasattr(self, "chain_panel"):
            for btn in self.chain_panel._buttons:
                if btn.state.block_id == bid:
                    btn._refresh_style()
                    btn.update()

    def _query_block_params(self, bid):
        """Запрашивает значения ручек для конкретного блока. 
        Запускается в отдельном потоке с блокировкой.
        """
        if not self.midi_out: return
        
        def _target():
            import time
            with self._midi_survey_lock:
                self._is_surveying = True
                b = self.blocks.get(bid)
                if not b: 
                    self._is_surveying = False
                    return
                
                # q_id: для FX и AMP добавляем 0x20, для слота 0x02 (GATE/CAB/...) оставляем как есть
                q_id = b.slot_id
                if q_id != 0x02:
                    q_id += 0x20
                
                # Получаем список индексов параметров из маппинга блока
                mapping = self._get_mapping(bid)
                hw_indices = []
                for p_cfg in mapping:
                    hw = p_cfg.get("hw_idx")
                    if hw is not None:
                        hw_indices.append(hw)

                if not hw_indices:
                    self._is_surveying = False
                    return
                
                self._log(f"🛰 Syncing {bid} (Slot 0x{q_id:02X})...")
                delay = 0.025 if bid == "REV" else 0.020

                for p_idx in hw_indices:
                    # F0 00 01 0C 14 00 60 00 SLOT PARAM F7
                    data = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x60, 0x00, q_id, p_idx]
                    self._send_raw(data)
                    time.sleep(delay)
                
                self._is_surveying = False
                self._log(f"✅ {bid} synced")

        __import__('threading').Thread(target=_target, daemon=True).start()

    def _query_all_fx_blocks(self):
        """Полная синхронизация всех FX слотов (последовательно в одном потоке)."""
        if not self.midi_out: return
        
        def _target():
            import time
            start_t = time.time()
            if getattr(self, "_midi_survey_lock", None) is None:
                self._midi_survey_lock = __import__('threading').Lock()
                
            with self._midi_survey_lock:
                self._is_surveying = True
                pg_found = False
                for bid in ["FX1", "FX2", "FX3"]:
                    if self.blocks[bid].model_id == 0x2F:
                        if not pg_found:
                            self._log("🛰 Pitch Glide detected! Polling parameters...")
                            pg_found = True
                        self._do_query_block_sync(bid)
                        time.sleep(0.010)
                
                # Дополнительно опрашиваем статус головы (AMP)
                self._send_raw([0x00, 0x01, 0x0C, 0x14, 0x00, 0x60, 0x00, 0x02, 0x14])
                
                if not pg_found:
                    self._log("⏩ Background poll not required (no Pitch Glide)")
                
                elapsed = time.time() - (self._sync_start_time if self._sync_start_time > 0 else start_t)
                self._sync_start_time = 0
                self._is_surveying = False
                self._log(f"✅ Full sync completed in {elapsed:.2f} sec")
                
                # Прячем прелоадер
                self._show_params_preloader(False)

        __import__('threading').Thread(target=_target, daemon=True).start()

    def _show_params_preloader(self, show=True):
        """Показывает/скрывает локальный прелоадер поверх панели параметров."""
        if not hasattr(self, "params_panel"): return
        
        if show:
            if not hasattr(self, "params_overlay"):
                self.params_overlay = QLabel(self.params_panel)
                self.params_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.params_overlay.setStyleSheet("""
                    color: #d6923c; 
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, 
                                               stop:0 rgba(0,0,0,160), 
                                               stop:0.7 rgba(0,0,0,80), 
                                               stop:1 rgba(0,0,0,0));
                    font-size: 32pt; 
                    border: none;
                """)
                self.params_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                
                # Создаем эффект блюра именно ДЛЯ КАРТОЧКИ
                self.params_overlay_blur = QGraphicsBlurEffect(self.params_overlay)
                self.params_overlay.setGraphicsEffect(self.params_overlay_blur)
            
            self._update_params_spinner()
            self.params_overlay.show()
            self.params_overlay.raise_()
            
            # Анимация "фокусировки" (размытие -> четкость)
            self.params_overlay_blur.setEnabled(True)
            self._blur_anim = QPropertyAnimation(self.params_overlay_blur, b"blurRadius")
            self._blur_anim.setDuration(400)
            self._blur_anim.setStartValue(15.0)
            self._blur_anim.setEndValue(0.0)
            self._blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._blur_anim.start()
            
            if not hasattr(self, "_spinner_timer"):
                self._spinner_timer = QTimer(self)
                self._spinner_timer.timeout.connect(self._update_params_spinner)
            self._spinner_idx = 0
            self._spinner_timer.start(80)
        else:
            if hasattr(self, "params_overlay"):
                # Уходим тоже красиво через прозрачность или просто прячем
                self.params_overlay.hide()
            if hasattr(self, "_spinner_timer"):
                self._spinner_timer.stop()

    def _update_params_spinner(self):
        """Анимация спиннера и обновление геометрии (25% по центру)."""
        if not hasattr(self, "params_overlay") or not self.params_overlay.isVisible(): return
        
        # Анимация текста
        spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_idx = (self._spinner_idx + 1) % len(spinners)
        self.params_overlay.setText(spinners[self._spinner_idx])
        
        # Geometry calculation (25% of panel, but at least 120px)
        if hasattr(self, "params_panel"):
            pr = self.params_panel.rect()
            w = max(120, int(pr.width() * 0.25))
            h = max(120, int(pr.height() * 0.25))
            # Make square if height allows
            if h > w: h = w
            
            x = (pr.width() - w) // 2
            # Offset to upper middle (approx 1/4 of height from top)
            y = int(pr.height() * 0.25) - (h // 2)
            if y < 20: y = 20 # So it doesn't touch the very edge
            self.params_overlay.setGeometry(x, y, w, h)
    def _find_cat(self, name):
        """Intelligent category search by effect name.
        Case-insensitive, ignoring extra characters.
        """
        if not name or name == "NONE":
            return "None"
            
        clean_name = name.strip().lower().replace("'", "").replace("-", " ")
        
        for cat, names in self.cats_data.items():
            for n in names:
                clean_n = n.strip().lower().replace("'", "").replace("-", " ")
                if clean_name == clean_n or clean_name.startswith(clean_n):
                    return cat
        return "None"

    def _log(self, msg):
        """Thread-safe logging wrapper."""
        self._sig_log.emit(msg)

    def _log_ui(self, msg):
        """UI update method, called only via signal."""
        if getattr(self, "log_level", 1) == 0: return # Полная тишина
        
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(msg)
        try:
            if getattr(self, "log_level", 1) >= 1:
                print(f"[HD300] {msg}")
        except UnicodeEncodeError:
            if getattr(self, "log_level", 1) >= 1:
                print(f"[HD300] {msg}".encode("ascii", "replace").decode("ascii"))

    def _open_settings_dialog(self):
        dlg = SettingsDialog(
            self,
            sync_on_launch=getattr(self, "sync_on_launch", True),
            black_mode=getattr(self, "black_mode", False),
            load_edit_buffer=getattr(self, "load_edit_buffer", True),
            experimental_free_routing=getattr(self, "experimental_free_routing", False),
            di_preset=getattr(self, "di_preset", 124),
        )
        
        def on_sync(s):
            self.sync_on_launch = (s == 2)
            self._save_settings()
            
        def on_black(s):
            self.black_mode = (s == 2)
            self._save_settings()
            self._apply_styles()
            self._select_block(self.selected_id)
            self._render_params()
            
        def on_buf(s):
            self.load_edit_buffer = (s == 2)
            self._save_settings()

        def on_free(s):
            self.experimental_free_routing = (s == 2)
            if hasattr(self, "chain_panel"):
                self.chain_panel.experimental_routing = self.experimental_free_routing
            self._save_settings()
            self._refresh_chain()
            
        def on_di_val(v):
            self.di_preset = v - 1
            self._save_settings()
            self._update_preset_ui(self.current_preset_num)
            
        dlg.cb_sync.stateChanged.connect(on_sync)
        dlg.cb_black.stateChanged.connect(on_black)
        dlg.cb_buf.stateChanged.connect(on_buf)
        dlg.cb_free.stateChanged.connect(on_free)
        dlg.sb_di.valueChanged.connect(on_di_val)
        
        dlg.exec()

    # ── UI BUILDERS ────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── Top bar ──
        top = QFrame()
        top.setFixedHeight(52)
        top.setObjectName("topBar")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(14, 0, 14, 2)
        top_lay.setSpacing(12)

        title = QLabel("POD HD300")
        title.setStyleSheet("background: transparent; font-size:15pt; font-weight:bold; color:#d6923c;")
        top_lay.addWidget(title)

        self.preset_lbl = QLabel("PRESET: ---")
        self.preset_lbl.setStyleSheet("background: transparent; font-size:13pt; color:#ddd;")
        top_lay.addWidget(self.preset_lbl)
        top_lay.addStretch()

        self.conn_lbl = QLabel("○ DISCONNECTED")
        self.conn_lbl.setStyleSheet("background: transparent; color:#e74c3c; font-weight:bold; font-size:9pt;")
        top_lay.addWidget(self.conn_lbl)

        self.btn_connect = QPushButton("⚡ Connect")
        self.btn_connect.clicked.connect(self._auto_connect)
        top_lay.addWidget(self.btn_connect)

        self.btn_di = DiModeButton("DI MODE")
        self.btn_di.setFixedWidth(100)
        self.btn_di.setStyleSheet("background-color: #333; color: #888; font-weight: bold; border: 1px solid #555; border-radius: 4px;")
        self.btn_di.setToolTip("Left Click: Toggle DI (32A + Mute), Right Click: Unmute (Failsafe)")
        self.btn_di.clicked.connect(self._toggle_di_mode)
        self.btn_di.rightClicked.connect(self._force_unmute_usb)
        top_lay.addWidget(self.btn_di)

        self.btn_dump = QPushButton("↻ Dump")
        self.btn_dump.clicked.connect(self._request_dump)
        top_lay.addWidget(self.btn_dump)

        self.btn_mapping = QPushButton("🔧 Mapping Mode")
        self.btn_mapping.setCheckable(True)
        self.btn_mapping.toggled.connect(self._on_mapping_toggle)
        top_lay.addWidget(self.btn_mapping)

        self.btn_settings = QPushButton("⚙ Settings")
        self.btn_settings.clicked.connect(self._open_settings_dialog)
        top_lay.addWidget(self.btn_settings)

        # ── Window Frame ──
        if sys.platform == "win32":
            try:
                QTimer.singleShot(100, self._apply_dwm_dark)
            except Exception as e:
                pass
        
        main.addWidget(top)

        # ── Signal Chain ──
        self.chain_panel = SignalChainPanel()
        self.chain_panel.experimental_routing = getattr(self, "experimental_free_routing", False)
        self.chain_panel.block_clicked.connect(self._select_block)
        self.chain_panel.block_right_clicked.connect(self._on_block_right_click)
        self.chain_panel.pre_post_changed.connect(self._on_prepost_drop)
        self.chain_panel.block_swap_requested.connect(self._on_swap_requested)
        self.chain_panel.block_unconditional_swap.connect(self._on_unconditional_swap)
        main.addWidget(self.chain_panel)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2a2d32;")
        main.addWidget(sep)

        # ── Main content splitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(2)
        main.addWidget(splitter, 1)

        # Preset list
        self.side_presets = QFrame()
        self.side_presets.setObjectName("sidePanel")
        self.side_presets.setFixedWidth(200)
        ll = QVBoxLayout(self.side_presets)
        ll.setContentsMargins(8, 8, 8, 8)
        
        hdr_lay = QHBoxLayout()
        self.lbl_p = QLabel("PRESETS")
        self.lbl_p.setStyleSheet("color:#666; font-size:8pt; font-weight:bold;")
        hdr_lay.addWidget(self.lbl_p)
        
        self.btn_sync_all = QPushButton("↻ Receive All")
        self.btn_sync_all.setToolTip("Download all 128 preset names from the processor")
        self.btn_sync_all.setFixedHeight(22)
        self.btn_sync_all.setStyleSheet("background: #252830; font-size: 7pt; padding: 2px 6px; border-radius: 4px;")
        self.btn_sync_all.clicked.connect(self._start_preset_sync)
        hdr_lay.addWidget(self.btn_sync_all)

        self.btn_send_active = QPushButton("▲ Send Active")
        self.btn_send_active.setToolTip("Save current preset to the active slot on the processor")
        self.btn_send_active.setFixedHeight(22)
        self.btn_send_active.setStyleSheet("background: #252830; font-size: 7pt; padding: 2px 6px; border-radius: 4px;")
        self.btn_send_active.clicked.connect(self._save_active_preset)
        hdr_lay.addWidget(self.btn_send_active)
        ll.addLayout(hdr_lay)
        
        self.preset_list = QListWidget()
        self.preset_list.setObjectName("presetList")
        self.preset_list.setAlternatingRowColors(True)
        self.preset_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.preset_list.customContextMenuRequested.connect(self._on_preset_right_click)
        for p in range(128):
            bank = (p // 4) + 1
            sub  = ["A","B","C","D"][p % 4]
            name = self.preset_cache.get(str(p))
            it = QListWidgetItem(f"{bank:02d}{sub} - {name}" if name else f"{bank:02d}{sub}")
            it.setData(Qt.ItemDataRole.UserRole, p)
            self.preset_list.addItem(it)
        self.preset_list.itemDoubleClicked.connect(self._on_preset_dclick)
        ll.addWidget(self.preset_list, 1)
        splitter.addWidget(self.side_presets)

        # Category + Model lists
        self.side_models = QFrame()
        self.side_models.setObjectName("sidePanel")
        self.side_models.setFixedWidth(365)
        ml = QVBoxLayout(self.side_models)
        ml.setContentsMargins(8, 8, 8, 8)
        ml.setSpacing(6)

        lbl_cat = QLabel("DEVICE TYPE")
        lbl_cat.setStyleSheet("color:#666; font-size:8pt; font-weight:bold;")
        ml.addWidget(lbl_cat)

        browser_row = QHBoxLayout()
        self.cat_list = QListWidget()
        self.cat_list.setObjectName("catList")
        self.cat_list.addItems(sorted(self.cats_data.keys()))
        self.cat_list.setMaximumWidth(155)
        self.cat_list.itemClicked.connect(self._on_cat_click)
        browser_row.addWidget(self.cat_list)

        mod_col = QVBoxLayout()
        lbl_mod = QLabel("MODULE NAME")
        lbl_mod.setStyleSheet("color:#666; font-size:8pt; font-weight:bold;")
        mod_col.addWidget(lbl_mod)
        self.model_list = QListWidget()
        self.model_list.setObjectName("modelList")
        self.model_list.itemClicked.connect(self._on_model_click)
        mod_col.addWidget(self.model_list)
        browser_row.addLayout(mod_col)
        ml.addLayout(browser_row, 1)
        splitter.addWidget(self.side_models)

        # Module Settings panel
        right = QFrame()
        right.setObjectName("settingsPanel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 8, 12, 8)
        rl.setSpacing(8)

        # header row
        hdr = QHBoxLayout()
        self.block_icon = QLabel()
        self.block_icon.setFixedSize(36, 36)
        self.block_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.block_icon.setStyleSheet("background: transparent;")
        hdr.addWidget(self.block_icon)
        self.block_title = QLabel("  SELECT A BLOCK")
        self.block_title.setStyleSheet("font-size:13pt; font-weight:bold; color:#eee;")
        hdr.addWidget(self.block_title, 1)

        self.btn_on = QPushButton("ON")
        self.btn_on.setCheckable(True)
        self.btn_on.setFixedWidth(60)
        self.btn_on.setChecked(True)
        self.btn_on.toggled.connect(self._on_toggle_on)
        hdr.addWidget(self.btn_on)

        self.btn_save_cfg = QPushButton("SAVE CFG")
        self.btn_save_cfg.setFixedWidth(80)
        self.btn_save_cfg.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_save_cfg.setVisible(False)
        self.btn_save_cfg.clicked.connect(self._save_mapping)
        hdr.addWidget(self.btn_save_cfg)

        self.btn_clear_cache = QPushButton("CLR CACHE")
        self.btn_clear_cache.setFixedWidth(85)
        self.btn_clear_cache.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_clear_cache.setVisible(False)
        self.btn_clear_cache.clicked.connect(self._clear_preset_cache)
        hdr.addWidget(self.btn_clear_cache)

        self.btn_pp = QPushButton("PRE")
        self.btn_pp.setCheckable(True)
        self.btn_pp.setFixedWidth(60)
        self.btn_pp.toggled.connect(self._on_toggle_pp)
        hdr.addWidget(self.btn_pp)
        rl.addLayout(hdr)

        # scroll for params
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        params_w = QWidget()
        self.params_layout = QVBoxLayout(params_w)
        self.params_layout.setContentsMargins(0, 4, 0, 4)
        self.params_layout.setSpacing(4)
        scroll.setWidget(params_w)
        rl.addWidget(scroll, 1)
        self.params_panel = right
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)

        # ── Status bar ──
        self.status_lbl = QLabel("Ready.")
        self.status_lbl.setFixedHeight(22)
        self.status_lbl.setStyleSheet(
            "background:#111; color:#666; padding: 2px 12px; font-size:8pt;"
        )
        main.addWidget(self.status_lbl)

    def _apply_styles(self):
        hm = getattr(self, "black_mode", False)
        rb = getattr(self, "remove_borders", True)
        
        bg_main = "#000000" if hm else "#1a1c1f"
        bg_top  = "#000000" if hm else "#111316"
        bg_side = "#000000" if hm else "#16181b"
        bg_chain= "#000000" if hm else "#111316"
        border  = "#2a2d32"
        bg_alt  = "#111111" if hm else "#1e2024"
        bg_btn_h= "#333333" if hm else "#2e3340"
        
        border_r = "border-right: none;" if rb else f"border-right: 1px solid {border};"
        spl_bg = "transparent" if rb else "#252830"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {bg_main};
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10pt;
            }}
            #topBar {{
                background: {bg_top};
                border-bottom: 1px solid {border};
            }}
            #sidePanel {{
                background: {bg_side};
                {border_r}
            }}
            #settingsPanel {{
                background: {bg_main};
            }}
            #chainPanel {{
                background: {bg_chain};
                border-bottom: 1px solid {border};
            }}
            QLabel, QCheckBox {{
                background: transparent;
            }}
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background: rgba(214, 146, 60, 50);
                color: #d6923c;
                border-left: 3px solid #d6923c;
                font-weight: bold;
            }}
            QListWidget::item:selected:!active {{
                background: rgba(214, 146, 60, 25);
            }}
            QListWidget::item:hover {{
                background: rgba(255, 255, 255, 10);
            }}
            QListWidget::item:alternate {{
                background: {bg_alt};
            }}
            QPushButton {{
                background: #252830;
                border: 1px solid #333840;
                border-radius: 6px;
                padding: 5px 12px;
                color: #ccc;
            }}
            QPushButton:hover {{
                background: {bg_btn_h};
                border-color: #d6923c;
            }}
            QPushButton:checked {{
                background: rgba(214, 146, 60, 40);
                border-color: #d6923c;
                color: #d6923c;
            }}
            QSlider::groove:horizontal {{
                background: #252830;
                height: 8px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #d6923c;
                width: 14px;
                height: 14px;
                margin: -3px 0;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: #d6923c;
                border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: #252830;
                border-radius: 2px;
            }}
            QScrollBar:vertical {{
                background: {bg_side};
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: #333;
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QLineEdit, QSpinBox, QDoubleSpinBox {{
                background: #252830;
                border: 1px solid #333840;
                border-radius: 4px;
                padding: 2px 6px;
                color: #ddd;
            }}
            QSplitter::handle {{
                background: {spl_bg};
            }}
        """)
        # On/Off button - green when active
        self.btn_on.setStyleSheet("""
            QPushButton { background:#1a3a1a; color:#4caf50; border:1px solid #2e7d32; }
            QPushButton:checked { background:#2e7d32; color: white; }
            QPushButton:!checked { background:#3a1a1a; color:#e53935; border:1px solid #b71c1c; }
        """)
        self.btn_pp.setStyleSheet("""
            QPushButton { background:#1a2a3a; color:#2196f3; border:1px solid #1565c0; }
            QPushButton:checked { background:#b45a10; color:white; border:1px solid #e65c00; }
        """)

    def _apply_dwm_dark(self):
        try:
            hwnd = self.winId().__int__()
            
            dark = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            
            backdrop = ctypes.c_int(1) 
            dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
            
            color = ctypes.c_int(0x00000000) 
            dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))
            
            text_color = ctypes.c_int(0x00AAAAAA)
            dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))

        except Exception as e:
            print(f"[DEBUG] DWM error: {e}")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if hasattr(self, "title_bar"):
                self.title_bar.update_max_icon()
        super().changeEvent(event)

    def _update_list_accent(self, widget, col):
        if not widget: return
        try:
            r = int(col[1:3], 16)
            g = int(col[3:5], 16)
            bl = int(col[5:7], 16)
            widget.setStyleSheet(f"""
                QListWidget::item:selected {{
                    background: rgba({r}, {g}, {bl}, 45);
                    color: {col};
                    border-left: 3px solid {col};
                    font-weight: bold;
                }}
                QListWidget::item:selected:!active {{
                    background: rgba({r}, {g}, {bl}, 20);
                }}
                QListWidget::item:hover {{
                    background: rgba(255, 255, 255, 10);
                }}
            """)
        except: pass

    def _sync_browser_to_block(self, b):
        """Selects current category and model in the effect browser."""
        if not hasattr(self, "cat_list") or not hasattr(self, "model_list"):
            return
            
        self.cat_list.blockSignals(True)
        self.model_list.blockSignals(True)
        try:
            # 1. Находим и выделяем категорию
            target_cat = b.category
            found_cat = False
            for i in range(self.cat_list.count()):
                it = self.cat_list.item(i)
                if it.text() == target_cat:
                    self.cat_list.setCurrentItem(it)
                    # Наполняем список моделей (это безопасно, сигналы заблочены)
                    self._on_cat_click(it)
                    found_cat = True
                    break
            
            if not found_cat:
                self.model_list.clear() # Если вдруг категория не из списка (None и т.д.)
                return

            # 2. Находим и выделяем конкретную модель
            target_name = b.name
            for i in range(self.model_list.count()):
                it = self.model_list.item(i)
                if it.text() == target_name:
                    self.model_list.setCurrentItem(it)
                    self.model_list.scrollToItem(it)
                    break
        finally:
            self.cat_list.blockSignals(False)
            self.model_list.blockSignals(False)

    # ── обработчики ────────────────────────────────

    def _on_mapping_toggle(self, v):
        self.mapping_mode = v
        self.btn_mapping.setText("🔧 Mapping Mode [ON]" if v else "🔧 Mapping Mode")
        if hasattr(self, "btn_save_cfg"):
            self.btn_save_cfg.setVisible(v)
        if hasattr(self, "btn_clear_cache"):
            self.btn_clear_cache.setVisible(v)
        
        if hasattr(self, "side_presets"): self.side_presets.setVisible(not v)
        if hasattr(self, "side_models"):  self.side_models.setVisible(not v)
        
        self._render_params()
        self._log(f"Mapping Mode: {'ON' if v else 'OFF'}")

    def _on_prepost_drop(self, bid, new_pp):
        """Zone 1: только флаг, без свапа."""
        flip_prepost(bid, new_pp, self.blocks)
        self._send_pre_post(bid)
        self._refresh_chain()  # Перестраиваем цепочку — блок перепрыгнул PRE/POST
        self._select_block(bid)

    def _on_swap_requested(self, src_bid: str, tgt_bid: str, new_pp_hint: int):
        """Zone 2: вставка между блоками (swap + новые флаги)."""
        if not getattr(self, "experimental_free_routing", False):
            # Если Free Routing выключен — просто флипаем pre_post (имитируем Zone 1)
            return self._on_prepost_drop(src_bid, new_pp_hint)

        old_tgt_pp = self.blocks[tgt_bid].pre_post
        combo_swap(src_bid, tgt_bid, old_tgt_pp, new_pp_hint, self.blocks)

        self._execute_swap(src_bid, tgt_bid)
        self._refresh_chain()
        self._select_block(src_bid)
        self._log(f"⇄ Zone-2 insert: {src_bid} ↔ {tgt_bid} (PP: {old_tgt_pp}, {new_pp_hint})")

    def _on_unconditional_swap(self, src_bid: str, tgt_bid: str):
        """Zone 3: drop прямо на блок, чистый свап, pre/post не трожем."""
        if not getattr(self, "experimental_free_routing", False):
            # Если Free Routing выключен — игнорируем безусловный свап
            return

        swap_blocks(src_bid, tgt_bid, self.blocks)
        self._execute_swap(src_bid, tgt_bid)
        self._refresh_chain()
        self._select_block(src_bid)
        self._log(f"⇄ Zone-3 swap: {src_bid} ↔ {tgt_bid} (unconditional)")

    def _execute_swap(self, bid_a: str, bid_b: str):
        """POST-сваповая отправка MIDI для двух блоков.
        Требует чтобы routing.py уже переставил данные в BlockState.
        Порядок: OFF обоим → pre/post → fx_type → параметры → ON обоим.
        Вызывается синхронно в GUI-потоке: mido буферизует, команды улетают раньше чем
        юзер успеет что-то сделать. threading не нужен.
        """
        b_a = self.blocks[bid_a]
        b_b = self.blocks[bid_b]

        # Сохраняем финальный is_on — routing.py уже переставил его
        final_on_a = b_a.is_on
        final_on_b = b_b.is_on

        # 1. OFF обоим блокам
        b_a.is_on = False; self._send_on_off(bid_a)
        b_b.is_on = False; self._send_on_off(bid_b)

        # 2. pre/post
        self._send_pre_post(bid_a)
        self._send_pre_post(bid_b)

        # 3. Тип эффекта (model_id)
        self._send_fx_type(bid_a)
        self._send_fx_type(bid_b)

        # 4. Параметры (данные уже переставлены в BlockState)
        mapping_a = self._get_mapping(bid_a)
        mapping_b = self._get_mapping(bid_b)
        for cfg, pct in zip(mapping_a, b_a.params):
            if cfg.get("enabled", True):
                self._send_param(bid_a, cfg, pct)
        for cfg, pct in zip(mapping_b, b_b.params):
            if cfg.get("enabled", True):
                self._send_param(bid_b, cfg, pct)

        # 5. Восстанавливаем is_on (реальное состояние после свапа)
        b_a.is_on = final_on_a; self._send_on_off(bid_a)
        b_b.is_on = final_on_b; self._send_on_off(bid_b)

    def _on_toggle_on(self, checked):
        b = self.blocks[self.selected_id]
        b.is_on = checked
        self.btn_on.setText("ON" if checked else "OFF")
        self._send_on_off(self.selected_id)
        self._refresh_chain()

    def _on_toggle_pp(self, checked):
        b = self.blocks[self.selected_id]
        b.pre_post = 1 if checked else 0
        self.btn_pp.setText("POST" if checked else "PRE")
        self._send_pre_post(self.selected_id)
        self._refresh_chain()

    def _on_block_right_click(self, bid):
        """ПКМ по блоку в цепи: переключает ON/OFF (Bypass)."""
        # Gate, Volume and Cabinet on HD300 usually are not switched like that.
        if bid in ["GATE", "VOL", "CAB"]:
            return

        b = self.blocks[bid]
        b.is_on = not b.is_on
        
        # Если блок сейчас выбран - синхронизируем кнопку в панели настроек
        if bid == self.selected_id:
            self.btn_on.blockSignals(True)
            self.btn_on.setChecked(b.is_on)
            self.btn_on.setText("ON" if b.is_on else "OFF")
            self.btn_on.blockSignals(False)

        self._send_on_off(bid)
        self._refresh_chain()
        self._log(f"→ {bid} toggled {'ON' if b.is_on else 'OFF'} via Right Click")

    def _on_cat_click(self, item):
        if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        cat = item.text()
        col = CATEGORY_COLOR.get(cat, "#d6923c")
        self._update_list_accent(self.cat_list, col)
        self._update_list_accent(self.model_list, col)
        
        self.model_list.clear()
        
        self.model_list.setIconSize(QSize(40, 40))
        
        for name in sorted(self.cats_data.get(cat, [])):
            lst_item = QListWidgetItem(name)
            
            img_file = FX_IMG_MAP.get(name)
            if img_file:
                icon_path = os.path.join(SCRIPT_DIR, "img_converted", img_file)
                if os.path.exists(icon_path):
                    lst_item.setIcon(QIcon(icon_path))
                
            self.model_list.addItem(lst_item)

    def _on_model_click(self, item):
        name = item.text()
        bid  = self.selected_id
        b    = self.blocks[bid]
        
        cat_item = self.cat_list.currentItem()
        cat = cat_item.text() if cat_item else ""
        
        if cat == "Amp":
            for i, n in enumerate(self.cats_data["Amp"]):
                if n == name: b.model_id = i; break
        elif cat == "Cabinet":
            for i, n in enumerate(self.cats_data["Cabinet"]):
                if n == name: b.model_id = i; break
        elif cat == "Wah":
            for i, n in enumerate(self.cats_data["Wah"]):
                if n == name: b.model_id = i; break
        else:
            for hex_id, cfg in self.fx_config.items():
                if cfg.get("name") == name:
                    b.model_id = int(hex_id, 16)
                    break
        
        b.update_name()
        b.category = self._find_cat(b.name)
        if cat == "Amp": b.category = "Amp"
        if cat == "Cabinet": b.category = "Cabinet"
        if cat == "Wah": b.category = "Wah"
        b.params = []
        self._refresh_chain()
        self._render_params()
        self._send_fx_type(bid)
        
        # ⚡ HAWKING: Only if 4-Band Shift EQ is placed in REV slot
        if bid == "REV" and b.model_id == 0x24:
            # Run warmup in a separate thread so UI doesn't freeze during pauses
            import threading
            threading.Thread(target=warmup_4band_eq, args=(self, bid), daemon=True).start()
            # Give a bit more time before general parameter polling
            QTimer.singleShot(600, lambda: self._query_block_params(bid))
        elif bid == "AMP":
            QTimer.singleShot(150, lambda: self._request_preset_dump(0x1FFFFF))
        else:
            QTimer.singleShot(150, lambda: self._query_block_params(bid))
        self._refresh_chain()
        self._select_block(bid)

    def _on_learn_request(self, row):
        """Learn button handler in ParamRow"""
        if self._learning_row:
            self._learning_row.btn_learn.setChecked(False)
            self._learning_row.setStyleSheet("")
            
        if row.btn_learn.isChecked():
            self._learning_row = row
            row.setStyleSheet("ParamRow { background: #d6923c44; border: 1px solid #d6923c; }")
            self._log(f"👂 Learn Mode: Turn a knob on HD300 for '{row.cfg['name']}'")
        else:
            self._learning_row = None
            row.setStyleSheet("")
            self._log("Learn Mode cancelled.")

    def _on_preset_dclick(self, item):
        pc = item.data(Qt.ItemDataRole.UserRole)
        if getattr(self, "_sync_mode", False):
            self._sync_mode = False
            self._update_sync_ui()
            self._log("⏸ Sync interrupted by user")
            
        if MIDO_OK and self.midi_out:
            self.midi_out.send(mido.Message('program_change', program=pc))
            QTimer.singleShot(500, self._request_dump)
            self._log(f"→ PC #{pc}")

    # ── Save / Rename ──────────────────────────────

    def _save_active_preset(self):
        """'Send Active' button: requests edit buffer, then saves to slot."""
        if not MIDO_OK or not self.midi_out:
            self._log("❌ MIDI not connected — saving impossible.")
            return
        self._waiting_for_save_dump = True
        self._log(f"💾 Requesting Edit Buffer for saving to slot #{self.current_preset_num}...")
        self._request_preset_dump(0x1FFFFF)

    def _do_save_to_processor(self, edit_buffer_raw):
        """Edit buffer dump received — assemble write-SysEx and send."""
        pc = self.current_preset_num
        new_name = self._pending_rename if self._pending_rename else self.preset_name

        try:
            sysex = make_save_sysex(edit_buffer_raw, pc, new_name)
        except Exception as e:
            self._log(f"❌ SysEx assembly error: {e}")
            return

        sysex_body = sysex[1:-1]
        self.midi_out.send(mido.Message('sysex', data=sysex_body))

        bank = (pc // 4) + 1
        sub = ["A", "B", "C", "D"][pc % 4]
        self._log(f"✅ Preset '{new_name}' saved to {bank:02d}{sub} (#{pc})")

        self.preset_name = new_name
        self._pending_rename = None
        self.preset_cache[str(pc)] = new_name
        self._save_preset_cache()

        for i in range(self.preset_list.count()):
            item = self.preset_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == pc:
                item.setText(f"{bank:02d}{sub} - {new_name}")
                break

        self._update_preset_ui(pc, name=new_name)

    def _on_preset_right_click(self, pos):
        """RMB on preset: inline rename ONLY for active."""
        item = self.preset_list.itemAt(pos)
        if not item:
            return
        pc = item.data(Qt.ItemDataRole.UserRole)
        if pc != self.current_preset_num:
            return  # active preset only

        current_name = self.preset_name or ""
        edit = QLineEdit(current_name)
        edit.setMaxLength(15)
        edit.setStyleSheet(
            "QLineEdit { background: #1a1d22; color: #f0f0f0; border: 1px solid #d6923c;"
            " border-radius: 3px; padding: 2px 4px; font-size: 8pt; }"
        )
        self.preset_list.setItemWidget(item, edit)
        edit.setFocus()
        edit.selectAll()

        def finish():
            if not edit.parent():
                return
            new_name = edit.text().strip()
            if not new_name:
                new_name = current_name
            self._pending_rename = new_name
            self.preset_name = new_name

            bank = (pc // 4) + 1
            sub = ["A", "B", "C", "D"][pc % 4]
            item.setText(f"{bank:02d}{sub} - {new_name}")
            self.preset_list.removeItemWidget(item)

            self._update_preset_ui(pc, name=new_name)
            self._log(f"📝 Name changed to '{new_name}' (unsaved — click Send Active)")

        edit.returnPressed.connect(finish)
        edit.editingFinished.connect(finish)
