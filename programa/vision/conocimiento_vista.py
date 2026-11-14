"""Lo aprendido de la vista del sistema (2D y 3D), guardado como CODIGO.

No hay capturas de pantalla aqui: los iconos son recortes diminutos de un solo
icono (sin texto, sin nombres de jugador), comprimidos como texto. Asi el
conocimiento viaja con el programa sin llevar nada de ninguna cuenta.

Que se ve en cada vista (aprendido jugando):
  2D (radar): el SOL es el centro del mapa (disco gris claro con la estacion
      dorada) y no cambia con el zoom ni al deslizar: es la referencia. Los
      iconos crecen con el zoom. Ballena = rombo naranja con un triangulo dentro
      (los piratas son otro simbolo, tambien naranja). Gema libre = aro gris con
      una concha blanca y rombos debajo; verde = la esta recogiendo mi cuenta.
      Iconos lila de color liso = depositos de recursos (Cristales, Mineral...),
      NO son gemas. Dorado = estaciones. Las gemas tambien caen FUERA del anillo
      del sistema.
  3D: la ballena es una silueta pequena con forma de pez cerca del anillo, con
      un circulo rojo al abrir el panel lateral.
"""
from __future__ import annotations

import base64
import zlib

import numpy as np

#  icono -> (alto, ancho, BGR en bruto comprimido con zlib y pasado a base64)
_ICONOS = {
    "ballena_2d": (36, 36, (
        "eNrlkktPGlEUx7to3NRHVeQxMA+Q4SE4gA4oohSUhyg+UItVV30tumi7bFKTLpp0aRdtk36HfoF+k6ZJN/0m7R+OvVzuDIMx"
        "xk2TX07u3HvO+d1zwUxpZkrLJBTCiAUEFpIqwJHZzQTZdNDsr2JHIJcJAf4ULBoq/4m2zi5w+nCbL2m36nwtSW1dAlYLkYrL"
        "9fUcEmrl7Fm7Oai2N8K8BhxEzi42Fw+8wJqfnlMAs/PXcBaBg50N6KwlfFUhO+fgYgg7yahfAKKlTGRzYxmnJ0dblONwQ+Ya"
        "itVlGiHoyoW0kHN82LAmAwOPEJeTusSwbc4+V5eS/Fz0hqDd2sRzYfNwr2orsnUR8VnvoBJwtF9DnI90EAo73W7IlU3r7KHI"
        "tdcoUclxq2Ht03eNaADYu/idfmP7oCHMhfxLwpK6uN377DLIJSTYgtP5qJzQ/Qc71VjIy4jE9OTJl9B8frLxSdCBhC4l+FsN"
        "o1kvcp8+wLvc629j4QCOPGsvSRcNehiU/2/tZCnmU5bNS1dpJUMua9Ugl4BtFR6NJRzu1hCrD5Yimpvh4MKbA1uXEZN5kpGA"
        "AApNQ6cOd17/sYVOCSOm4FfGnwcIrdhV58L+7oV9rWbFeqX79QtKQ2d+QHzOKi4QjJuewnPs0DuH1RkrfGHXJSEuZWJsZ79Z"
        "QRo1JJhu5OkvX+4EO/fa3xHdhRde85GuuYGzq1bOU6SGpdVFWkyV3yGN7n85hdxZeHNnI09+0jron0Z0rb7CYlaeAVhYXfyF"
        "AXTCjiDqRNnlKr2hBWJIlRBHW99IylxWymtmc7PUay5fsr9doUUo0AF9JjY/sxHoiOnAyOMf1NDBJUzBXAxyUfL41ldEObJw"
        "99lvklJUfJMEc9FadHXvsNvYAN3PPhGm412sIbk82VNmsbqsFPMLtvOyzopvCsjeyYB7QpWmFL9Hiq9RwkTxXJHEtpp/WuvV"
        "ijex68/T5wJj5Q+eaGFs9Xy0+hH7Aqo0DZBsbcVygoGZ7fq6s4vAerz0frRyYRXxLgHbZAFblwNXcS2bRlxXruJyRkGJXTI6"
        "FFdMRLze1ee6nouNls+mbsGViGr0wkOhJkNRfVPagORr/DeGzgWdwxuuF5dv7fe62bn+N9dfBQgTAg=="
    )),
    "gema_blanca_2d": (46, 44, (
        "eNrll2lQU1cUx7+2qKwhK4QlCGEVxEptqyiyddS6FymbBDABAhhc2MEkJGitY1vH6XSzTjtVu6ldRG0/tNV22mld2imtneki"
        "2rHfGEdlKcrSf94pt48XEh7b+ME7Z96cd3PfPb97lntvJJ4ekWHByY8lSTw9piJS79kKPy+/OQ+LF9/ZD5Hgc3+vWZpAxf1l"
        "mBaZFobU5CdmgoEZciNskohQ9X1nmKFYPCAMzBaKS+7rKcbi9DLw1/tgMmg1wfk52aX6kq2VRlNVRblBryvIS4yLmhxDfFSE"
        "eNPBKpmxzJCUGO/KD7HauZXGsuhwzYQYRG5NMFFdVamU+FAJpKckNzfW26xme6sFAqWhtiZt6WI2bemWYpW/7zQyRM0NXZmR"
        "BkUtl+y22+ytVpsVpq0EQNJms0JsFrPdapH7eWFmxGvxooViGGQ+c9wDPBIfGxakgtLUUMfZdUhTfS2LBQ0LUcnMzU0AINEX"
        "FVKybVq/bop+SIiJDOWO1F3NjWQ9a/0avPb29ixf8rggWFQXxlI9YVh2NeMVkBvXrZ4KQwpnyOFhDgA7IV67uroGBgbu3r17"
        "584dvP7x+2/Dw8P/9PXh+ebhQ5gzUOZHGFZzC16DlFKNWum+Nl1hIMPxNFUaCQCpiNebN2/C+j2ugeTTM6fxJJ06QQIqDLZz"
        "OWMo1sFKbnbWJPaHIIU/EjskQM4H6OvtZbaoDQ0NISjvHjvaam5hMOjMy346NEBOKSrz9cS36cuSJ8SAyJoqKqC02VoBsH71"
        "Kuj3nBrMERsEuf3X9euHXnuF+gcHB9FZpi8BA0hgaO1TK93UhUDmx0ai/OEBkKASgQGlu7sb0b99+/atW7f6+nrh8AGunTz+"
        "vlYTVFluQKqo/H3w+Zn2U0QIDLxS2SJjIdjiSGFCFrEQQX94SGDasiVQ9MU6zIDnwQMvCMY4CxiUEm8omBA3ZIQDnHg1tzSB"
        "AfGCXpifO+a3SEhBTkaHhzbW10HB5wiE0t+ndse2NSsysa6BkYa0hE8uX7r465Urf9+4gXzAcsDAJnnn6JH+/n4o2FvgyYba"
        "ndDLS/Xiz4WK8lJHSXKJDQW3bgDcG6sR0nfffiNgQHTgB4SJP096ylKRAHALMVBFQLG2NJEtkGDma51XL174/ssvPj925O2V"
        "mWksJ/kMgTIJwpG7aSN/nvhorUgAPHE48r+F3W1VFTRAJfUNUytHV7H0rcNvCBggYMjJ2sCfJ1YbJj4WFDjmw08++hCG4AdW"
        "DuQQVAr+o0Fx9gORk8LmWbQgQTwDjmmkq6Wlmb5FzmNClgDQC/Ny0Il6JXHDEKyUIidbmhqg6zbni2dYkZGKoGw3VWEJ+c9s"
        "IscC4JeODqTZ66++jFfAQIeC6DgzoB/1AqWxrgYLyVjuyEZDSZF4BmxKuK6g0mmfRA/yENH8ueMntiEjHD093QEyP+ecREIK"
        "AkHbadL8ePd2Fy0YNWCLTsf2akrUz86eQcmzqqQzlInAD3ar2XF52LCWJeTC+fNcmU4a+WlhQhxygPVnpqZgd8L9kE0C6bz6"
        "J/kBDhHMwxgwCZ3pCok3OQHHHzqLCvJFLp8vWRvW4Yl0ossbFeaPP1yGNw48v98Vw6WLF4iE4Ckb2TV4ooJNW8FNy+4w1C+I"
        "Ap8BJ9p/saBbH0cOWfVkhhiLOFbmRYYLOvO4okBGMYz0ZUvG/BwMNdtN/BzAJ/TTVqNR5KqxCnYZ4EuJrvDEB+/REUbxxbOo"
        "IO+r8+f4wyJC1DjFKIdtrZZq7KteHrja4Q8QlP/FtXU6PaPmhjj/+vX5c8NcQ8HizwtWt2/vHuq51tlJS4bp4ZG2p80eqlbA"
        "XPupj6knWCUdl4Gd3WNeLOmKiIarNfXsrN7KLBLDvr3Psp7wkADYitFqaD9Hq6/ZMS7DuILZDMWFdMt9lNvzdfm5YBOcXDCH"
        "G7VGrTh54jhZRE9dzXYxsXDlFv5/B3YEoCXGRVcZyw0lxVCwnaJMsIVuzsvZsc2E/wLYUTHm7On2UaYnwhAToXF11R/mNVe1"
        "aaosZ2McZTIpBvd/eVwBMAap96z9zzky9qWDL4r3A76CsFe13N89xpj1y2eA4PpEirOMCTZqALd1u9m93QifwY2IYYAsmBeT"
        "5PqMcyUKP88Aqc9UGBJitGyYJlAeplYIYjSjDP8CdGOWug=="
    )),
}


