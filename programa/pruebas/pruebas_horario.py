"""Pruebas del horario por cuenta (franjas en las que no se hace una tarea).

    python pruebas\\pruebas_horario.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cerebro import planificador as p                    # noqa: E402
from interfaz.horario import leer_franjas, texto_franjas  # noqa: E402


def hora(h, m=0):
    """Epoch de hoy a esa hora local."""
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, m, 0, 0, 0, -1))


fallos = 0


def ok(nombre, cond, extra=""):
    global fallos
    if cond:
        print("OK  ", nombre)
    else:
        fallos += 1
        print("FALLO", nombre, extra)


# leer y escribir franjas
ok("2-8 se lee", leer_franjas("2-8") == [[2, 8]])
ok("varias franjas", leer_franjas("2-8, 14-15") == [[2, 8], [14, 15]])
ok("vacio = ninguna", leer_franjas("") == [])
ok("22-6 cruza la medianoche", leer_franjas("22-6") == [[22, 6]])
ok("mal escrito no revienta", leer_franjas("ocho-nueve") is None and leer_franjas("2-") is None)
ok("2-2 no es una franja", leer_franjas("2-2") == [])
ok("texto_franjas", texto_franjas([[2, 8], [14, 15]]) == "2-8, 14-15")

# dentro y fuera de una franja
ok("las 3 esta dentro de 2-8", p.franja_activa([[2, 8]], hora(3)))
ok("las 8 esta fuera de 2-8", not p.franja_activa([[2, 8]], hora(8)))
ok("las 2 esta dentro de 2-8", p.franja_activa([[2, 8]], hora(2)))
ok("las 23 esta dentro de 22-6", p.franja_activa([[22, 6]], hora(23)))
ok("las 5 esta dentro de 22-6", p.franja_activa([[22, 6]], hora(5)))
ok("las 12 no esta en 22-6", not p.franja_activa([[22, 6]], hora(12)))
ok("sin franjas: nada bloqueado", not p.franja_activa([], hora(3)))

# el planificador respeta el horario
ahora = hora(3)
claves = lambda horario: {a.clave for a in p.decidir(  # noqa: E731
    {}, {"sigilo": True}, None, ahora=ahora, opciones={"horario": horario})}
ok("sin horario, sigilo se ofrece", "sigilo" in claves({}))
ok("con 2-8, a las 3 no se ofrece sigilo", "sigilo" not in claves({"sigilo": [[2, 8]]}))
ok("con 9-15, a las 3 si se ofrece sigilo", "sigilo" in claves({"sigilo": [[9, 15]]}))
ok("bloquear sigilo no bloquea otras tareas",
   "gratis" in {a.clave for a in p.decidir({}, {"sigilo": True, "gratis": True}, None,
                                            ahora=ahora, opciones={"horario": {"sigilo": [[2, 8]]}})})
ok("en hogar sin datos, no revienta",
   isinstance(p.decidir({}, {}, None, ahora=ahora, opciones={"horario": {"sigilo": [[2, 8]]}}), list))

print(f"\nFALLOS: {fallos}")
sys.exit(1 if fallos else 0)
