"""Piezas pequenas de la ventana: zona desplazable, barra, ayuda emergente, boton plano."""
from __future__ import annotations

import tkinter as tk

from interfaz.tema import BORDE, CLARO, FONDO_AYUDA, LETRA, PANEL2, TEAL, TEXTO, VERDE, titular


class Desplazable(tk.Frame):
    """Zona que se puede bajar con la rueda del raton y con su barra. Lo que
    se monta dentro va en self.dentro. El registro (Text) se baja solo."""

    def __init__(self, master, fondo, texto=None):
        super().__init__(master, bg=fondo)
        self.texto = texto
        self.lienzo = tk.Canvas(self, bg=fondo, bd=0, highlightthickness=0)
        self.barra = tk.Scrollbar(self, orient="vertical", command=self.lienzo.yview, width=10)
        self.lienzo.configure(yscrollcommand=self.barra.set)
        self.barra.pack(side="right", fill="y")
        self.lienzo.pack(side="left", fill="both", expand=True)
        self.dentro = tk.Frame(self.lienzo, bg=fondo)
        self.ventana = self.lienzo.create_window((0, 0), window=self.dentro, anchor="nw")
        self.dentro.bind("<Configure>", self._ajustar)
        self.lienzo.bind("<Configure>", self._ajustar)
        self.bind_all("<MouseWheel>", self._rueda, add="+")

    def _ajustar(self, _e=None):
        alto_vista = self.lienzo.winfo_height()
        alto = max(alto_vista, self.dentro.winfo_reqheight())
        self.lienzo.itemconfigure(self.ventana, width=self.lienzo.winfo_width(), height=alto)
        self.lienzo.configure(scrollregion=(0, 0, self.lienzo.winfo_width(), alto))

    def _rueda(self, e):
        w = e.widget
        if self.texto is not None and str(w).startswith(str(self.texto)):
            return                                   # el registro se baja solo
        if self.dentro.winfo_reqheight() <= self.lienzo.winfo_height():
            return
        self.lienzo.yview_scroll(int(-1 * (e.delta / 120) * 3), "units")


class Barra(tk.Canvas):
    """Barra de progreso dibujada a mano, para controlar el color."""

    def __init__(self, master, ancho=260, alto=8):
        super().__init__(master, width=ancho, height=alto, bg=PANEL2,
                         highlightthickness=0)
        self.ancho, self.alto = ancho, alto
        self.create_rectangle(0, 0, ancho, alto, fill=BORDE, outline="")
        self.relleno = self.create_rectangle(0, 0, 0, alto, fill=VERDE, outline="")

    def set(self, fraccion: float, color=VERDE):
        f = max(0.0, min(1.0, fraccion))
        self.coords(self.relleno, 0, 0, self.ancho * f, self.alto)
        self.itemconfig(self.relleno, fill=color)


class Ayuda:
    """Texto de ayuda al pasar el raton por encima."""

    def __init__(self, widget, texto):
        self.w, self.texto, self.tip = widget, texto, None
        widget.bind("<Enter>", self._ver, add="+")
        widget.bind("<Leave>", self._quitar, add="+")

    def _ver(self, _e=None):
        if self.tip or not self.texto:
            return
        x = self.w.winfo_rootx() + 10
        y = self.w.winfo_rooty() + self.w.winfo_height() + 4
        self.tip = tk.Toplevel(self.w)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.texto, bg=FONDO_AYUDA, fg=TEXTO, padx=8, pady=4,
                 font=(LETRA, 9), justify="left", wraplength=320, highlightthickness=1,
                 highlightbackground=BORDE).pack()

    def _quitar(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def _plano(master, texto, cmd, bg=PANEL2, fg=TEXTO, negrita=False, **kw):
    """Boton plano con cambio de color al pasar el raton."""
    claro = CLARO.get(bg, bg)
    b_ = tk.Button(master, text=texto, command=cmd, bg=bg, fg=fg, activebackground=claro,
                   activeforeground=fg, bd=0, relief="flat", cursor="hand2",
                   font=titular(10) if negrita else (LETRA, 10), **kw)
    b_.bind("<Enter>", lambda e: b_.cget("state") != "disabled" and b_.config(bg=claro))
    b_.bind("<Leave>", lambda e: b_.config(bg=b_._bg))
    b_._bg = bg

    def color(nuevo_bg, nuevo_fg=None):
        b_._bg = nuevo_bg
        b_.config(bg=nuevo_bg, activebackground=CLARO.get(nuevo_bg, nuevo_bg), fg=nuevo_fg or b_.cget("fg"),
                  activeforeground=nuevo_fg or b_.cget("fg"))
    b_.color = color
    return b_


def titulo_seccion(master, texto, bg, **pack):
    """Titulo de seccion: rombo cian y texto en mayusculas con letra de titulares."""
    lbl = tk.Label(master, text="◆  " + texto.upper(), bg=bg, fg=TEAL, font=titular(10))
    if pack is not None:
        lbl.pack(**pack)
    return lbl