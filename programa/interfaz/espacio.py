"""Cabecera espacial de la ventana: cielo con nebulosas, estrellas que
parpadean, un planeta con anillo, el titulo y el estado (ADB, version).

Todo se dibuja en un Canvas, asi que se redibuja al cambiar el ancho."""
from __future__ import annotations

import random
import tkinter as tk

from interfaz.tema import AMBAR, FONDO, FONDO_AYUDA, LETRA, ROJO, SUAVE, TEAL, TEXTO, VERDE, VIOLETA, titular

ALTO = 112


def _mezcla(a: str, b: str, f: float) -> str:
    """Color entre a y b (f=0 -> a, f=1 -> b)."""
    a1 = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b1 = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a1, b1))


class _Texto:
    """Un texto del lienzo que se usa como una etiqueta: .config(text=, fg=)."""

    def __init__(self, lienzo, item):
        self.lienzo, self.item = lienzo, item

    def config(self, text=None, fg=None, **_):
        if text is not None:
            self.lienzo.itemconfigure(self.item, text=text)
        if fg is not None:
            self.lienzo.itemconfigure(self.item, fill=fg)
        self.lienzo.recolocar()

    configure = config


class CieloEstelar(tk.Canvas):
    def __init__(self, master, subtitulo: str, version: str, adb_ok: bool, adb_ruta: str,
                 al_actualizar=None):
        super().__init__(master, height=ALTO, bg=FONDO, highlightthickness=0, bd=0)
        self.azar = random.Random(7)
        self._ancho = 0
        self._estrellas = []          # (item, color brillante, color apagado)
        self._tip = None
        self.subtitulo = subtitulo
        # textos fijos (se colocan en recolocar)
        self.t_brillo = self.create_text(0, 0, text="N O V A B O T", fill=_mezcla(FONDO, TEAL, 0.35),
                                         font=titular(24), anchor="nw", tags="texto")
        self.t_titulo = self.create_text(0, 0, text="N O V A B O T", fill=TEXTO, font=titular(24),
                                         anchor="nw", tags="texto")
        self.t_sub = self.create_text(0, 0, text=subtitulo, fill=SUAVE, font=(LETRA, 9),
                                      anchor="nw", tags="texto")
        self.t_resumen = self.create_text(0, 0, text="", fill=TEXTO, font=titular(12, False),
                                          anchor="ne", tags="texto")
        self.t_adb = self.create_text(0, 0, text="● ADB listo" if adb_ok else "● ADB no encontrado",
                                      fill=VERDE if adb_ok else ROJO, font=(LETRA, 8), anchor="ne",
                                      tags=("texto", "adb"))
        self.t_version = self.create_text(0, 0, text=f"v{version}", fill=SUAVE, font=(LETRA, 8),
                                          anchor="ne", tags="texto")
        self.t_actualizar = self.create_text(0, 0, text="Actualizar desde archivo…", fill=TEAL,
                                             font=(LETRA, 8, "underline"), anchor="ne",
                                             tags=("texto", "actualizar"))
        self.lbl_resumen = _Texto(self, self.t_resumen)
        self.lbl_adb = _Texto(self, self.t_adb)
        if al_actualizar:
            self.tag_bind("actualizar", "<Button-1>", lambda e: al_actualizar())
        self._ayuda("actualizar", "Instala una versión nueva sin perder ajustes ni estadísticas.")
        self._ayuda("adb", f"ADB: {adb_ruta or 'no encontrado'}")
        self.tag_bind("actualizar", "<Enter>", lambda e: self.config(cursor="hand2"), add="+")
        self.tag_bind("actualizar", "<Leave>", lambda e: self.config(cursor=""), add="+")
        self.bind("<Configure>", self._redibujar)
        self.after(700, self._parpadeo)

    # ------------------------------------------------------------ dibujo --
    def _redibujar(self, e=None):
        w = max(self.winfo_width(), 600)
        if w == self._ancho:
            return
        self._ancho = w
        self.delete("fondo")
        azar = random.Random(7)
        # degradado vertical del cielo
        arriba, medio, abajo = "#03050f", "#0a1134", "#120d36"
        for i in range(ALTO):
            f = i / (ALTO - 1)
            col = _mezcla(arriba, medio, f * 2) if f < 0.5 else _mezcla(medio, abajo, (f - 0.5) * 2)
            self.create_line(0, i, w, i, fill=col, tags="fondo")
        # nebulosas: circulos concentricos que se funden con el cielo
        for cx, cy, r, col in ((w * 0.30, 70, 120, "#2a1a6e"), (w * 0.55, 20, 90, "#0f3a6b"),
                               (w * 0.85, 90, 110, "#3a1555")):
            for k in range(14, 0, -1):
                rr = r * k / 14
                self.create_oval(cx - rr * 1.6, cy - rr * 0.55, cx + rr * 1.6, cy + rr * 0.55,
                                 fill=_mezcla("#0a1134", col, (1 - k / 14) * 0.9 + 0.1),
                                 outline="", tags="fondo")
        # estrellas
        self._estrellas = []
        for _ in range(int(w / 7)):
            x, y = azar.uniform(0, w), azar.uniform(0, ALTO - 6)
            tam = azar.choice((0.6, 0.6, 0.6, 1.0, 1.0, 1.6))
            col = azar.choice(("#ffffff", "#cdd8ff", "#9fd8ff", TEAL, "#ffe2a8"))
            it = self.create_oval(x - tam, y - tam, x + tam, y + tam, fill=col, outline="", tags="fondo")
            self._estrellas.append((it, col, _mezcla("#0a1134", col, 0.25)))
        for _ in range(5):                       # estrellas grandes con destello
            x, y = azar.uniform(w * 0.05, w - 280), azar.uniform(8, ALTO - 20)   # no sobre el estado
            for dx, dy, l in ((1, 0, 6), (0, 1, 6)):
                self.create_line(x - dx * l, y - dy * l, x + dx * l, y + dy * l,
                                 fill=_mezcla("#0a1134", "#cdd8ff", 0.6), tags="fondo")
            self.create_oval(x - 1.6, y - 1.6, x + 1.6, y + 1.6, fill="#ffffff", outline="", tags="fondo")
        # estrella fugaz
        x0, y0 = w * 0.42, 18
        for k in range(18):
            self.create_line(x0 + k * 4, y0 + k * 1.2, x0 + k * 4 + 4, y0 + k * 1.2 + 1.2,
                             fill=_mezcla("#0a1134", "#ffffff", k / 18), width=1 + (k > 12), tags="fondo")
        self._planeta(max(w * 0.48, w - 345), 56, 28)       # a la izquierda del estado
        # linea de horizonte: cian -> violeta -> naranja
        tramos = 60
        for k in range(tramos):
            f = k / (tramos - 1)
            col = _mezcla(TEAL, VIOLETA, f * 2) if f < 0.5 else _mezcla(VIOLETA, AMBAR, (f - 0.5) * 2)
            self.create_rectangle(w * k / tramos, ALTO - 3, w * (k + 1) / tramos + 1, ALTO,
                                  fill=col, outline="", tags="fondo")
        self.tag_lower("fondo")
        self.recolocar()

    def _planeta(self, cx, cy, r):
        anillo = (cx - r * 2.0, cy - r * 0.55, cx + r * 2.0, cy + r * 0.55)
        # mitad de atras del anillo
        self.create_arc(*anillo, start=0, extent=180, style="arc", outline="#6c5fd0", width=3, tags="fondo")
        # halo
        for k in range(8, 0, -1):
            rr = r + k * 2.2
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                             fill=_mezcla("#0a1134", "#3b4fb8", (1 - k / 8) * 0.5), outline="", tags="fondo")
        # cuerpo con luz desde arriba a la izquierda
        for k in range(16):
            f = k / 15
            rr = r * (1 - f * 0.75)
            ox, oy = -r * 0.35 * f, -r * 0.35 * f
            self.create_oval(cx + ox - rr, cy + oy - rr, cx + ox + rr, cy + oy + rr,
                             fill=_mezcla("#231a66", "#7fd6ff", f ** 1.4), outline="", tags="fondo")
        # mitad de delante del anillo
        self.create_arc(*anillo, start=180, extent=180, style="arc", outline="#a89bff", width=3, tags="fondo")

    def recolocar(self):
        w = self._ancho or max(self.winfo_width(), 600)
        x0, y0 = 22, 22
        self.coords(self.t_brillo, x0 + 1, y0 + 1)
        self.coords(self.t_titulo, x0, y0)
        self.coords(self.t_sub, x0 + 2, y0 + 40)
        xd = w - 22
        self.coords(self.t_resumen, xd, 20)
        self.coords(self.t_adb, xd, 46)
        bbox = self.bbox(self.t_actualizar)
        ancho_act = (bbox[2] - bbox[0]) if bbox else 140
        self.coords(self.t_actualizar, xd, 64)
        self.coords(self.t_version, xd - ancho_act - 8, 64)
        self.tag_raise("texto")

    def _parpadeo(self):
        try:
            if self._estrellas:
                for it, viva, apagada in self.azar.sample(self._estrellas, min(6, len(self._estrellas))):
                    actual = self.itemcget(it, "fill")
                    self.itemconfigure(it, fill=apagada if actual == viva else viva)
            self.after(450, self._parpadeo)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ ayudas --
    def _ayuda(self, etiqueta, texto):
        def ver(e):
            self._quitar()
            self._tip = tk.Toplevel(self)
            self._tip.wm_overrideredirect(True)
            self._tip.wm_geometry(f"+{e.x_root + 10}+{e.y_root + 16}")
            tk.Label(self._tip, text=texto, bg=FONDO_AYUDA, fg=TEXTO, padx=8, pady=4,
                     font=(LETRA, 9), justify="left", wraplength=320).pack()
        self.tag_bind(etiqueta, "<Enter>", ver, add="+")
        self.tag_bind(etiqueta, "<Leave>", lambda e: self._quitar(), add="+")

    def _quitar(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
