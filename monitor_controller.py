"""
MonitorController — configure your monitor from Windows through DDC/CI.
Configure o seu monitor pelo Windows via DDC/CI.

NOTICE / AVISO
    This project was developed with the help of AI (Claude, by Anthropic).
    Este projeto foi desenvolvido com a ajuda de IA (Claude, da Anthropic).
    Review the code and use it at your own risk. / Revise o código e use por sua conta e risco.

Run / Rodar:       python monitor_controller.py
Demo (no monitor): python monitor_controller.py --demo
CLI:               MonitorController.exe --profile NAME [--monitor N]
Language:          --lang pt | --lang en
"""
from __future__ import annotations

import ctypes
import json
import os
import pprint
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

try:
    import customtkinter as ctk
    from PIL import Image
except ImportError:
    raise SystemExit("Missing dependencies / Faltam dependências:  pip install -r requirements.txt")
try:
    from monitorcontrol import get_monitors
except ImportError:
    raise SystemExit("Missing dependency / Falta dependência:  pip install monitorcontrol")

APP_NAME = "MonitorController"
APP_ID = "MonitorController"
VERSION = "1.0.0"
CFG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_ID)
CFG_FILE = os.path.join(CFG_DIR, "config.json")
PROFILES_FILE = os.path.join(CFG_DIR, "profiles.json")
LOCK = threading.Lock()
IS_WIN = sys.platform == "win32"

# ------------------------------------------------------------------ theme
BG = "#060a12"
CARD = "#0c121d"
CARD2 = "#111a2a"
HOVER = "#17233a"
BORDER = "#1a2538"
TEXT = "#e6edf7"
MUTED = "#7b8798"
ACCENT = "#2b86ff"
ACCENT_HOVER = "#4a9bff"
ACCENT_DIM = "#0b2a57"
DANGER = "#ff5d6c"
OK = "#3ddc97"
KNOB = "#e8f1ff"
FAMILY = "Segoe UI" if IS_WIN else None


def font(size=13, bold=False):
    return ctk.CTkFont(family=FAMILY, size=size, weight="bold" if bold else "normal")


def resource(path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, path)


# ------------------------------------------------------------------ i18n
def detect_lang():
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            lang = json.load(f).get("lang")
            if lang in ("pt", "en"):
                return lang
    except Exception:
        pass
    try:
        if IS_WIN:
            return "pt" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF) == 0x16 else "en"
    except Exception:
        pass
    return "pt" if os.environ.get("LANG", "").lower().startswith("pt") else "en"


LANG = detect_lang()


def T(pt, en):
    return pt if LANG == "pt" else en


def tr(x):
    return (x[0] if LANG == "pt" else x[1]) if isinstance(x, tuple) else x


