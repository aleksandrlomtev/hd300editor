import time

def warmup_4band_eq(app, bid):
    """
    ♿ КРЕСЛО ХОККИНГА (Спец-хак для 4-Band Shift EQ в REV слоте).
    Инициализирует регистры процессора SET-командами, чтобы он проснулся.
    """
    if bid != "REV":
        return

    app._log("♿ Принудительный прогрев 4-Band EQ (FX4)...")
    app._is_warming_up = True
    
    # СЛОТ 0x23 - управление параметрами REV
    # Выставляем все 5 ручек в 50% (центр/0дб)
    # И обязательно шлем парами 0x63 (Live) и 0x62 (Commit), прямо как при кручении ползунков
    warmup_val = [0x3F, 0x7F, 0x7F]
    
    try:
        for p_idx in range(1, 6):
            cmd_63 = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x63, 0x00, 0x23, p_idx] + warmup_val
            cmd_62 = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x62, 0x00, 0x23, p_idx] + warmup_val
            
            app._send_raw(cmd_63)
            app._send_raw(cmd_62)
            time.sleep(0.04) # небольшая задержка между параметрами
        
        time.sleep(0.3) # Даем процу переварить эти 10 сообщений
    finally:
        app._is_warming_up = False
        app._log("♿ Посадка завершена.")
