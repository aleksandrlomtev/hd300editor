"""
Константы, словари и маппинги для POD HD300 Visual Editor.
Все имена эффектов, усилителей, кабинетов, цвета категорий, иконки.
"""

import os

# Базовая директория ресурсов (сейчас в самой папке refactor/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────
#  СЛОВАРИ ID → ИМЯ
# ─────────────────────────────────────────────

FX_NAMES = {
    0x01:"Screamer", 0x02:"Spring", 0x03:"Smart Harmony", 0x04:"Chorus",
    0x05:"Seeker", 0x06:"Opto Tremolo", 0x07:"Digital Delay", 0x08:"Tape Echo",
    0x09:"Auto Volume Echo", 0x0A:"Plate", 0x0B:"Tube Drive", 0x0C:"Classic Distortion",
    0x0D:"Heavy Distortion", 0x0E:"Color Drive", 0x0F:"Overdrive", 0x10:"Line6 Drive",
    0x11:"Line6 Distortion", 0x12:"Boost Comp", 0x13:"Red Comp", 0x14:"Blue Comp",
    0x15:"Blue Comp Treb", 0x16:"Vetta Comp", 0x17:"Vetta Juice", 0x18:"Fuzz Pi",
    0x19:"Octave Fuzz", 0x1A:"Jet Fuzz", 0x1B:"Sub Octave Fuzz", 0x1C:"Buzz Saw",
    0x1D:"Facial Fuzz", 0x1E:"Jumbo Fuzz", 0x1F:"Spring '63", 0x20:"Particle Verb",
    0x21:"Graphic EQ", 0x22:"Studio EQ", 0x23:"Parametric EQ", 0x24:"4 Band Shift EQ",
    0x25:"Mid Focus EQ", 0x26:"Slow Filter", 0x27:"Tron Down", 0x28:"Tron Up",
    0x29:"Q Filter", 0x2A:"Ring Mod", 0x2B:"Dimension", 0x2C:"Freq Shifter",
    0x2D:"Rotary Drum", 0x2E:"Rotary Drum & Horn", 0x2F:"Pitch Glide",
    0x30:"Attack Synth", 0x31:"Synth String", 0x32:"Growler", 0x33:"Synth-O-Matic",
    0x34:"Bass Octaver", 0x35:"V-Tron", 0x36:"Analog Flanger", 0x37:"U-Vibe",
    0x38:"Phaser", 0x39:"Dual Phaser", 0x3A:"Barberpole Phaser", 0x3B:"Panned Phaser",
    0x3C:"Script Phase", 0x3D:"Pitch Vibrato", 0x3E:"Throbber", 0x3F:"Spin Cycle",
    0x40:"Obi Wah", 0x41:"Voice Box", 0x42:"Bias Tremolo", 0x43:"Pattern Tremolo",
    0x44:"Panner", 0x45:"Dig Delay w/Mod", 0x46:"Analog Echo",
    0x47:"Analog Echo w/Mod", 0x48:"Echo Platter", 0x49:"Echo Platter Studio",
    0x4A:"Low Res Delay", 0x4B:"Stereo Delay", 0x4C:"Ping Pong",
    0x4D:"Dynamic Delay", 0x4E:"Tape Echo Studio", 0x4F:"Tube Echo",
    0x50:"Tube Echo Studio", 0x51:"Multi-Head Delay", 0x52:"Sweep Echo",
    0x53:"Sweep Echo Studio", 0x54:"Reverse Delay", 0x55:"Room", 0x56:"Chamber",
    0x57:"Hall", 0x58:"Cave", 0x59:"Ducking", 0x5A:"Octo", 0x5B:"Tile",
    0x5C:"Echo (Reverb)", 0x5D:"Octisynth", 0x5E:"Vintage Pre", 0x5F:"Hard Gate",
    0x00:"NONE",
}