def save_config(**kw):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        try:
            with open(CFG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg.update(kw)
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        pass


# ------------------------------------------------------------------ VCP tables (MCCS)
R, G, B = ("Vermelho", "Red"), ("Verde", "Green"), ("Azul", "Blue")
Y, C, M = ("Amarelo", "Yellow"), ("Ciano", "Cyan"), ("Magenta", "Magenta")
G_PIC = ("Imagem", "Picture")
G_AUD = ("Áudio", "Audio")
G_TMP = ("Temperatura de cor", "Color temperature")
G_GAIN = ("Ganho RGB (balanço de branco)", "RGB gain (white balance)")
G_BLK = ("Nível de preto", "Black level")
G_SAT = ("Saturação por cor", "Saturation per color")
G_HUE = ("Matiz por cor", "Hue per color")

# (code, label, page, group)
SLIDERS = [
    (0x10, ("Brilho", "Brightness"), "image", G_PIC),
    (0x12, ("Contraste", "Contrast"), "image", G_PIC),
    (0x87, ("Nitidez", "Sharpness"), "image", G_PIC),
    (0x8A, ("Saturação", "Saturation"), "image", G_PIC),
    (0x90, ("Matiz", "Hue"), "image", G_PIC),
    (0x62, ("Volume", "Volume"), "image", G_AUD),
    (0x0C, ("Temperatura", "Temperature"), "color", G_TMP),
    (0x16, R, "color", G_GAIN), (0x18, G, "color", G_GAIN), (0x1A, B, "color", G_GAIN),
    (0x6C, R, "color", G_BLK), (0x6E, G, "color", G_BLK), (0x70, B, "color", G_BLK),
    (0x59, R, "color", G_SAT), (0x5A, Y, "color", G_SAT), (0x5B, G, "color", G_SAT),
    (0x5C, C, "color", G_SAT), (0x5D, B, "color", G_SAT), (0x5E, M, "color", G_SAT),
    (0x9B, R, "color", G_HUE), (0x9C, Y, "color", G_HUE), (0x9D, G, "color", G_HUE),
    (0x9E, C, "color", G_HUE), (0x9F, B, "color", G_HUE), (0xA0, M, "color", G_HUE),
]
GAIN_CODES = (0x16, 0x18, 0x1A)

COLOR_PRESETS = {
    0x01: "sRGB", 0x02: T("Nativo", "Native"), 0x03: "4000K", 0x04: "5000K", 0x05: "6500K",
    0x06: "7500K", 0x07: "8200K", 0x08: "9300K", 0x09: "10000K", 0x0A: "11500K",
    0x0B: T("Usuário 1", "User 1"), 0x0C: T("Usuário 2", "User 2"), 0x0D: T("Usuário 3", "User 3"),
}
INPUTS = {
    0x01: "VGA-1", 0x02: "VGA-2", 0x03: "DVI-1", 0x04: "DVI-2", 0x05: "Composite-1",
    0x0F: "DisplayPort-1", 0x10: "DisplayPort-2", 0x11: "HDMI-1", 0x12: "HDMI-2",
    0x13: "HDMI-3", 0x14: "HDMI-4", 0x1B: "USB-C",
}
DISPLAY_MODES = {
    0x00: T("Padrão", "Standard"), 0x01: T("Produtividade", "Productivity"), 0x02: T("Misto", "Mixed"),
    0x03: T("Filme", "Movie"), 0x04: T("Usuário", "User"), 0x05: T("Jogos", "Games"),
    0x06: T("Esportes", "Sports"), 0x07: T("Profissional", "Professional"),
}
# (code, label, page, table)
CHOICES = [
    (0xDC, ("Modo de imagem", "Picture mode"), "image", DISPLAY_MODES),
    (0x14, ("Preset de cor", "Color preset"), "color", COLOR_PRESETS),
    (0x60, ("Fonte de entrada", "Input source"), "input", INPUTS),
]
# (code, label, page, group, on_value, off_value)
TOGGLES = [
    (0x8D, ("Mudo", "Mute"), "image", G_AUD, 1, 2),
    (0xCA, ("Menu OSD / botões do monitor", "OSD menu / monitor buttons"), "adv", None, 2, 1),
]
RESETS = [
    (0x08, ("Restaurar cores", "Reset colors")),
    (0x05, ("Restaurar brilho e contraste", "Reset brightness & contrast")),
    (0x04, ("Reset de fábrica", "Factory reset")),
]
RISKY = {0x04, 0x05, 0x06, 0x08, 0xD6, 0x60, 0xCA}
PROBE = (
    [c for c, *_ in SLIDERS] + [c for c, *_ in CHOICES] + [t[0] for t in TOGGLES]
)
VCP_NAMES = {
    0x02: "New control value", 0x04: "Restore factory defaults", 0x05: "Restore brightness/contrast",
    0x06: "Restore geometry", 0x08: "Restore color defaults", 0x0B: "Color temp increment",
    0x0C: "Color temp request", 0x10: "Brightness", 0x12: "Contrast", 0x14: "Color preset",
    0x16: "Gain R", 0x18: "Gain G", 0x1A: "Gain B", 0x1E: "Auto setup", 0x20: "H position",
    0x30: "V position", 0x52: "Active control", 0x59: "Saturation R", 0x5A: "Saturation Y",
    0x5B: "Saturation G", 0x5C: "Saturation C", 0x5D: "Saturation B", 0x5E: "Saturation M",
    0x60: "Input source", 0x62: "Volume", 0x6C: "Black level R", 0x6E: "Black level G",
    0x70: "Black level B", 0x72: "Gamma", 0x87: "Sharpness", 0x8A: "Saturation", 0x8D: "Mute",
    0x90: "Hue", 0x9B: "Hue R", 0x9C: "Hue Y", 0x9D: "Hue G", 0x9E: "Hue C", 0x9F: "Hue B",
    0xA0: "Hue M", 0xAC: "H frequency", 0xAE: "V frequency", 0xB2: "Sub-pixel layout",
    0xB6: "Display technology", 0xC0: "Usage hours", 0xC8: "Controller type", 0xC9: "Firmware",
    0xCA: "OSD / buttons", 0xCC: "OSD language", 0xD6: "Power mode", 0xDC: "Picture mode",
    0xDF: "VCP version",
}


# ------------------------------------------------------------------ DDC/CI layer
class Ddc:
    def __init__(self, mon):
        self.mon = mon
        self.raw_caps = None

    def get(self, code):
        with LOCK, self.mon:
            return self.mon.vcp.get_vcp_feature(code)

    def try_get(self, code, tries=2):
        for _ in range(tries):
            try:
                return self.get(code)
            except Exception:
                time.sleep(0.05)
        return None

    def set(self, code, value):
        with LOCK, self.mon:
            self.mon.vcp.set_vcp_feature(code, int(value))

    def capabilities(self):
        try:
            with LOCK, self.mon:
                self.raw_caps = self.mon.get_vcp_capabilities()
        except Exception:
            self.raw_caps = None
        return self.raw_caps


def parse_caps(raw):
    out = {"model": None, "mccs": None, "codes": set(), "allowed": {}}
    if not isinstance(raw, dict):
        return out
    out["model"] = raw.get("model") or None
    out["mccs"] = raw.get("mccs_ver") or None
    vcp = raw.get("vcp")
    if isinstance(vcp, dict):
        for code, vals in vcp.items():
            try:
                c = int(code)
            except (TypeError, ValueError):
                continue
            out["codes"].add(c)
            if vals:
                try:
                    out["allowed"][c] = sorted(int(v) for v in vals)
                except (TypeError, ValueError):
                    pass
    return out


def parse_val(text):
    text = str(text).strip()
    m = re.search(r"0x([0-9a-fA-F]+)", text)
    try:
        return int(m.group(1), 16) if m else int(text, 0)
    except ValueError:
        return None


# ------------------------------------------------------------------ profiles
def load_profiles():
    for path in (PROFILES_FILE, os.path.join(os.path.dirname(CFG_DIR), "TargetMonitor", "profiles.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def save_profiles(data):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def cli_apply(name, idx):
    profs = load_profiles()
    if name not in profs:
        raise SystemExit(f"Profile '{name}' not found. Available: {', '.join(profs) or '(none)'}")
    mons = list(get_monitors())
    if idx >= len(mons):
        raise SystemExit("Monitor not found.")
    ddc = Ddc(mons[idx])
    for code, val in profs[name].items():
        try:
            ddc.set(int(code, 16), val)
        except Exception as e:
            print(f"Error {code}: {e}")
        time.sleep(0.1)


# ------------------------------------------------------------------ demo monitors (--demo)
class _DemoVcp:
    def __init__(self, state, maxes):
        self.state, self.maxes = state, maxes

    def get_vcp_feature(self, code):
        if code not in self.state:
            raise RuntimeError("unsupported")
        time.sleep(0.005)
        return self.state[code], self.maxes[code]

    def set_vcp_feature(self, code, value):
        if code not in self.state:
            raise RuntimeError("unsupported")
        self.state[code] = value


class DemoMonitor:
    def __init__(self, spec, caps):
        self.state = {c: v[0] for c, v in spec.items()}
        self.maxes = {c: v[1] for c, v in spec.items()}
        self.vcp = _DemoVcp(self.state, self.maxes)
        self._caps = caps

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_vcp_capabilities(self):
        return self._caps


def demo_monitors():
    full = {
        0x10: (50, 100), 0x12: (52, 100), 0x14: (11, 11), 0x16: (50, 100), 0x18: (50, 100),
        0x1A: (50, 100), 0x0C: (35, 63), 0x60: (0x11, 3), 0x62: (50, 100), 0x6C: (80, 100),
        0x6E: (80, 100), 0x70: (80, 100), 0x87: (2, 4), 0x8A: (50, 100), 0x8D: (0, 2),
        0xCA: (1, 2), 0xDC: (0, 9), 0x04: (0, 1), 0x05: (0, 1), 0x08: (0, 1), 0xAE: (18020, 65535),
    }
    full_caps = {
        "model": "DEMO-27G180", "mccs_ver": "2.2", "type": "lcd",
        "vcp": {0x10: {}, 0x12: {}, 0x14: {1: {}, 4: {}, 5: {}, 8: {}, 11: {}}, 0x60: {0x0F: {}, 0x11: {}, 0x12: {}},
                0xDC: {0: {}, 1: {}, 3: {}, 5: {}, 7: {}}, 0x8D: {}, 0xCA: {}},
    }
    basic = {0x10: (70, 100), 0x12: (75, 100), 0x14: (5, 8), 0x60: (0x0F, 2), 0x04: (0, 1)}
    basic_caps = {"model": "DEMO-Office-24", "mccs_ver": "2.1",
                  "vcp": {0x10: {}, 0x12: {}, 0x14: {1: {}, 5: {}, 8: {}}, 0x60: {0x0F: {}, 0x01: {}}}}
    return [DemoMonitor(full, full_caps), DemoMonitor(basic, basic_caps)]


# ------------------------------------------------------------------ widgets
class Card(ctk.CTkFrame):
    def __init__(self, master, title=None):
        super().__init__(master, fg_color=CARD, border_width=1, border_color=BORDER, corner_radius=14)
        if title:
            ctk.CTkLabel(self, text=str(title).upper(), text_color=MUTED, font=font(11, True)).pack(
                anchor="w", padx=16, pady=(14, 2))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x", padx=16, pady=(6 if title else 14, 14))


class SliderRow(ctk.CTkFrame):
    def __init__(self, master, label, value, maxv, on_change):
        super().__init__(master, fg_color="transparent")
        self.max = max(1, int(maxv))
        self.on_change = on_change
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=label, font=font(13), text_color=TEXT).pack(side="left")
        self.pill = ctk.CTkLabel(top, text=str(value), width=50, height=24, corner_radius=8,
                                 fg_color=CARD2, text_color=TEXT, font=font(12, True))
        self.pill.pack(side="right")
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(4, 0))
        self._btn(bar, "‹", -1).pack(side="left")
        self.slider = ctk.CTkSlider(
            bar, from_=0, to=self.max, number_of_steps=self.max if self.max <= 1000 else None,
            command=self._moved, height=16, progress_color=ACCENT, button_color=KNOB,
            button_hover_color="#ffffff", fg_color="#1b2638")
        self.slider.set(min(value, self.max))
        self.slider.pack(side="left", fill="x", expand=True, padx=8)
        self._btn(bar, "›", +1).pack(side="left")

    def _btn(self, parent, text, delta):
        return ctk.CTkButton(parent, text=text, width=28, height=26, corner_radius=8, fg_color=CARD2,
                             hover_color=HOVER, text_color=TEXT, font=font(15, True),
                             command=lambda: self.step(delta))

    def _moved(self, v):
        v = int(round(v))
        self.pill.configure(text=str(v))
        self.on_change(v)

    def step(self, delta):
        v = max(0, min(self.max, int(round(self.slider.get())) + delta))
        self.slider.set(v)
        self._moved(v)


class Tiles(ctk.CTkFrame):
    def __init__(self, master, options, current, on_pick, columns=3, height=40):
        super().__init__(master, fg_color="transparent")
        self.on_pick = on_pick
        self.buttons = {}
        for i, (val, label) in enumerate(options):
            b = ctk.CTkButton(self, text=label, height=height, corner_radius=10, border_width=1,
                              font=font(13), command=lambda v=val: self._pick(v))
            b.grid(row=i // columns, column=i % columns, padx=4, pady=4, sticky="ew")
            self.buttons[val] = b
        for c in range(columns):
            self.grid_columnconfigure(c, weight=1, uniform="tiles")
        self.current = None
        self.select(current)

    def select(self, val):
        self.current = val
        for v, b in self.buttons.items():
            if v == val:
                b.configure(fg_color=ACCENT, border_color=ACCENT_HOVER, hover_color=ACCENT_HOVER, text_color="#ffffff")
            else:
                b.configure(fg_color=CARD2, border_color=BORDER, hover_color=HOVER, text_color=TEXT)

    def _pick(self, val):
        if self.on_pick(val) is not False:
            self.select(val)


class Dropdown(ctk.CTkOptionMenu):
    def __init__(self, master, options, current, on_pick, width=260):
        self.map = {label: val for val, label in options}
        self.rev = {val: label for val, label in options}
        self.on_pick = on_pick
        self.cur = current
        super().__init__(master, values=[l for _, l in options], command=self._cmd, width=width, height=36,
                         corner_radius=10, fg_color=CARD2, button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                         dropdown_fg_color=CARD2, dropdown_hover_color=HOVER, dropdown_text_color=TEXT,
                         text_color=TEXT, font=font(13), dropdown_font=font(13), anchor="w")
        self.set(self.rev.get(current, str(current)))

    def _cmd(self, label):
        val = self.map[label]
        if self.on_pick(val) is False:
            self.set(self.rev.get(self.cur, ""))
        else:
            self.cur = val


def make_choice(parent, options, current, on_pick, tile_height=40):
    if len(options) <= 6:
        return Tiles(parent, options, current, on_pick, columns=max(1, min(3, len(options))), height=tile_height)
    return Dropdown(parent, options, current, on_pick)


class Modal(ctk.CTkToplevel):
    def __init__(self, parent, title, message, entry=False, default="", yes=None, no=None, danger=False):
        super().__init__(parent, fg_color=CARD)
        self.result = None
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        ctk.CTkLabel(self, text=message, font=font(13), text_color=TEXT, wraplength=380,
                     justify="left").pack(padx=22, pady=(20, 10), anchor="w")
        self.entry = None
        if entry:
            self.entry = ctk.CTkEntry(self, width=380, height=36, fg_color=CARD2, border_color=BORDER, text_color=TEXT)
            self.entry.pack(padx=22, pady=(0, 10))
            self.entry.insert(0, default)
            self.entry.bind("<Return>", lambda e: self._ok())
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(8, 18))
        ctk.CTkButton(row, text=yes or "OK", width=110, height=34, corner_radius=10,
                      fg_color=DANGER if danger else ACCENT, hover_color="#ff7d89" if danger else ACCENT_HOVER,
                      font=font(13, True), command=self._ok).pack(side="right")
        ctk.CTkButton(row, text=no or T("Cancelar", "Cancel"), width=110, height=34, corner_radius=10,
                      fg_color=CARD2, hover_color=HOVER, text_color=TEXT, font=font(13),
                      command=self._cancel).pack(side="right", padx=8)
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.after(150, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
            (self.entry or self).focus_set()
        except tk.TclError:
            pass

    def _ok(self):
        self.result = self.entry.get() if self.entry else True
        self.destroy()

    def _cancel(self):
        self.result = None if self.entry else False
        self.destroy()


def ask(parent, title, message, **kw):
    m = Modal(parent, title, message, **kw)
    parent.wait_window(m)
    return m.result


# ------------------------------------------------------------------ app
class App(ctk.CTk):
    def __init__(self, demo=False):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=BG)
        self.title(APP_NAME)
        self.geometry("800x840")
        self.minsize(720, 640)
        self.set_icon()
        self.ui_q = queue.Queue()
        self.timers = {}
        self.values = {}
        self.overlay = None
        self.dim_pct = 0
        self.ddc = None
        self.info = parse_caps(None)
        self.token = 0
        self.sel_profile = None
        self.mon_idx = 0
        self.err = None
        try:
            self.monitors = list(demo_monitors() if demo else get_monitors())
        except Exception as e:
            self.monitors, self.err = [], str(e)
        self.mon_labels = [f"{T('Monitor', 'Monitor')} {i + 1}" for i in range(len(self.monitors))]
        self.build_ui()
        self.after(50, self.poll)
        self.after(250, self.load)

    # ---- infra
    def set_icon(self):
        try:
            if IS_WIN:
                self.after(300, lambda: self.iconbitmap(resource("assets/icon.ico")))
            else:
                self._icon = tk.PhotoImage(file=resource("assets/icon.png"))
                self.iconphoto(True, self._icon)
        except Exception:
            pass

    def ui(self, fn):
        self.ui_q.put(fn)

    def poll(self):
        try:
            while True:
                self.ui_q.get_nowait()()
        except queue.Empty:
            pass
        self.after(50, self.poll)

    def bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def status(self, msg, kind="info"):
        def apply():
            self.status_lbl.configure(text=msg)
            self.dot.configure(text_color={"ok": OK, "err": DANGER}.get(kind, ACCENT))
        self.ui(apply)

    # ---- layout
    def build_ui(self):
        for w in self.winfo_children():
            w.destroy()
        self.overlay = None
        self.page = {}

        # footer first, so the tab area fills what's left
        foot = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=34)
        foot.pack(fill="x", side="bottom")
        self.dot = ctk.CTkLabel(foot, text="●", text_color=ACCENT, font=font(12))
        self.dot.pack(side="left", padx=(14, 6), pady=6)
        self.status_lbl = ctk.CTkLabel(foot, text=T("Pronto", "Ready"), text_color=MUTED, font=font(12))
        self.status_lbl.pack(side="left")
        ctk.CTkLabel(foot, text=T("Desenvolvido com auxílio de IA (Claude)", "Built with AI assistance (Claude)"),
                     text_color="#566175", font=font(11)).pack(side="right", padx=14)

        # header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 6))
        try:
            img = Image.open(resource("assets/logo_light.png"))
            self.logo = ctk.CTkImage(light_image=img, dark_image=img, size=(33, 36))
            ctk.CTkLabel(head, image=self.logo, text="").pack(side="left", padx=(0, 12))
        except Exception:
            pass
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text=APP_NAME, font=font(20, True), text_color=TEXT).pack(anchor="w")
        self.sub_lbl = ctk.CTkLabel(titles, text="DDC/CI", font=font(12), text_color=MUTED)
        self.sub_lbl.pack(anchor="w")

        lang = ctk.CTkSegmentedButton(head, values=["PT", "EN"], command=self.set_lang, height=30,
                                      fg_color=CARD, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
                                      unselected_color=CARD, unselected_hover_color=CARD2, text_color=TEXT,
                                      font=font(12, True))
        lang.set(LANG.upper())
        lang.pack(side="right")
        ctk.CTkButton(head, text="⟳", width=36, height=34, corner_radius=10, fg_color=CARD2, hover_color=HOVER,
                      text_color=TEXT, font=font(16, True), command=self.load).pack(side="right", padx=8)
        if self.monitors:
            self.mon_menu = Dropdown(head, list(enumerate(self.mon_labels)), self.mon_idx, self.pick_monitor, width=210)
            self.mon_menu.pack(side="right")

        # tabs
        self.tabs = ctk.CTkTabview(
            self, fg_color=BG, border_width=0, corner_radius=14, segmented_button_fg_color=CARD,
            segmented_button_selected_color=ACCENT, segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=CARD, segmented_button_unselected_hover_color=CARD2, text_color=TEXT)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(2, 0))
        try:
            self.tabs._segmented_button.configure(font=font(13, True), height=34)
        except Exception:
            pass
        names = {
            "image": T("Imagem", "Picture"), "color": T("Cores", "Color"), "input": T("Entrada", "Input"),
            "adv": T("Avançado", "Advanced"), "prof": T("Perfis", "Profiles"),
        }
        for key, name in names.items():
            self.tabs.add(name)
            sf = ctk.CTkScrollableFrame(self.tabs.tab(name), fg_color="transparent", scrollbar_button_color=BORDER,
                                        scrollbar_button_hover_color=MUTED)
            sf.pack(fill="both", expand=True)
            self.page[key] = sf
        self.adv_dyn = ctk.CTkFrame(self.page["adv"], fg_color="transparent")
        self.adv_dyn.pack(fill="x")
        self.build_scanner(self.page["adv"])
        self.build_profiles(self.page["prof"])
        if self.err:
            self.status(T("Erro ao listar monitores: ", "Could not list monitors: ") + self.err, "err")

    def set_lang(self, value):
        global LANG
        LANG = value.lower()
        save_config(lang=LANG)
        for k in (COLOR_PRESETS, DISPLAY_MODES):
            pass
        # tables with translated labels are rebuilt on restart; rebuild what we can now
        COLOR_PRESETS.update({0x02: T("Nativo", "Native"), 0x0B: T("Usuário 1", "User 1"),
                              0x0C: T("Usuário 2", "User 2"), 0x0D: T("Usuário 3", "User 3")})
        DISPLAY_MODES.update({0x00: T("Padrão", "Standard"), 0x01: T("Produtividade", "Productivity"),
                              0x02: T("Misto", "Mixed"), 0x03: T("Filme", "Movie"), 0x04: T("Usuário", "User"),
                              0x05: T("Jogos", "Games"), 0x06: T("Esportes", "Sports"),
                              0x07: T("Profissional", "Professional")})
        self.mon_labels = [f"{T('Monitor', 'Monitor')} {i + 1}" for i in range(len(self.monitors))]
        self.dim_pct = 0
        self.build_ui()
        self.load()

    def pick_monitor(self, idx):
        self.mon_idx = idx
        self.load()

    # ---- dynamic content helpers
    def clear_dynamic(self):
        for k in ("image", "color", "input"):
            for w in self.page[k].winfo_children():
                w.destroy()
        for w in self.adv_dyn.winfo_children():
            w.destroy()

    def note(self, page, text, title=None):
        c = Card(self.page[page], title)
        c.pack(fill="x", pady=6)
        ctk.CTkLabel(c.body, text=text, font=font(13), text_color=MUTED, wraplength=640, justify="left").pack(anchor="w")
        return c

    # ---- load / populate
    def load(self):
        self.token += 1
        tok = self.token
        self.clear_dynamic()
        self.values = {}
        if not self.monitors:
            self.populate(parse_caps(None), {}, tok)
            return
        self.ddc = Ddc(self.monitors[self.mon_idx])
        self.note("image", T("Lendo o monitor…", "Reading monitor…"))
        self.status(T("Lendo o monitor…", "Reading monitor…"))
        ddc = self.ddc

        def job():
            info = parse_caps(ddc.capabilities())
            data = {}
            for code in PROBE:
                r = ddc.try_get(code, tries=2 if (not info["codes"] or code in info["codes"]) else 1)
                if r:
                    data[code] = r
            self.ui(lambda: self.populate(info, data, tok))

        self.bg(job)

    def populate(self, info, data, tok):
        if tok != self.token:
            return
        self.info = info
        self.values = {}
        self.clear_dynamic()
        if info["model"] or info["mccs"]:
            bits = [info["model"], f"MCCS {info['mccs']}" if info["mccs"] else None]
            self.sub_lbl.configure(text=" · ".join(b for b in bits if b))
        else:
            self.sub_lbl.configure(text="DDC/CI")
        if not data:
            self.empty_state()
            self.status(T("Sem resposta DDC/CI", "No DDC/CI response"), "err")
            return

        allowed = info["allowed"]
        groups = {}

        def card(page, group):
            key = (page, group)
            if key not in groups:
                c = Card(self.page[page], tr(group) if group else None)
                c.pack(fill="x", pady=6)
                groups[key] = c
            return groups[key]

        # choices first (mode / preset / input)
        for code, label, page, table in CHOICES:
            if code not in data:
                continue
            cur = data[code][0] & 0xFF
            vals = list(allowed.get(code) or table.keys())
            generic = code not in allowed
            if cur not in vals:
                vals.insert(0, cur)
            options = [(v, table.get(v, f"0x{v:02X}")) for v in vals]
            c = card(page, label)
            self.values[code] = cur
            tall = 52 if code == 0x60 else 40
            make_choice(c.body, options, cur, lambda v, k=code: self.on_choice(k, v), tall).pack(fill="x")
            if generic:
                ctk.CTkLabel(c.body, text=T("Lista genérica: o monitor não informou os valores aceitos.",
                                            "Generic list: the monitor did not report its accepted values."),
                             font=font(11), text_color=MUTED).pack(anchor="w", pady=(6, 0))
            if code == 0x60:
                ctk.CTkLabel(c.body, text=T("Cuidado: trocar para uma entrada sem sinal deixa a tela preta e você não "
                                            "consegue voltar por este programa.",
                                            "Careful: switching to an input with no signal blanks the screen and you "
                                            "can't switch back from this app."),
                             font=font(11), text_color=MUTED, wraplength=640, justify="left").pack(anchor="w", pady=(6, 0))

        # sliders
        for code, label, page, group in SLIDERS:
            r = data.get(code)
            if not r or r[1] <= 0:
                continue
            cur, mx = r
            cur = min(cur, mx)
            self.values[code] = cur
            row = SliderRow(card(page, group).body, tr(label), cur, mx, lambda v, k=code: self.on_slider(k, v))
            row.pack(fill="x", pady=5)

        # white-point preview next to the RGB gain
        if all(c in data for c in GAIN_CODES):
            body = card("color", G_GAIN).body
            prev = ctk.CTkFrame(body, fg_color="transparent")
            prev.pack(fill="x", pady=(8, 0))
            ctk.CTkLabel(prev, text=T("Prévia do branco", "White preview"), font=font(12), text_color=MUTED).pack(side="left")
            self.swatch = ctk.CTkFrame(prev, width=90, height=22, corner_radius=8, fg_color="#ffffff")
            self.swatch.pack(side="right")
            self.update_swatch()

        # toggles
        for code, label, page, group, on_v, off_v in TOGGLES:
            if code not in data:
                continue
            cur = data[code][0] & 0xFF
            self.values[code] = cur
            parent = self.adv_dyn if page == "adv" else card(page, group).body
            if page == "adv":
                c = Card(parent, T("Controles do monitor", "Monitor controls"))
                c.pack(fill="x", pady=6)
                parent = c.body
                self.adv_card = c
            sw = ctk.CTkSwitch(parent, text=tr(label), font=font(13), text_color=TEXT, progress_color=ACCENT,
                               button_color=KNOB, button_hover_color="#ffffff", fg_color="#253148")
            sw.configure(command=lambda s=sw, k=code, a=on_v, b=off_v: self.write(k, a if s.get() else b))
            if cur == on_v:
                sw.select()
            sw.pack(anchor="w", pady=4)

        # resets
        shown = [(c, l) for c, l in RESETS if c in data or c in info["codes"]]
        if shown:
            if not hasattr(self, "adv_card") or not self.adv_card.winfo_exists() or self.adv_card.master is not self.adv_dyn:
                c = Card(self.adv_dyn, T("Controles do monitor", "Monitor controls"))
                c.pack(fill="x", pady=6)
                self.adv_card = c
            row = ctk.CTkFrame(self.adv_card.body, fg_color="transparent")
            row.pack(fill="x", pady=(8, 0))
            for code, label in shown:
                ctk.CTkButton(row, text=tr(label), height=34, corner_radius=10, border_width=1,
                              fg_color="#1d1117" if code == 0x04 else CARD2,
                              border_color=DANGER if code == 0x04 else BORDER,
                              hover_color="#2b1820" if code == 0x04 else HOVER,
                              text_color=DANGER if code == 0x04 else TEXT, font=font(12),
                              command=lambda k=code, l=label: self.reset(k, l)).pack(side="left", padx=(0, 8))

        self.add_dim_card()
        if not self.page["input"].winfo_children():
            self.note("input", T("Este monitor não informou a fonte de entrada via DDC/CI.",
                                 "This monitor did not report an input source over DDC/CI."))
        if not self.page["color"].winfo_children():
            self.note("color", T("Este monitor não expõe controles de cor via DDC/CI.",
                                 "This monitor exposes no color controls over DDC/CI."))
        self.status(T(f"Monitor lido: {len(data)} controles respondem", f"Monitor read: {len(data)} controls respond"), "ok")

    def empty_state(self):
        msg = T(
            "Nenhum controle respondeu via DDC/CI.\n\n"
            "• Ative a opção DDC/CI no menu do monitor, se existir.\n"
            "• Teste com cabo DisplayPort/HDMI direto (sem adaptador, dock ou KVM).\n"
            "• Alguns monitores/notebooks não suportam DDC/CI.\n"
            "• Use a aba Avançado → Escanear para ver o que o monitor responde.\n"
            "• Plano B: o escurecer por software abaixo.",
            "No control responded over DDC/CI.\n\n"
            "• Enable the DDC/CI option in the monitor menu, if there is one.\n"
            "• Try a direct DisplayPort/HDMI cable (no adapter, dock or KVM).\n"
            "• Some monitors/laptops do not support DDC/CI.\n"
            "• Use Advanced → Scan to see what the monitor answers.\n"
            "• Plan B: the software dimmer below.")
        self.note("image", msg, T("Sem resposta DDC/CI", "No DDC/CI response"))
        self.add_dim_card()
        self.note("color", T("Sem DDC/CI.", "No DDC/CI."))
        self.note("input", T("Sem DDC/CI.", "No DDC/CI."))

    # ---- callbacks
    def on_slider(self, code, v):
        self.values[code] = v
        if code in GAIN_CODES:
            self.update_swatch()
        if code in self.timers:
            self.after_cancel(self.timers[code])
        self.timers[code] = self.after(150, lambda: self.write(code, v))

    def update_swatch(self):
        try:
            g = [self.values.get(c, 0) for c in GAIN_CODES]
            m = max(g) or 1
            r, gg, b = (int(255 * x / m) for x in g)
            self.swatch.configure(fg_color=f"#{r:02x}{gg:02x}{b:02x}")
        except Exception:
            pass

    def on_choice(self, code, v):
        if code == 0x60 and not ask(
                self, T("Trocar entrada", "Switch input"),
                T("Se a entrada escolhida não tiver sinal, a tela fica preta e você não consegue voltar por aqui.\n\n"
                  "Continuar?",
                  "If the chosen input has no signal the screen goes black and you can't switch back from here.\n\n"
                  "Continue?"),
                yes=T("Trocar", "Switch")):
            return False
        self.write(code, v)
        return None

    def write(self, code, v):
        if not self.ddc:
            return
        self.values[code] = v
        ddc = self.ddc

        def job():
            try:
                ddc.set(code, v)
                self.status(f"0x{code:02X} {VCP_NAMES.get(code, '')} = {v}", "ok")
            except Exception as e:
                self.status(f"0x{code:02X}: {e}", "err")

        self.bg(job)

    def reset(self, code, label):
        if not self.ddc:
            return
        if not ask(self, T("Restaurar", "Reset"), T(f"Executar: {tr(label)}?", f"Run: {tr(label)}?"),
                   yes=T("Restaurar", "Reset"), danger=True):
            return
        ddc = self.ddc

        def job():
            try:
                ddc.set(code, 1)
                time.sleep(1.5)
                self.ui(self.load)
            except Exception as e:
                self.status(f"0x{code:02X}: {e}", "err")

        self.bg(job)

    # ---- software dimmer
    def add_dim_card(self):
        c = Card(self.page["image"], T("Escurecer por software", "Software dimmer"))
        c.pack(fill="x", pady=6)
        SliderRow(c.body, T("Escurecer %", "Dim %"), self.dim_pct, 80, self.dim).pack(fill="x")
        ctk.CTkLabel(
            c.body, font=font(11), text_color=MUTED, wraplength=640, justify="left",
            text=T("Filtro preto por cima de todas as telas, útil quando o DDC/CI não funciona. "
                   "Captura de tela/monitor no OBS sai escurecida; use captura de jogo ou de janela.",
                   "Black overlay on top of all screens, useful when DDC/CI doesn't work. Screen/display capture "
                   "in OBS will be dimmed too; use game or window capture.")).pack(anchor="w", pady=(6, 0))

    def dim(self, pct):
        self.dim_pct = pct
        if not IS_WIN:
            return
        if pct <= 0:
            if self.overlay is not None:
                self.overlay.destroy()
                self.overlay = None
            return
        if self.overlay is None:
            u = ctypes.windll.user32
            x, y, w, h = (u.GetSystemMetrics(i) for i in (76, 77, 78, 79))
            ov = ctk.CTkToplevel(self, fg_color="black")
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            ov.geometry(f"{w}x{h}{x:+d}{y:+d}")
            ov.update_idletasks()
            hwnd = u.GetParent(ov.winfo_id()) or ov.winfo_id()
            style = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20)  # layered + click-through
            self.overlay = ov
        self.overlay.attributes("-alpha", pct / 100)

    # ---- advanced: scanner
    def build_scanner(self, parent):
        c = Card(parent, T("Scanner de códigos VCP", "VCP code scanner"))
        c.pack(fill="x", pady=6)
        bar = ctk.CTkFrame(c.body, fg_color="transparent")
        bar.pack(fill="x")
        ctk.CTkButton(bar, text=T("Escanear 0x00–0xFF", "Scan 0x00–0xFF"), height=34, corner_radius=10,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, font=font(12, True), command=self.scan).pack(side="left")
        ctk.CTkButton(bar, text="Capabilities", height=34, corner_radius=10, fg_color=CARD2, hover_color=HOVER,
                      text_color=TEXT, font=font(12), command=self.show_caps).pack(side="left", padx=8)
        self.prog = ctk.CTkLabel(bar, text="", font=font(12), text_color=MUTED)
        self.prog.pack(side="left", padx=6)

        style = ttk.Style(self)
        style.theme_use("clam")
        fam = FAMILY or "TkDefaultFont"
        style.configure("Dark.Treeview", background=CARD2, fieldbackground=CARD2, foreground=TEXT, borderwidth=0,
                        rowheight=26, font=(fam, 10))
        style.layout("Dark.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no white border
        style.configure("Dark.Treeview.Heading", background=CARD, foreground=MUTED, relief="flat",
                        font=(fam, 10, "bold"))
        style.map("Dark.Treeview", background=[("selected", ACCENT_DIM)], foreground=[("selected", "#ffffff")])
        style.map("Dark.Treeview.Heading", background=[("active", CARD)])

        wrap = ctk.CTkFrame(c.body, fg_color=CARD2, corner_radius=10)
        wrap.pack(fill="x", pady=(10, 0))
        self.tree = ttk.Treeview(wrap, columns=("code", "name", "cur", "max"), show="headings", height=10,
                                 style="Dark.Treeview")
        for col, title, w in (("code", T("Código", "Code"), 70), ("name", T("Nome", "Name"), 250),
                              ("cur", T("Atual", "Current"), 80), ("max", T("Máx", "Max"), 80)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, anchor="w")
        sb = ctk.CTkScrollbar(wrap, command=self.tree.yview, button_color=BORDER, button_hover_color=MUTED)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb.pack(side="left", fill="y", pady=6, padx=(0, 4))
        self.tree.bind("<Double-1>", self.edit_row)
        ctk.CTkLabel(c.body, text=T("Duplo clique numa linha para editar o valor.", "Double-click a row to edit its value."),
                     font=font(11), text_color=MUTED).pack(anchor="w", pady=(6, 0))

        m = Card(parent, T("Ler / escrever manualmente", "Manual read / write"))
        m.pack(fill="x", pady=6)
        row = ctk.CTkFrame(m.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text=T("Código (hex)", "Code (hex)"), font=font(12), text_color=MUTED).pack(side="left")
        self.m_code = ctk.CTkEntry(row, width=80, height=34, fg_color=CARD2, border_color=BORDER, text_color=TEXT)
        self.m_code.pack(side="left", padx=(8, 14))
        ctk.CTkLabel(row, text=T("Valor", "Value"), font=font(12), text_color=MUTED).pack(side="left")
        self.m_val = ctk.CTkEntry(row, width=100, height=34, fg_color=CARD2, border_color=BORDER, text_color=TEXT)
        self.m_val.pack(side="left", padx=(8, 14))
        ctk.CTkButton(row, text=T("Ler", "Read"), width=70, height=34, corner_radius=10, fg_color=CARD2,
                      hover_color=HOVER, text_color=TEXT, font=font(12), command=self.manual_read).pack(side="left")
        ctk.CTkButton(row, text=T("Escrever", "Write"), width=90, height=34, corner_radius=10, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, font=font(12, True), command=self.manual_write).pack(side="left", padx=8)

    def scan(self):
        if not self.ddc:
            return
        self.tree.delete(*self.tree.get_children())
        ddc = self.ddc

        def job():
            found = 0
            for code in range(0x100):
                r = ddc.try_get(code, tries=1)
                if r:
                    found += 1
                    name = VCP_NAMES.get(code, T("(fabricante/desconhecido)", "(vendor/unknown)"))
                    self.ui(lambda c=code, n=name, r=r: self.tree.insert(
                        "", "end", iid=f"{c:02X}", values=(f"0x{c:02X}", n, r[0], r[1])))
                self.ui(lambda c=code: self.prog.configure(text=f"{c + 1}/256"))
            self.ui(lambda: self.prog.configure(
                text=T(f"Pronto: {found} códigos respondem", f"Done: {found} codes respond")))

        self.bg(job)

    def edit_row(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        code = int(sel[0], 16)
        cur = self.tree.item(sel[0], "values")[2]
        txt = ask(self, T("Editar valor", "Edit value"),
                  T(f"Novo valor para 0x{code:02X} (atual {cur}):", f"New value for 0x{code:02X} (current {cur}):"),
                  entry=True, default=str(cur))
        v = parse_val(txt) if txt is not None else None
        if v is not None:
            self.confirm_write(code, v)

    def confirm_write(self, code, v):
        if (code in RISKY or code >= 0xE0) and not ask(
                self, T("Atenção", "Warning"),
                T(f"0x{code:02X} é um controle sensível (reset/entrada/energia/fabricante).\nEscrever {v} mesmo assim?",
                  f"0x{code:02X} is a sensitive control (reset/input/power/vendor).\nWrite {v} anyway?"),
                yes=T("Escrever", "Write"), danger=True):
            return
        self.write(code, v)

    def manual_read(self):
        code = parse_val("0x" + self.m_code.get().lower().replace("0x", ""))
        if code is None or not self.ddc:
            return
        ddc = self.ddc

        def job():
            r = ddc.try_get(code)
            self.status(f"0x{code:02X}: {T('atual', 'current')}={r[0]} max={r[1]}" if r
                        else f"0x{code:02X}: {T('sem resposta', 'no response')}", "ok" if r else "err")

        self.bg(job)

    def manual_write(self):
        code = parse_val("0x" + self.m_code.get().lower().replace("0x", ""))
        v = parse_val(self.m_val.get())
        if code is None or v is None:
            self.status(T("Código/valor inválido", "Invalid code/value"), "err")
            return
        self.confirm_write(code, v)

    def show_caps(self):
        if not self.ddc:
            return
        self.status(T("Lendo capabilities (pode levar alguns segundos)…", "Reading capabilities (may take a few seconds)…"))
        ddc = self.ddc

        def job():
            raw = ddc.raw_caps or ddc.capabilities()
            txt = pprint.pformat(raw, width=100) if raw else T("Este monitor não informou capabilities.",
                                                              "This monitor did not report capabilities.")
            self.ui(lambda: self.caps_window(txt))
            self.status(T("Pronto", "Ready"), "ok")

        self.bg(job)

    def caps_window(self, txt):
        w = ctk.CTkToplevel(self, fg_color=CARD)
        w.title("Capabilities")
        w.geometry("660x500")
        w.transient(self)
        box = ctk.CTkTextbox(w, fg_color=CARD2, text_color=TEXT, border_width=0, corner_radius=10,
                             font=ctk.CTkFont(family="Consolas" if IS_WIN else "monospace", size=12))
        box.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        box.insert("1.0", txt)
        ctk.CTkButton(w, text=T("Copiar", "Copy"), height=34, corner_radius=10, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, font=font(12, True),
                      command=lambda: (self.clipboard_clear(), self.clipboard_append(txt))).pack(pady=(0, 14))

    # ---- profiles
    def build_profiles(self, parent):
        c = Card(parent, T("Perfis", "Profiles"))
        c.pack(fill="x", pady=6)
        self.prof_box = ctk.CTkFrame(c.body, fg_color="transparent")
        self.prof_box.pack(fill="x")
        bar = ctk.CTkFrame(c.body, fg_color="transparent")
        bar.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(bar, text=T("Salvar atual como…", "Save current as…"), height=34, corner_radius=10,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, font=font(12, True),
                      command=self.prof_save).pack(side="left")
        ctk.CTkButton(bar, text=T("Aplicar", "Apply"), height=34, corner_radius=10, fg_color=CARD2, hover_color=HOVER,
                      text_color=TEXT, font=font(12), command=self.prof_apply).pack(side="left", padx=8)
        ctk.CTkButton(bar, text=T("Excluir", "Delete"), height=34, corner_radius=10, fg_color="#1d1117",
                      border_width=1, border_color=DANGER, hover_color="#2b1820", text_color=DANGER, font=font(12),
                      command=self.prof_delete).pack(side="left")
        h = Card(parent, T("Aplicar ao ligar o PC", "Apply at startup"))
        h.pack(fill="x", pady=6)
        ctk.CTkLabel(
            h.body, font=font(12), text_color=MUTED, justify="left", wraplength=640,
            text=T("Aperte Win+R, digite shell:startup e crie um atalho para o programa com este destino:\n"
                   "MonitorController.exe --profile NOME_DO_PERFIL\n"
                   "Em PC com mais de um monitor, adicione --monitor 2 (ou 3…) para escolher qual.",
                   "Press Win+R, type shell:startup and create a shortcut to the program with this target:\n"
                   "MonitorController.exe --profile PROFILE_NAME\n"
                   "With more than one monitor, add --monitor 2 (or 3…) to choose which one.")).pack(anchor="w")
        self.prof_refresh()

    def prof_refresh(self):
        for w in self.prof_box.winfo_children():
            w.destroy()
        names = list(load_profiles())
        if self.sel_profile not in names:
            self.sel_profile = None
        if not names:
            ctk.CTkLabel(self.prof_box, text=T("Nenhum perfil salvo ainda.", "No saved profiles yet."),
                         font=font(12), text_color=MUTED).pack(anchor="w")
            return
        Tiles(self.prof_box, [(n, n) for n in names], self.sel_profile, self._prof_pick, columns=3).pack(fill="x")

    def _prof_pick(self, name):
        self.sel_profile = name

    def prof_save(self):
        if not self.values:
            self.status(T("Nada lido ainda para salvar", "Nothing read yet to save"), "err")
            return
        name = ask(self, T("Novo perfil", "New profile"), T("Nome do perfil:", "Profile name:"), entry=True)
        if not name or not name.strip():
            return
        p = load_profiles()
        p[name.strip()] = {f"0x{k:02X}": v for k, v in self.values.items()}
        save_profiles(p)
        self.sel_profile = name.strip()
        self.prof_refresh()
        self.status(T(f"Perfil '{name.strip()}' salvo", f"Profile '{name.strip()}' saved"), "ok")

    def prof_apply(self):
        if not self.sel_profile or not self.ddc:
            return
        name = self.sel_profile
        data = load_profiles().get(name, {})
        ddc = self.ddc

        def job():
            for code, v in data.items():
                try:
                    ddc.set(int(code, 16), v)
                except Exception as e:
                    self.status(f"{code}: {e}", "err")
                time.sleep(0.1)
            self.status(T(f"Perfil '{name}' aplicado", f"Profile '{name}' applied"), "ok")
            self.ui(self.load)

        self.bg(job)

    def prof_delete(self):
        if not self.sel_profile:
            return
        if not ask(self, T("Excluir perfil", "Delete profile"),
                   T(f"Excluir o perfil '{self.sel_profile}'?", f"Delete profile '{self.sel_profile}'?"),
                   yes=T("Excluir", "Delete"), danger=True):
            return
        p = load_profiles()
        p.pop(self.sel_profile, None)
        save_profiles(p)
        self.sel_profile = None
        self.prof_refresh()


def main():
    global LANG
    args = sys.argv[1:]
    if "--lang" in args:
        i = args.index("--lang")
        if i + 1 < len(args) and args[i + 1] in ("pt", "en"):
            LANG = args[i + 1]
    if "--profile" in args:
        i = args.index("--profile")
        name = args[i + 1] if i + 1 < len(args) else ""
        idx = int(args[args.index("--monitor") + 1]) - 1 if "--monitor" in args else 0
        cli_apply(name, idx)
        return
    App(demo="--demo" in args).mainloop()


if __name__ == "__main__":
    main()
