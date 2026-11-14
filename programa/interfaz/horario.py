"""Horario de una cuenta: franjas en las que NO se hace una tarea.

Por ejemplo, "sin piratas de 2:00 a 8:00": se escribe 2-8 en la linea de
«Piratas de sigilo». El planificador respeta estas franjas (horas locales) y
esas tareas no se eligen mientras esten dentro. Las franjas que cruzan la
medianoche se escriben asi: 22-6.
"""
from __future__ import annotations

import re
import tkinter as tk

from interfaz.tema import (AMBAR, BORDE, ESP_L, ESP_M, ESP_S, PANEL, PANEL2, ROJO, SUAVE, TAM_M, TAM_S,
                           TEAL, TEXTO, fuente, titular)
from interfaz.widgets import Ayuda, _plano

#  tareas que se pueden limitar por horas (las del planificador)
TAREAS_HORARIO = (("sigilo", "Piratas de sigilo"), ("normales", "Piratas normales"),
                  ("ballenas", "Ballenas de éter"), ("eventos", "Recompensas de eventos"),
                  ("gratis", "Suministros gratis"), ("simulacion", "Simulación"),
                  ("recompensas", "Recompensas diarias"), ("cosmomante", "Cosmomante"),
                  ("roaming", "Roaming Test"), ("artefactos", "Artefactos"),
                  ("bingo", "Bingo Estelar"), ("escombros", "Recoger escombros"),
                  ("gemas", "Recoger gemas"), ("llamar_flotas", "Llamar flotas"),
                  ("destacamento", "Destacamento"))


def leer_franjas(texto: str) -> list[list[int]] | None:
    """'2-8, 14-15' -> [[2, 8], [14, 15]]. Vacío -> []. Mal escrito -> None."""
    out: list[list[int]] = []
    for trozo in re.split(r"[,;]", texto or ""):
        trozo = trozo.strip()
        if not trozo:
            continue
        m = re.fullmatch(r"(\d{1,2})\s*[-–—:.]\s*(\d{1,2})", trozo)
        if not m:
            return None
        a, b = int(m.group(1)), int(m.group(2))
        if not (0 <= a <= 24 and 0 <= b <= 24):
            return None
        if a != b:
            out.append([a, b])
    return out


def texto_franjas(franjas) -> str:
    """[[2, 8], [14, 15]] -> '2-8, 14-15'."""
    return ", ".join(f"{int(a)}-{int(b)}" for a, b in (franjas or []))


def ventana_horario(master, tema, nombre: str, horario: dict, guardar):
    """Ventana con una linea por tarea; al guardar, llama a guardar(dict)."""
    w = tk.Toplevel(master)
    w.title(f"Horario · {nombre}")
    w.configure(bg=tema["FONDO"])
    w.transient(master)
    try:
        w.grab_set()
    except tk.TclError:
        pass
    tk.Label(w, text="◆  HORARIO DE ESTA CUENTA", bg=tema["FONDO"], fg=TEAL,
             font=titular(TAM_M)).pack(anchor="w", padx=ESP_L, pady=(ESP_L, 0))
    tk.Label(w, text="Franjas en las que NO se hace cada tarea (horas 0-24).\n"
                     "Ejemplo: 2-8 = desde las 2 hasta las 8. 22-6 cruza la medianoche. "
                     "Vacío = a cualquier hora.",
             bg=tema["FONDO"], fg=SUAVE, font=fuente(TAM_S), justify="left",
             wraplength=460).pack(anchor="w", padx=ESP_L, pady=(ESP_S, ESP_M))
    caja = tk.Frame(w, bg=PANEL, padx=ESP_L, pady=ESP_M, highlightthickness=1,
                    highlightbackground=BORDE)
    caja.pack(fill="both", expand=True, padx=ESP_L)
    variables = {}
    for i, (clave, etiqueta) in enumerate(TAREAS_HORARIO):
        v = tk.StringVar(value=texto_franjas((horario or {}).get(clave)))
        variables[clave] = v
        fila = tk.Frame(caja, bg=PANEL)
        fila.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, ESP_L), pady=ESP_S)
        tk.Label(fila, text=etiqueta, bg=PANEL, fg=TEXTO, font=fuente(TAM_S), width=20,
                 anchor="w").pack(side="left")
        e = tk.Entry(fila, textvariable=v, bg=PANEL2, fg=TEXTO, bd=0, width=12,
                     insertbackground=TEXTO, highlightthickness=0, font=fuente(TAM_S),
                     justify="center")
        e.pack(side="left", ipady=ESP_S)
        Ayuda(e, "Horas en las que NO se hace (p.ej. 2-8). Vacío = siempre.")
    w.grid_columnconfigure(0, weight=1)
    self_aviso = tk.Label(w, text="", bg=tema["FONDO"], fg=ROJO, font=fuente(TAM_S))
    self_aviso.pack(anchor="w", padx=ESP_L, pady=(ESP_S, 0))
    pie = tk.Frame(w, bg=tema["FONDO"])
    pie.pack(fill="x", padx=ESP_L, pady=ESP_M)

    def aceptar():
        h = {}
        for clave, v in variables.items():
            fr = leer_franjas(v.get())
            if fr is None:
                self_aviso.config(text=f"No entiendo «{v.get()}» (usa 2-8, 14-15…).")
                return
            if fr:
                h[clave] = fr
        guardar(h)
        w.destroy()

    _plano(pie, "Guardar", aceptar, bg=AMBAR, fg=tema["TINTA"], negrita=True,
           padx=ESP_L, pady=ESP_S).pack(side="right")
    _plano(pie, "Cancelar", w.destroy, padx=ESP_L, pady=ESP_S).pack(side="right", padx=(0, ESP_M))
    _plano(pie, "Quitar todo", lambda: [v.set("") for v in variables.values()],
           padx=ESP_L, pady=ESP_S).pack(side="left")
    w.resizable(False, False)
    return w