AMP_NAMES = {
    0x01:"Blackface Double Norm", 0x02:"Hiway 100", 0x03:"Super O",
    0x04:"Gibtone 185", 0x05:"Tweed B-Man Norm", 0x06:"Blackface Lux",
    0x07:"Divide 9/15", 0x08:"PhD Motorway", 0x09:"Class A-15",
    0x0A:"Class A-30", 0x0B:"Brit Plexi J-45 Bright", 0x0C:"Brit P-75 Bright",
    0x0D:"Brit J-800", 0x0E:"Bomber Uber", 0x0F:"Treadplate",
    0x10:"Angl Fireball", 0x11:"Blackface Double Vib", 0x12:"Tweed B-Man Bright",
    0x13:"Blackface Lux Vib", 0x14:"Brit Plexi J-45 Norm", 0x15:"Brit P-75 Norm",
    0x16:"Line6 Elektrik", 0x17:"Plexi Norm", 0x18:"Plexi Bright",
    0x19:"SLO100 Clean", 0x1A:"SLO100 Crunch", 0x1B:"SLO100 Overdrive",
    0x1C:"Line6 Doom", 0x1D:"Line6 Epic", 0x1E:"Flip Top",
}

CAB_NAMES = {
    0x00:"Matched Cab", 0x01:"212 Blackface", 0x02:"412 Hiway",
    0x03:"6x9 Supro", 0x04:"112 Gibtone F-coil", 0x05:"410 Tweed B-Man",
    0x06:"112 Blackface Lux", 0x07:"112 Brit 12H", 0x08:"212 PhD Ported",
    0x09:"112 Blue Bell", 0x0A:"212 Silver Bell", 0x0B:"412 Greenback 25",
    0x0C:"412 Blackback 30", 0x0D:"412 Brit T75", 0x0E:"412 Uber",
    0x0F:"412 Treadplate 30", 0x10:"XXL V-30", 0x11:"115 Flip Top",
    0x12:"NONE",
}

MATCHED_CABS = {
    0x01: 0x01, 0x11: 0x01, 0x06: 0x06, 0x13: 0x06,
    0x05: 0x05, 0x12: 0x05, 0x04: 0x04, 0x03: 0x03,
    0x02: 0x02, 0x07: 0x07, 0x08: 0x08, 0x09: 0x09,
    0x0A: 0x0A, 0x0B: 0x0B, 0x14: 0x0B, 0x17: 0x0B,
    0x18: 0x0B, 0x0C: 0x0C, 0x15: 0x0C, 0x0D: 0x0D,
    0x0E: 0x0E, 0x0F: 0x0F, 0x10: 0x10, 0x19: 0x0D,
    0x1A: 0x0D, 0x1B: 0x0D, 0x16: 0x0E, 0x1C: 0x02,
    0x1D: 0x10, 0x1E: 0x11,
}

WAH_NAMES = {
    0x00:"Vetta Wah", 0x01:"Fassel Wah", 0x02:"Chrome Wah",
    0x03:"Weeper Wah", 0x04:"Conductor Wah", 0x05:"Colorful Wah",
}

# ─────────────────────────────────────────────
#  ВИЗУАЛ: ЦВЕТА, ИКОНКИ, МАППИНГИ
# ─────────────────────────────────────────────

CATEGORY_COLOR = {
    "Distortion":  "#e67e22",
    "Dynamics":    "#5d5d5d",
    "Modulation":  "#2980b9",
    "Delay":       "#27ae60",
    "Reverb":      "#16a085",
    "Pitch/Synth": "#EA2142", #old #d35400
    "Filter":      "#8564bf", 
    "EQ":          "#8564bf",
    "Amp":         "#c0392b",
    "Cabinet":     "#c0392b",
    "Wah":         "#b9a03c",
    "Vol":         "#555555",
    "Gate":        "#2c3e50",
    "None":        "#3a3a3a",
}

CATEGORY_IMG = {
    "Distortion": "dist.webp",
    "Dynamics": "dyn.webp",
    "Modulation": "mod.webp",
    "Delay": "dly.webp",
    "Reverb": "rev.webp",
    "Pitch/Synth": "pitch.webp",
    "Filter": "filt_eq.webp",
    "EQ": "filt_eq.webp",
    "Amp": "amp.webp",
    "Cabinet": "cab.webp",
    "Gate": "gate.webp",
    "Vol": "vol.webp",
    "Volume": "vol.webp",
    "Wah": "wah.webp"
}

