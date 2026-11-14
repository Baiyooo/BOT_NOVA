"""Colores y letras de la ventana: tema espacial (azul de espacio profundo,
cian de neon, violeta de nebulosa y naranja de estrella)."""
from __future__ import annotations


# ---------------------------------------------------------------- colores ---
FONDO = "#060a1a"          # espacio profundo
PANEL = "#0c1330"          # tarjetas
PANEL2 = "#141d45"         # botones y campos
BORDE = "#25316b"          # bordes, lineas
TEXTO = "#e6ebff"          # luz de estrella
SUAVE = "#8e97c8"          # texto secundario
AMBAR = "#ffb547"          # accion principal (propulsor)
TEAL = "#3ee0ff"           # cian de neon (enlaces, acentos)
VERDE = "#3ddc97"
ROJO = "#ff4d6d"
VIOLETA = "#9d7bff"        # nebulosa
TINTA = "#170e02"          # texto sobre los botones naranjas
BLANCO = "#ffffff"
FONDO_AYUDA = "#1b2557"    # globos de ayuda

#  color de cada fondo de boton al pasar el raton
CLARO = {PANEL2: "#1f2b63", AMBAR: "#ffc977", ROJO: "#ff6f88", TEAL: "#86ecff", VIOLETA: "#b9a1ff"}

# ---------------------------------------------------------------- letras ----
LETRA = "Segoe UI"         # textos
TITULAR = "Bahnschrift"    # titulos, cifras grandes y botones principales
MONO = "Consolas"          # registro


def titular(tam: int, negrita: bool = True):
    return (TITULAR, tam, "bold" if negrita else "normal")


# ---------------------------------------------------------------- estados ---
COLOR_ESTADO = {
    "en espera": SUAVE, "arrancando": TEAL, "jugando": VERDE,
    "reiniciando": AMBAR, "terminado": TEAL, "parado": SUAVE,
    "sin tickets": AMBAR, "sin tablero": ROJO, "atascado": ROJO,
    "atacando": AMBAR, "combatiendo": AMBAR, "sin_busquedas": AMBAR,
    "sin_radar": ROJO, "sin_ir_a": ROJO, "sin conexión": ROJO,
}
#  como se escribe cada estado interno en la tarjeta
TEXTO_ESTADO = {
    "sin_busquedas": "Sin búsquedas", "sin_radar": "Sin radar", "sin_ir_a": "Sin «Ir a»",
    "sin tickets": "Sin tickets", "sin tablero": "Sin tablero",
    "sin conexión": "Sin conexión con BlueStacks",
}
#  colores para distinguir cada cuenta en el registro
COLORES_INST = ("#3ee0ff", "#ffb547", "#9d7bff", "#5aa8ff", "#3ddc97", "#ff6bd6")


def texto_estado(estado: str) -> str:
    if estado in TEXTO_ESTADO:
        return TEXTO_ESTADO[estado]
    t = estado.replace("_", " ")
    return t[:1].upper() + t[1:]
