import time

def warmup_4band_eq(app, bid):
    """
    ♿ HAWKING'S WHEELCHAIR (Special hack for 4-Band Shift EQ in REV slot).
    Initializes CPU registers with SET commands to wake it up.
    """
    if bid != "REV":
        return

    app._log("♿ Forced warm-up for 4-Band EQ (FX4)...")
    app._is_warming_up = True
    
    # SLOT 0x23 - REV parameter control
    # Set all 5 knobs to 50% (center/0dB)
    # And must send in pairs 0x63 (Live) and 0x62 (Commit), just like when turning sliders
    warmup_val = [0x3F, 0x7F, 0x7F]
    
    try:
        for p_idx in range(1, 6):
            cmd_63 = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x63, 0x00, 0x23, p_idx] + warmup_val
            cmd_62 = [0x00, 0x01, 0x0C, 0x14, 0x00, 0x62, 0x00, 0x23, p_idx] + warmup_val
            
            app._send_raw(cmd_63)
            app._send_raw(cmd_62)
            time.sleep(0.04) # small delay between parameters
        
        time.sleep(0.3) # Give the CPU time to digest these 10 messages
    finally:
        app._is_warming_up = False
        app._log("♿ Landing completed.")