CATEGORY_ICON = {
    "Distortion": "🟧", "Dynamics": "📈", "Modulation": "🌀",
    "Delay": "⏱", "Reverb": "🌊", "Pitch/Synth": "🎹",
    "Filter": "⚗", "EQ": "🎚", "Amp": "🔊", "Cabinet": "🧱",
    "Gate": "⊘", "Vol": "⊣", "Wah": "🦶", "None": "◼",
}

# Маппинг имён эффектов/усилителей/кабинетов на файлы иконок в img_converted/
FX_IMG_MAP = {
    # FX
    "Screamer": "Screamer.png", "Spring": "Spring.png", "Smart Harmony": "SmartHarmony.png",
    "Chorus": "AnalogChorus.png", "Seeker": "Seeker.png", "Opto Tremolo": "OptoTremolo.png",
    "Digital Delay": "DigitalDelay.png", "Tape Echo": "TapeEcho.png",
    "Auto Volume Echo": "Auto-Volume.png", "Plate": "Plate.png",
    "Tube Drive": "TubeDrive.png", "Classic Distortion": "ClassicDistortion.png",
    "Heavy Distortion": "HeavyDistortion.png", "Color Drive": "ColorDrive.png",
    "Overdrive": "Overdrive.png", "Line6 Drive": "Line6Drive.png",
    "Line6 Distortion": "Line6Distortion.png", "Boost Comp": "BoostComp.png",
    "Red Comp": "RedComp.png", "Blue Comp": "BlueComp.png",
    "Blue Comp Treb": "BlueCompTreb.png", "Vetta Comp": "VettaComp.png",
    "Vetta Juice": "VettaJuice.png", "Fuzz Pi": "FuzzPi.png",
    "Octave Fuzz": "OctaveFuzz.png", "Jet Fuzz": "JetFuzz.png",
    "Sub Octave Fuzz": "SubOctaveFuzz.png", "Buzz Saw": "BuzzSaw.png",
    "Facial Fuzz": "FacialFuzz.png", "Jumbo Fuzz": "JumboFuzz.png",
    "Spring '63": "Spring.png", "Particle Verb": "Octo.png",
    "Graphic EQ": "GraphicEQ.png", "Studio EQ": "StudioEQ.png",
    "Parametric EQ": "ParametricEQ.png", "4 Band Shift EQ": "4BandShiftEQ.png",
    "Mid Focus EQ": "MidFocusEQ.png", "Slow Filter": "SlowFilter.png",
    "Tron Down": "TronDown.png", "Tron Up": "TronUp.png",
    "Q Filter": "QFilter.png", "Ring Mod": "RingModulator.png",
    "Dimension": "Dimension.png", "Freq Shifter": "FrequencyShifter.png",
    "Rotary Drum": "RotaryDrum.png", "Rotary Drum & Horn": "RotaryDrum&Horn.png",
    "Pitch Glide": "PitchGlide.png", "Attack Synth": "AttackSynth.png",
    "Synth String": "SynthString.png", "Growler": "Growler.png",
    "Synth-O-Matic": "Synth-O-Matic.png", "Bass Octaver": "BassOctaver.png",
    "V-Tron": "V-Tron.png", "Analog Flanger": "AnalogFlanger.png",
    "U-Vibe": "U-Vibe.png", "Phaser": "Phaser.png",
    "Dual Phaser": "DualPhaser.png", "Barberpole Phaser": "BarberpolePhaser.png",
    "Panned Phaser": "PannedPhaser.png", "Script Phase": "ScriptPhase.png",
    "Pitch Vibrato": "PitchVibrato.png", "Throbber": "Throbber.png",
    "Spin Cycle": "SpinCycle.png", "Obi Wah": "ObiWah.png",
    "Voice Box": "VoiceBox.png", "Bias Tremolo": "BiasTremolo.png",
    "Pattern Tremolo": "PatternTremolo.png", "Panner": "Panner.png",
    "Dig Delay w/Mod": "DigitalDlywMod.png", "Analog Echo": "AnalogEcho.png",
    "Analog Echo w/Mod": "AnalogDlywMod.png", "Echo Platter": "EchoPlatter.png",
    "Echo Platter Studio": "EchoPlatterDry.png", "Low Res Delay": "LoResDelay.png",
    "Stereo Delay": "StereoDelay.png", "Ping Pong": "PingPong.png",
    "Dynamic Delay": "DynamicDelay.png", "Tape Echo Studio": "TapeEchoDry.png",
    "Tube Echo": "TubeEcho.png", "Tube Echo Studio": "TubeEchoDry.png",
    "Multi-Head Delay": "Multi-HeadDelay.png", "Sweep Echo": "SweepEcho.png",
    "Sweep Echo Studio": "SweepEchoDry.png", "Reverse Delay": "ReverseDelay.png",
    "Room": "Room.png", "Chamber": "Chamber.png", "Hall": "Hall.png",
    "Cave": "Cave.png", "Ducking": "Ducking.png", "Octo": "Octo.png",
    "Tile": "Tile.png", "Echo (Reverb)": "Echo.png", "Octisynth": "Octisynth.png",
    "Vintage Pre": "VintagePre.png", "Hard Gate": "HardGate.png",
    # AMP
    "Blackface Double Norm": "BlackfaceDblNrm.png", "Hiway 100": "Hiway100.png",
    "Super O": "SuperO.png", "Gibtone 185": "Gibtone185.png",
    "Tweed B-Man Norm": "TweedB-ManNrm.png", "Blackface Lux": "1x12BlueBell.png",
    "Divide 9/15": "Divide915.png", "PhD Motorway": "PhDMotorway.png",
    "Class A-15": "ClassA-15.png", "Class A-30": "ClassA-30TB.png",
    "Brit Plexi J-45 Bright": "BritJ-45Brt.png", "Brit P-75 Bright": "BritP-75Brt.png",
    "Brit J-800": "BritJ-800.png", "Bomber Uber": "BomberUber.png",
    "Treadplate": "Treadplate.png", "Angl Fireball": "AngelF-Ball.png",
    "Blackface Double Vib": "BlackfaceDblVib.png", "Tweed B-Man Bright": "TweedB-ManBrt.png",
    "Blackface Lux Vib": "BlackfaceDblVib.png", "Brit Plexi J-45 Norm": "BritJ-45Nrm.png",
    "Brit P-75 Norm": "BritP-75Nrm.png", "Line6 Elektrik": "Line6Elektrik.png",
    "Plexi Norm": "PlexiLead100Nrm.png", "Plexi Bright": "PlexiLead100Brt.png",
    "SLO100 Clean": "Solo-100Clean.png", "SLO100 Crunch": "Solo-100Crunch.png",
    "SLO100 Overdrive": "Solo-100Overdrive.png", "Line6 Doom": "Line6Doom.png",
    "Line6 Epic": "Line6Epic.png", "Flip Top": "FlipTop.png",
    # CAB
    "Matched Cab": "2x12BlackfaceDbl.png", "212 Blackface": "2x12BlackfaceDbl.png",
    "412 Hiway": "4x12Hiway.png", "6x9 Supro": "1x(6x9)SuperO.png",
    "112 Gibtone F-coil": "1x12GibtoneF-Coil.png", "410 Tweed B-Man": "4x10TweedB-Man.png",
    "112 Blackface Lux": "1x12BlueBell.png", "112 Brit 12H": "1x12Celest12-H.png",
    "212 PhD Ported": "2x12PhDPorted.png", "112 Blue Bell": "1x12BlueBell.png",
    "212 Silver Bell": "2x12SilverBell.png", "412 Greenback 25": "4x12Greenback25.png",
    "412 Blackback 30": "4x12Blackback30.png", "412 Brit T75": "4x12BritT-75.png",
    "412 Uber": "4x12Uber.png", "412 Treadplate 30": "4x12TreadV-30.png",
    "XXL V-30": "4x12XXLV-30.png", "115 Flip Top": "115FlipTop.png",
    # WAH
    "Vetta Wah": "VettaWah.png", "Fassel Wah": "Fassel.png",
    "Chrome Wah": "Chrome.png", "Weeper Wah": "Weeper.png",
    "Conductor Wah": "Conductor.png", "Colorful Wah": "Colorful.png",
    # Special
    "Volume Pedal": "VolumePedal.png", "Noise Gate": "NoiseGate.png",
}
