"""Pestana BlueStacks: como tiene que estar configurado BlueStacks para que el bot
funcione, con una comprobacion en vivo de lo que se puede mirar desde aqui
(ADB, instancias detectadas y conectadas). Los pasos son texto fijo (PASOS) y no
llevan nada de ninguna cuenta."""
from __future__ import annotations

import tkinter as tk

from interfaz.tema import (BORDE, ESP_L, ESP_M, ESP_S, ESP_XS, FONDO, NIVEL_COLOR, NIVEL_ICONO, PANEL, SUAVE,
                           TAM_M, TAM_S, TEAL, TEXTO, fuente, titular)

#  (titulo, [lineas]) en el orden en que hay que hacerlo
PASOS = (
    ("1. BlueStacks 5 y una instancia por cuenta",
     ["Instala BlueStacks 5 y crea una instancia por cada cuenta (Administrador de instancias múltiples).",
      "Abre cada instancia y déjala abierta y visible: si está cerrada o minimizada el bot no ve "
      "la pantalla de esa cuenta y la para."]),
    ("2. Resolución de pantalla: 1600 × 900",
     ["En BlueStacks: Ajustes > Pantalla > Resolución de la pantalla = 1600 × 900.",
      "Es la resolución con la que se ha probado el bot. Con otra, el bot reescala lo que ve, "
      "pero es menos fiable."]),
    ("3. ADB activado",
     ["En BlueStacks: Ajustes > Avanzado > Android Debug Bridge (ADB) = activado.",
      "BOT.bat lo activa solo la primera vez, con BlueStacks cerrado. Si no se activa, hazlo a mano."]),
    ("4. Juego en español",
     ["Pon Nova Empire en español: el bot lee textos del juego («Ballena de éter», «Recoger», "
      "«Elige tu flota», «Gema …»)."]),
    ("5. Pantalla táctil virtual",
     ["El zoom con dos dedos (pellizco) usa la pantalla táctil virtual que trae BlueStacks. "
      "No la desactives."]),
    ("6. Vista de ballenas y gemas",
     ["En los ajustes de cada cuenta (botón «Ajustes» de su tarjeta > Ballenas) eliges la vista: 2D "
      "(recomendada) o 3D. El bot cambia de vista solo con el botón redondo del lateral derecho del juego: "
      "no lo muevas mientras trabaja.",
      "En 2D el centro del mapa es el sol (el disco del medio): el bot lo usa de referencia."]),
    ("7. Memoria del equipo",
     ["Cada instancia abierta usa del orden de 1,5 GB de memoria. Cierra lo que no uses y mira "
      "la pestaña Salud si el equipo va justo."]),
    ("8. Si algo falla",
     ["Pestaña Salud: estado del equipo, del detector y de la conexión ADB de cada cuenta (con «Reconectar»).",
      "Pestaña Registro: filtra por cuenta y por tipo para ver qué ha pasado."]),
)


class Guia(tk.Frame):
    """Guia de configuracion de BlueStacks y comprobaciones en vivo."""

    def __init__(self, master, tema, app):
        super().__init__(master, bg=tema["FONDO"], padx=ESP_L, pady=ESP_S)
        self.t = tema
        self.app = app
        tk.Label(self, text="◆  CONFIGURAR BLUESTACKS", bg=FONDO, fg=TEAL,
                 font=titular(TAM_M)).pack(anchor="w", pady=(0, ESP_XS))
        tk.Label(self, text="Para que el bot funcione, BlueStacks tiene que estar así. Los pasos van en orden.",
                 bg=FONDO, fg=SUAVE, font=fuente(TAM_S)).pack(anchor="w", pady=(0, ESP_M))

        #  comprobacion en vivo
        vivo = tk.Frame(self, bg=PANEL, padx=ESP_L, pady=ESP_M, highlightthickness=1, highlightbackground=BORDE)
        vivo.pack(fill="x", pady=(0, ESP_M))
        tk.Label(vivo, text="Comprobación ahora mismo", bg=PANEL, fg=TEXTO, font=titular(TAM_S)).pack(anchor="w")
        self.filas = {}
        for clave in ("adb", "instancias", "conectadas"):
            lbl = tk.Label(vivo, text="…", bg=PANEL, fg=SUAVE, font=fuente(TAM_S), anchor="w", justify="left")
            lbl.pack(anchor="w", pady=(ESP_XS, 0))
            self.filas[clave] = lbl

        #  pasos
        for titulo, lineas in PASOS:
            caja = tk.Frame(self, bg=PANEL, padx=ESP_L, pady=ESP_M, highlightthickness=1, highlightbackground=BORDE)
            caja.pack(fill="x", pady=(0, ESP_S))
            tk.Label(caja, text=titulo, bg=PANEL, fg=TEAL, font=titular(TAM_S), anchor="w").pack(anchor="w")
            for linea in lineas:
                tk.Label(caja, text="•  " + linea, bg=PANEL, fg=TEXTO, font=fuente(TAM_S), anchor="w",
                         justify="left", wraplength=820).pack(anchor="w", pady=(ESP_XS, 0))
        self.actualizar()

    def _poner(self, clave: str, nivel: str, texto: str):
        self.filas[clave].config(text=f"{NIVEL_ICONO[nivel]} {texto}", fg=NIVEL_COLOR[nivel])

    def actualizar(self):
        """Mira ADB, cuantas instancias hay y cuantas estan conectadas."""
        adb = getattr(self.app, "adb", "")
        filas = list(getattr(self.app, "filas", []))
        conectadas = getattr(self.app, "conectadas", set())
        if adb:
            self._poner("adb", "ok", "ADB de BlueStacks encontrado.")
        else:
            self._poner("adb", "error", "No encuentro el ADB de BlueStacks: instala BlueStacks 5 y abre BOT.bat (paso 3).")
        if filas:
            self._poner("instancias", "ok", f"{len(filas)} {'instancia detectada' if len(filas) == 1 else 'instancias detectadas'}.")
        else:
            self._poner("instancias", "aviso", "No hay instancias de BlueStacks detectadas: ábrelas (paso 1).")
        n = sum(1 for f in filas if f"127.0.0.1:{f.puerto}" in conectadas)
        if not filas:
            self._poner("conectadas", "aviso", "Sin instancias que conectar.")
        elif n == len(filas):
            self._poner("conectadas", "ok", "Todas las instancias están conectadas por ADB.")
        else:
            self._poner("conectadas", "aviso" if n else "error",
                        f"{n} de {len(filas)} conectadas por ADB (pasos 1 y 3; reconecta en la pestaña Salud).")
