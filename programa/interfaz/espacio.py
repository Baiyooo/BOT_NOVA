"""Cabecera espacial de la ventana: cielo con nebulosas, estrellas que
parpadean, un planeta con anillo, el titulo y el estado general (version,
cuentas en marcha, todo bien / avisos / errores, ADB).

Todo se dibuja en un Canvas, asi que se redibuja al cambiar el ancho. Las
medidas se escalan con el escalado de Windows (125 %, 150 %...)."""
from __future__ import annotations

import random
import tkinter as tk

from interfaz.tema import (ALTO_CABECERA, AMBAR, ANILLO_ADELANTE, ANILLO_ATRAS, CIELO_ABAJO, CIELO_ARRIBA,
                           CIELO_MEDIO, ESTRELLAS, FONDO, FONDO_AYUDA, HALO_PLANETA, NEBULOSAS, PLANETA_LUZ,
                           PLANETA_SOMBRA, ROJO, SUAVE, TAM_L, TAM_M, TAM_S, TAM_TITULO, TAM_XS, TEAL, TEXTO,
                           VERDE, VIOLETA, fuente, titular)


def factor_escala(widget) -> float:
    """Cuanto mas grande que a 96 ppp es todo (1.0 = 100 %, 1.5 = 150 %)."""
    try:
        return max(1.0, float(widget.tk.call("tk", "scaling")) / (96 / 72))
    except (tk.TclError, ValueError):
        return 1.0


