"""Tk window + system-tray icon. Closing the window hides it to the tray; Quit stops the agent."""
import platform
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw, ImageFont

from . import __version__, printers
from .api import AgentApi, ApiError
from .config import Settings
from .runner import AgentRunner

GOLD, BLACK, PANEL, TEXT, GREEN, RED = "#d4af37", "#0b0b0b", "#171717", "#eeeeee", "#34d399", "#fb7185"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "PrintBotAgent"


def make_icon(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), BLACK)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, size - 3, size - 3), radius=size // 5, outline=GOLD, width=max(2, size // 20))
    try:
        font = ImageFont.truetype("arialbd.ttf", int(size * 0.62))
    except OSError:
        font = ImageFont.load_default()
    d.text((size / 2, size / 2), "P", fill=GOLD, font=font, anchor="mm")
    return img


def _autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def _set_autostart(on: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" -m printbot_agent'
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, exe)
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass


class App:
    def __init__(self, start_hidden: bool = False):
        self.settings = Settings.load()
        self.runner = AgentRunner(self.settings, printers.discover, printers.print_pdf)
        self.root = tk.Tk()
        self.root.title("PrintBot Agent")
        self.root.geometry("560x520")
        self.root.configure(bg=BLACK)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self._style()
        self.frame = None
        self.tray = pystray.Icon("PrintBotAgent", make_icon(), "PrintBot Agent", menu=pystray.Menu(
            pystray.MenuItem("Open", lambda: self.root.after(0, self.show), default=True),
            pystray.MenuItem("Quit", lambda: self.root.after(0, self.quit))))
        self.tray.run_detached()
        self._render()
        if self.settings.is_paired:
            self.runner.start()
        if start_hidden and self.settings.is_paired:
            self.root.withdraw()
        self.root.after(1000, self._tick)

    def _style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(".", background=BLACK, foreground=TEXT, fieldbackground=PANEL)
        s.configure("TButton", background=GOLD, foreground=BLACK, padding=8, borderwidth=0)
        s.map("TButton", background=[("active", "#e6c35c")])
        s.configure("TEntry", insertcolor=TEXT, padding=6)
        s.configure("TCheckbutton", background=BLACK)
        s.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground=GOLD)
        s.configure("Sub.TLabel", foreground="#9a9a9a")

    # ── views ──
    def _render(self):
        if self.frame is not None:
            self.frame.destroy()
        self.frame = ttk.Frame(self.root, padding=24)
        self.frame.pack(fill="both", expand=True)
        (self._home if self.settings.is_paired else self._pair)()
        self._paired_view = self.settings.is_paired

    def _pair(self):
        f = self.frame
        ttk.Label(f, text="PrintBot Agent", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text="In the dashboard open Print Agents → Add Agent, then enter the code here.",
                  style="Sub.TLabel", wraplength=500).pack(anchor="w", pady=(4, 20))
        ttk.Label(f, text="Server address").pack(anchor="w")
        self.url_var = tk.StringVar(value=self.settings.server_url or "http://localhost:8000")
        ttk.Entry(f, textvariable=self.url_var).pack(fill="x", pady=(2, 12))
        ttk.Label(f, text="Pairing code").pack(anchor="w")
        self.code_var = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.code_var, font=("Consolas", 14))
        e.pack(fill="x", pady=(2, 16))
        e.bind("<Return>", lambda _: self._do_pair())
        self.pair_btn = ttk.Button(f, text="Pair this PC", command=self._do_pair)
        self.pair_btn.pack(anchor="w")
        self.pair_msg = ttk.Label(f, text="", foreground=RED, wraplength=500)
        self.pair_msg.pack(anchor="w", pady=10)
        e.focus_set()

    def _do_pair(self):
        url = self.url_var.get().strip().rstrip("/")
        code = self.code_var.get().strip().upper()
        if not url.startswith(("http://", "https://")) or not code:
            self.pair_msg.config(text="Enter a server address starting with http:// or https:// and the code.")
            return
        self.pair_btn.state(["disabled"])
        self.pair_msg.config(text="Pairing…", foreground=TEXT)

        def work():
            try:
                token, name = AgentApi(url).pair(code, "windows", platform.node() or "Windows PC", __version__)
                self.root.after(0, lambda: self._paired(url, token, name))
            except ApiError as e:
                self.root.after(0, lambda: (self.pair_msg.config(text=str(e), foreground=RED),
                                            self.pair_btn.state(["!disabled"])))
        threading.Thread(target=work, daemon=True).start()

    def _paired(self, url, token, name):
        self.settings.server_url, self.settings.token, self.settings.agent_name = url, token, name
        self.settings.save()
        self.runner.start()
        self._render()

    def _home(self):
        f = self.frame
        ttk.Label(f, text=self.settings.agent_name or "PrintBot Agent", style="Title.TLabel").pack(anchor="w")
        self.status = ttk.Label(f, text="")
        self.status.pack(anchor="w", pady=(2, 12))
        ttk.Label(f, text="Printers reported to the dashboard", style="Sub.TLabel").pack(anchor="w")
        self.printer_list = tk.Listbox(f, height=5, bg=PANEL, fg=TEXT, relief="flat", highlightthickness=0,
                                       selectbackground=PANEL, activestyle="none")
        self.printer_list.pack(fill="x", pady=(2, 12))
        ttk.Label(f, text="Activity", style="Sub.TLabel").pack(anchor="w")
        self.log_box = tk.Text(f, height=10, bg=PANEL, fg=TEXT, relief="flat", highlightthickness=0, state="disabled")
        self.log_box.tag_config("err", foreground=RED)
        self.log_box.pack(fill="both", expand=True, pady=(2, 12))
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.auto_var = tk.BooleanVar(value=_autostart_enabled())
        ttk.Checkbutton(row, text="Start with Windows", variable=self.auto_var, command=self._toggle_auto).pack(side="left")
        ttk.Button(row, text="Unpair", command=self._unpair).pack(side="right")
        self._tick()

    def _toggle_auto(self):
        try:
            _set_autostart(self.auto_var.get())
        except OSError as e:
            self.auto_var.set(not self.auto_var.get())
            messagebox.showerror("PrintBot Agent", f"Could not change startup setting: {e}")

    def _unpair(self):
        if messagebox.askyesno("PrintBot Agent", "Unpair this PC? Remove the agent in the dashboard too."):
            self.runner.stop()
            self.settings.clear_pairing()
            self._render()

    def _tick(self):
        r = self.runner
        if self.settings.is_paired != getattr(self, "_paired_view", None):
            self._render()  # e.g. revoked from the dashboard
        elif self.settings.is_paired and getattr(self, "status", None) is not None:
            if r.current_job:
                text, color = f"Printing {r.current_job}", GOLD
            elif r.online:
                text, color = f"Online · {r.printed_count} printed this session", GREEN
            else:
                text, color = "Offline · cannot reach server", RED
            self.status.config(text="● " + text, foreground=color)
            self.printer_list.delete(0, "end")
            for p in r.printers:
                self.printer_list.insert("end", f"{p.name}   ({'colour' if p.color else 'B/W'}"
                                                f"{', ' + p.state if p.state == 'error' else ''})")
            self.log_box.config(state="normal")
            self.log_box.delete("1.0", "end")
            for t, msg, err in list(r.log)[:60]:
                self.log_box.insert("end", f"{t:%H:%M:%S}  {msg}\n", "err" if err else "")
            self.log_box.config(state="disabled")
        self.tray.title = "PrintBot Agent — " + ("online" if r.online else "offline")
        self.root.after(1000, self._tick)

    # ── window / tray ──
    def hide(self):
        self.root.withdraw()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit(self):
        self.runner.stop()
        self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def single_instance() -> bool:
    """False if another copy is already running (it is brought to the tray instead of duplicated)."""
    try:
        import win32api
        import win32event
        import winerror
        global _mutex
        _mutex = win32event.CreateMutex(None, False, "Local\\PrintBotAgentSingleton")
        return win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS
    except ImportError:
        return True


def main():
    if not single_instance():
        return
    App(start_hidden="--hidden" in sys.argv).run()
