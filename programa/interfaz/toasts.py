"""Avisos emergentes pequenos que se cierran solos (toasts).

Uso:
    toasts.instalar(ventana)              # una vez, al montar la ventana
    toasts.avisar("Tarea acabada", "ok")  # desde cualquier sitio del hilo de la interfaz

Niveles: "info", "ok", "aviso" y "error". Cada aviso lleva icono y texto (el
nivel nunca se da solo por color). Un clic lo cierra. Si no hay ventana
instalada (pruebas, sin interfaz) `avisar` no hace nada y devuelve False.
"""
from __future__ import annotations

import time
import tkinter as tk

from interfaz.tema import (ESP_L, ESP_M, ESP_S, FONDO_AYUDA, NIVEL_COLOR, NIVEL_ICONO,
                           TAM_S, TEXTO, fuente)

SEGUNDOS = {"info": 5, "ok": 5, "aviso": 8, "error": 10}
MAX_A_LA_VEZ = 4
REPETIDO_S = 30            # el mismo texto no se vuelve a avisar antes de tantos segundos

_raiz = None
_vivos: list = []          # avisos en pantalla, el mas nuevo al final
_vistos: dict[str, float] = {}


def instalar(raiz) -> None:
    """Registra la ventana sobre la que salen los avisos."""
    global _raiz
    _raiz = raiz
    _vivos.clear()
    _vistos.clear()


def avisar(texto: str, nivel: str = "info", segundos: float | None = None) -> bool:
    """Saca un aviso pequeno. Devuelve False si no se ha mostrado (sin
    ventana, o repetido hace poco)."""
    if _raiz is None or not texto:
        return False
    nivel = nivel if nivel in NIVEL_COLOR else "info"
    ahora = time.time()
    if ahora - _vistos.get(texto, 0) < REPETIDO_S:
        return False
    _vistos[texto] = ahora
    if len(_vistos) > 200:
        for k in [k for k, t in _vistos.items() if ahora - t > REPETIDO_S]:
            _vistos.pop(k, None)
    try:
        while len(_vivos) >= MAX_A_LA_VEZ:
            _cerrar(_vivos[0])
        w = _crear(texto, nivel)
        _vivos.append(w)
        _colocar()
        dur = SEGUNDOS[nivel] if segundos is None else segundos
        w.after(int(dur * 1000), lambda: _cerrar(w))
        return True
    except tk.TclError:
        return False


def _crear(texto: str, nivel: str):
    w = tk.Toplevel(_raiz)
    w.wm_overrideredirect(True)
    try:
        w.wm_attributes("-topmost", True)
    except tk.TclError:
        pass
    color = NIVEL_COLOR[nivel]
    marco = tk.Frame(w, bg=FONDO_AYUDA, highlightthickness=1, highlightbackground=color,
                     padx=ESP_L, pady=ESP_M)
    marco.pack()
    tk.Label(marco, text=NIVEL_ICONO[nivel], bg=FONDO_AYUDA, fg=color,
             font=fuente(TAM_S + 2, True)).pack(side="left", padx=(0, ESP_M))
    tk.Label(marco, text=texto, bg=FONDO_AYUDA, fg=TEXTO, font=fuente(TAM_S),
             justify="left", wraplength=320).pack(side="left")
    for x in (w, marco, *marco.winfo_children()):
        x.bind("<Button-1>", lambda _e, w=w: _cerrar(w))
    return w


def _cerrar(w) -> None:
    if w in _vivos:
        _vivos.remove(w)
    try:
        w.destroy()
    except tk.TclError:
        pass
    _colocar()


def _colocar() -> None:
    """Apila los avisos en la esquina de abajo a la derecha de la ventana."""
    if _raiz is None:
        return
    try:
        _raiz.update_idletasks()
        x1 = _raiz.winfo_rootx() + _raiz.winfo_width() - ESP_L * 2
        y = _raiz.winfo_rooty() + _raiz.winfo_height() - ESP_L * 2
        for w in reversed(_vivos):
            w.update_idletasks()
            ancho, alto = w.winfo_reqwidth(), w.winfo_reqheight()
            y -= alto
            w.wm_geometry(f"+{max(0, x1 - ancho)}+{max(0, y)}")
            y -= ESP_S
    except tk.TclError:
        pass