def _mezcla(a: str, b: str, f: float) -> str:
    """Color entre a y b (f=0 -> a, f=1 -> b)."""
    a1 = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b1 = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a1, b1, strict=False))


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
        self.k = factor_escala(master)
        self.alto = round(ALTO_CABECERA * self.k)
        super().__init__(master, height=self.alto, bg=FONDO, highlightthickness=0, bd=0)
        self.azar = random.Random(7)
        self._ancho = 0
        self._estrellas = []          # (item, color brillante, color apagado)
        self._tip = None
        self.subtitulo = subtitulo
        self.version = version
        # textos fijos (se colocan en recolocar)
        self.t_brillo = self.create_text(0, 0, text="N O V A B O T", fill=_mezcla(FONDO, TEAL, 0.35),
                                         font=titular(TAM_TITULO), anchor="nw", tags="texto")
        self.t_titulo = self.create_text(0, 0, text="N O V A B O T", fill=TEXTO, font=titular(TAM_TITULO),
                                         anchor="nw", tags="texto")
        self.t_sub = self.create_text(0, 0, text=subtitulo, fill=SUAVE, font=fuente(TAM_XS + 1),
                                      anchor="nw", tags="texto")
        self.t_resumen = self.create_text(0, 0, text="", fill=TEXTO, font=fuente(TAM_L),
                                          anchor="ne", tags="texto")
        self.t_general = self.create_text(0, 0, text="✔ Todo bien", fill=VERDE, font=fuente(TAM_M, True),
                                          anchor="ne", tags=("texto", "general"))
        self.t_adb = self.create_text(0, 0, text="● ADB listo" if adb_ok else "✖ ADB no encontrado",
                                      fill=VERDE if adb_ok else ROJO, font=fuente(TAM_XS), anchor="ne",
                                      tags=("texto", "adb"))
        self.t_version = self.create_text(0, 0, text=f"v{version}", fill=SUAVE, font=fuente(TAM_XS, True),
                                          anchor="ne", tags="texto")
        self.t_actualizar = self.create_text(0, 0, text="Actualizar desde archivo…", fill=TEAL,
                                             font=fuente(TAM_XS, subrayada=True), anchor="ne",
                                             tags=("texto", "actualizar"))
        self.lbl_resumen = _Texto(self, self.t_resumen)
        self.lbl_general = _Texto(self, self.t_general)
        self.lbl_adb = _Texto(self, self.t_adb)
        if al_actualizar:
            self.tag_bind("actualizar", "<Button-1>", lambda e: al_actualizar())
        self._ayuda("actualizar", "Instala una versión nueva sin perder ajustes ni estadísticas.")
        self._ayuda("adb", f"ADB: {adb_ruta or 'no encontrado'}")
        self._ayuda("general", "Estado general: todo bien, avisos (algo pide atención) o errores.")
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
        k, alto = self.k, self.alto
        self.delete("fondo")
        azar = random.Random(7)
        # degradado vertical del cielo
        for i in range(alto):
            f = i / (alto - 1)
            col = (_mezcla(CIELO_ARRIBA, CIELO_MEDIO, f * 2) if f < 0.5
                   else _mezcla(CIELO_MEDIO, CIELO_ABAJO, (f - 0.5) * 2))
            self.create_line(0, i, w, i, fill=col, tags="fondo")
        # nebulosas: circulos concentricos que se funden con el cielo
        for cx, cy, r, col in ((w * 0.30, alto * 0.6, 90 * k, NEBULOSAS[0]),
                               (w * 0.55, alto * 0.15, 70 * k, NEBULOSAS[1]),
                               (w * 0.85, alto * 0.8, 80 * k, NEBULOSAS[2])):
            for n in range(14, 0, -1):
                rr = r * n / 14
                self.create_oval(cx - rr * 1.6, cy - rr * 0.55, cx + rr * 1.6, cy + rr * 0.55,
                                 fill=_mezcla(CIELO_MEDIO, col, (1 - n / 14) * 0.9 + 0.1),
                                 outline="", tags="fondo")
        # estrellas
        self._estrellas = []
        for _ in range(int(w / 9)):
            x, y = azar.uniform(0, w), azar.uniform(0, alto - 6)
            tam = azar.choice((0.6, 0.6, 0.6, 1.0, 1.0, 1.6)) * k
            col = azar.choice(ESTRELLAS)
            it = self.create_oval(x - tam, y - tam, x + tam, y + tam, fill=col, outline="", tags="fondo")
            self._estrellas.append((it, col, _mezcla(CIELO_MEDIO, col, 0.25)))
        self._planeta(max(w * 0.48, w - 400 * k), alto * 0.5, 20 * k)       # a la izquierda del estado
        # linea de horizonte: cian -> violeta -> naranja
        tramos = 60
        for n in range(tramos):
            f = n / (tramos - 1)
            col = _mezcla(TEAL, VIOLETA, f * 2) if f < 0.5 else _mezcla(VIOLETA, AMBAR, (f - 0.5) * 2)
            self.create_rectangle(w * n / tramos, alto - 3, w * (n + 1) / tramos + 1, alto,
                                  fill=col, outline="", tags="fondo")
        self.tag_lower("fondo")
        self.recolocar()

    def _planeta(self, cx, cy, r):
        anillo = (cx - r * 2.0, cy - r * 0.55, cx + r * 2.0, cy + r * 0.55)
        # mitad de atras del anillo
        self.create_arc(*anillo, start=0, extent=180, style="arc", outline=ANILLO_ATRAS, width=3, tags="fondo")
        # halo
        for n in range(8, 0, -1):
            rr = r + n * 2.2
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                             fill=_mezcla(CIELO_MEDIO, HALO_PLANETA, (1 - n / 8) * 0.5), outline="", tags="fondo")
        # cuerpo con luz desde arriba a la izquierda
        for n in range(16):
            f = n / 15
            rr = r * (1 - f * 0.75)
            ox, oy = -r * 0.35 * f, -r * 0.35 * f
            self.create_oval(cx + ox - rr, cy + oy - rr, cx + ox + rr, cy + oy + rr,
                             fill=_mezcla(PLANETA_SOMBRA, PLANETA_LUZ, f ** 1.4), outline="", tags="fondo")
        # mitad de delante del anillo
        self.create_arc(*anillo, start=180, extent=180, style="arc", outline=ANILLO_ADELANTE, width=3,
                        tags="fondo")

    def recolocar(self):
        w = self._ancho or max(self.winfo_width(), 600)
        k = self.k
        x0, y0 = round(20 * k), round(8 * k)
        self.coords(self.t_brillo, x0 + 1, y0 + 1)
        self.coords(self.t_titulo, x0, y0)
        self.coords(self.t_sub, x0 + 2, y0 + round(34 * k))
        xd = w - round(20 * k)
        self.coords(self.t_resumen, xd, round(8 * k))
        self.coords(self.t_general, xd, round(28 * k))
        # fila de abajo, de derecha a izquierda: actualizar, version, ADB
        y3 = round(50 * k)
        self.coords(self.t_actualizar, xd, y3)
        x = xd - self._ancho_de(self.t_actualizar, 140) - 10
        self.coords(self.t_version, x, y3)
        x -= self._ancho_de(self.t_version, 30) + 10
        self.coords(self.t_adb, x, y3)
        self.tag_raise("texto")

    def _ancho_de(self, item, defecto: int) -> int:
        bbox = self.bbox(item)
        return (bbox[2] - bbox[0]) if bbox else defecto

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
                     font=fuente(TAM_S), justify="left", wraplength=320).pack()
        self.tag_bind(etiqueta, "<Enter>", ver, add="+")
        self.tag_bind(etiqueta, "<Leave>", lambda e: self._quitar(), add="+")

    def _quitar(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