def icono(nombre: str) -> np.ndarray:
    """El icono (BGR, uint8) guardado en este modulo."""
    alto, ancho, datos = _ICONOS[nombre]
    crudo = zlib.decompress(base64.b64decode(datos))
    return np.frombuffer(crudo, np.uint8).reshape(alto, ancho, 3).copy()


#  ---- vista 2D ---------------------------------------------------------------
SOL_REF = (800.0, 450.0, 37.0)           # sol a zoom medio: centro de la pantalla y radio en px (1600x900)
SOL_ZOOM_MEDIO = (30, 46)                # radio del sol a zoom medio (indica el zoom del mapa)
SOL_RADIO_MIN = 11                       # el sol del sistema entero mide ~14-18 px de radio
UMBRAL_BALLENA_2D = 0.62                 # parecido minimo (canal naranja)
ESCALAS_BALLENA_2D = (0.85, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0, 2.3, 2.6)
UMBRAL_GEMA_BLANCA = 0.72
ESCALAS_GEMA_BLANCA = (0.85, 1.0, 1.15, 1.3, 1.5)
GEMA_PEQUENA_PX = (6, 18)                # tamano de la mancha de una gema con el sistema entero
GEMA_AISLADA_PX = 70                     # una gema suelta fuera del anillo no tiene nada tan cerca
PELLIZCO_SUAVE = 0.3                     # fuerza del pellizco al alejar el mapa
PELLIZCO_ACERCAR = 0.2                   # fuerza del pellizco al acercar un poco
PELLIZCO_PASOS = 12                      # mas pasos = gesto mas suave

#  ---- panel lateral (2D / Ayuda / Recursos), en 1600x900 --------------------------
BOTON_LADO = (1572, 626)                 # boton redondo que despliega el panel
PANEL_ICONOS_Y = 622                     # los iconos del panel estan siempre sobre esta altura
#  el rotulo «2D» va ENCIMA de su icono (en 3D) y el «3D» DEBAJO (en 2D)

#  ---- textos con los que el juego confirma lo que se toca ------------------------
TEXTO_BALLENA = "ballena de eter"
TEXTOS_GEMA = ("gema", "gamma", "organic", "sagrad")
TEXTOS_RECURSO = ("cristal", "mineral", "aleacion", "nucleo")
