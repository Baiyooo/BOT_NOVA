"""Todo el estilo de la ventana en un solo sitio: colores, letras y espaciados.

Tema espacial oscuro (azul de espacio profundo, cian de neon, violeta de
nebulosa y naranja de estrella). El resto de la interfaz importa de aqui y no
escribe colores ni tamanos de letra sueltos. El estado nunca se da solo por
color: va siempre con un icono y un texto (ver ICONO_ESTADO)."""
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
LATERAL = "#080e24"        # barra lateral de pestanas
TEXTO_MISION = "#b9c2ef"   # texto de las misiones de un evento
ANILLO_ATRAS = "#6c5fd0"   # cabecera: anillo del planeta
ANILLO_ADELANTE = "#a89bff"

#  cabecera espacial (cielo, nebulosas, planeta, estrellas)
CIELO_ARRIBA, CIELO_MEDIO, CIELO_ABAJO = "#03050f", "#0a1134", "#120d36"
NEBULOSAS = ("#2a1a6e", "#0f3a6b", "#3a1555")
HALO_PLANETA = "#3b4fb8"
PLANETA_SOMBRA, PLANETA_LUZ = "#231a66", "#7fd6ff"
ESTRELLAS = ("#ffffff", "#cdd8ff", "#9fd8ff", TEAL, "#ffe2a8")
BRILLO_ESTRELLA = "#cdd8ff"

#  color de cada fondo de boton al pasar el raton
CLARO = {PANEL2: "#1f2b63", AMBAR: "#ffc977", ROJO: "#ff6f88", TEAL: "#86ecff", VIOLETA: "#b9a1ff"}

#  el mismo juego de colores, para los modulos que lo reciben en un diccionario
TEMA = {"FONDO": FONDO, "PANEL": PANEL, "PANEL2": PANEL2, "BORDE": BORDE, "TEXTO": TEXTO,
        "SUAVE": SUAVE, "AMBAR": AMBAR, "TEAL": TEAL, "ROJO": ROJO, "VERDE": VERDE,
        "VIOLETA": VIOLETA, "TINTA": TINTA, "BLANCO": BLANCO}

# ---------------------------------------------------------------- letras ----
LETRA = "Segoe UI"         # todos los textos (tambien titulos y botones)
TITULAR = LETRA            # (alias: antes habia una letra aparte para titulos)
MONO = "Consolas"          # registro y cifras alineadas

#  tamanos de letra
TAM_XS = 8                 # notas, etiquetas pequenas
TAM_S = 9                  # texto normal
TAM_M = 10                 # botones, desplegables
TAM_L = 12                 # nombres de cuenta, resumen
TAM_XL = 18                # cifras grandes
TAM_TITULO = 20            # titulo de la cabecera


def fuente(tam: int = TAM_S, negrita: bool = False, cursiva: bool = False, subrayada: bool = False):
    """Letra normal de la interfaz."""
    est = " ".join(x for x, si in (("bold", negrita), ("italic", cursiva), ("underline", subrayada)) if si)
    return (LETRA, tam, est) if est else (LETRA, tam)


def titular(tam: int, negrita: bool = True):
    return (LETRA, tam, "bold" if negrita else "normal")


def mono(tam: int = TAM_S):
    return (MONO, tam)


# ------------------------------------------------------------- espaciados ---
ESP_XS = 2
ESP_S = 4
ESP_M = 8
ESP_L = 12
ESP_XL = 20
ANCHO_LATERAL = 150        # barra lateral de pestanas (px, a escala 100 %)
ALTO_CABECERA = 72         # cabecera espacial (px, a escala 100 %)
ANCHO_MIN, ALTO_MIN = 820, 560     # tamano minimo de la ventana

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
#  nivel de cada estado: "ok", "aviso" o "error" (para la cabecera y el icono)
NIVEL_COLOR = {"ok": VERDE, "aviso": AMBAR, "error": ROJO, "info": TEAL, "inactivo": SUAVE}
NIVEL_ICONO = {"ok": "✔", "aviso": "⚠", "error": "✖", "info": "●", "inactivo": "○"}


def nivel_estado(estado: str, en_marcha: bool = True) -> str:
    """Nivel de un estado interno: el color del COLOR_ESTADO decide."""
    col = COLOR_ESTADO.get(estado)
    if col == ROJO:
        return "error"
    if col == AMBAR:
        return "aviso"
    if not en_marcha:
        return "inactivo"
    return "ok" if col in (VERDE, None) else "info"


def icono_estado(estado: str, en_marcha: bool = True) -> str:
    """Icono del estado (asi nunca se distingue solo por el color)."""
    return NIVEL_ICONO[nivel_estado(estado, en_marcha)]


#  colores para distinguir cada cuenta en el registro
COLORES_INST = ("#3ee0ff", "#ffb547", "#9d7bff", "#5aa8ff", "#3ddc97", "#ff6bd6")


def texto_estado(estado: str) -> str:
    if estado in TEXTO_ESTADO:
        return TEXTO_ESTADO[estado]
    t = estado.replace("_", " ")
    return t[:1].upper() + t[1:]
