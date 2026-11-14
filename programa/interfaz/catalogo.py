"""Las tareas que ofrece la ventana: nombres, grupos, limites y ayudas."""
from __future__ import annotations

from cerebro import rutina
from tareas.cosmomante import juego
from tareas import eventos
from tareas.piratas import mixto
from tareas.piratas import normales
from tareas.piratas import sigilo
from tareas import recompensas


#  El selector de cada instancia, por grupos (cada grupo es un submenú)
TAREA_GRUPOS = (
    ("Automático", ("Rutina automática",)),
    ("Piratas", ("Piratas de sigilo", "Piratas normales", "Piratas: sigilo + normales")),
    ("Recompensas", ("Recompensas diarias", "Recompensas de eventos")),
    ("Cosmomante", ("Cosmomante",)),
    ("Ballenas", ("Solo ballenas",)),
    ("Recolección", ("Recolección (a elegir)",)),
    ("Minijuegos y otros", ("Roaming Test", "Simulación")),
)
TAREA_FILA = {"Piratas de sigilo": "piratas",
              "Piratas normales": "normales",
              "Piratas: sigilo + normales": "mixto", "Roaming Test": "roaming",
              "Recompensas diarias": "recompensas", "Recompensas de eventos": "eventos",
              "Simulación": "simulacion", "Cosmomante": "cosmomante",
              "Rutina automática": "rutina", "Solo ballenas": "ballenas",
              "Recolección (a elegir)": "recoleccion"}


NOMBRE_TAREA = {v: k for k, v in TAREA_FILA.items()}
NOMBRE_TAREA["cosmo"] = "Cosmomante"       # ajustes guardados con la variante antigua
#  Nombre de cada tarea tal como lo dicen las propias tareas (para el registro)
TAREAS = {"roaming": "Roaming Test", "piratas": sigilo.PiratasSigilo.NOMBRE,
          "normales": normales.PiratasNormales.NOMBRE, "recompensas": recompensas.Recompensas.NOMBRE,
          "simulacion": recompensas.Simulacion.NOMBRE, "rutina": rutina.Rutina.NOMBRE,
          "cosmomante": juego.Cosmomante.NOMBRE, "mixto": mixto.PiratasMixto.NOMBRE,
          "eventos": eventos.RecogerEventos.NOMBRE, "ballenas": rutina.SoloBallenas.NOMBRE,
          "recoleccion": rutina.SoloRecoleccion.NOMBRE}


#  Lo que cuenta el limite de cada tarea (None = no tiene limite que poner)
UNIDAD = {"piratas": "búsquedas", "normales": "ataques", "roaming": "partidas", "mixto": None,
          "recompensas": None, "eventos": None, "simulacion": None, "cosmomante": None,
          "rutina": None, "ballenas": None, "recoleccion": None}
SIN_LIMITE = {"ballenas": "hasta el tope del día","recompensas": "una pasada", "eventos": "una pasada", "simulacion": "una pasada",
              "cosmomante": "una pasada", "rutina": "hasta que la pares", "recoleccion": "hasta que la pares",
              "mixto": "hasta que la pares"}
AYUDA_TAREA = {
    "piratas": "Busca piratas de sigilo con el radar y los ataca con todas las flotas.",
    "normales": "Ataca piratas normales del sistema, una flota por pirata.",
    "mixto": "Piratas normales sin parar y, cada 30 min, los de sigilo.",
    "roaming": "Juega el minijuego Roaming Test del evento Neural Roaming.",
    "recompensas": "Recoge los suministros gratis, la recompensa diaria y las tareas diarias.",
    "eventos": "Recoge las recompensas de los eventos; nunca compra ni gasta GEC.",
    "simulacion": "Simulación automática de batalla, solo si es gratis (0 GEC).",
    "cosmomante": "Tiradas gratis y metas; gasta dados solo si llega a nivel 6 (ajustes en Eventos).",
    "ballenas": "Solo ballenas de éter, con los mismos ajustes que la Rutina "
                "(Ajustes > Ballenas: rol, pareja, robots y tope del día).",
    "recoleccion": "Hace solo las tareas de recoger que marques en Ajustes > Recolección: suministros "
                   "gratis, recompensas, destacamento, escombros y gemas del sistema.",
    "rutina": "Decide sola qué toca en cada momento: lee los eventos y sus misiones, "
              "hace lo diario al empezar y ataca piratas según lo que pidan los eventos.",
}
