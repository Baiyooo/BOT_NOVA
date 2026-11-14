"""Memoria de los eventos del juego y de sus misiones (sin tocar el juego).

Dos archivos en %LOCALAPPDATA%\\NovaBot:
  - eventos_juego.json (comun a todas las cuentas): cada evento con su hora de
    fin, y la lista de misiones que pide, leida UNA sola vez por evento (los
    requisitos se repiten siempre).
  - misiones_<cuenta>.json: el progreso de cada cuenta en cada mision. Se
    reinicia solo cuando empieza una edicion nueva del evento (cambia su fin).

Cada mision se clasifica con las reglas del bot:
  bot     -> la hace el bot (piratas de sigilo, fuerza pirata, simulacion,
             destacamento, ballenas);
  manual  -> la hace el jugador (gastar GEC, construir naves, abrir cajas,
             acelerar, academia, comprar...);
  espera  -> pendiente de que el bot sepa hacerla (explorar planetas,
             producir armas mientras no exista la tarea).
"""
from __future__ import annotations

import difflib
import os
import re
import time
import unicodedata

from cerebro import textos_mision as tm
from nucleo import config as _cfg

# --------------------------------------------------------------- textos --


def sin_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", texto).strip()


def clave(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", sin_acentos(nombre)).strip("_")[:50] or "evento"


# Nombres de eventos que se ven en el juego. El OCR a veces los lee mal
# ("-tefactos", "EENTOS", "Hidrauedes"...): si un nombre se parece mucho a uno
# de estos (o a otro ya guardado), se cambia por el bueno.
CONOCIDOS = ("Neural Roaming", "Cosmomante", "Artefactos", "Materiales de Vacio",
             "Bendicion celestial", "Reflejo de vacio", "Eventos de intercambio",
             "Corazon Carmesi", "Mision en predesarrollo", "Santuario de la Hidra",
             "Explorar galaxia")
# Eventos cuyas misiones se leen una sola vez (siempre son las mismas): luego
# no se vuelve a mirar su progreso (en Artefactos solo se pulsa «Buscar»)
LEER_UNA_VEZ = ("artefactos",)
# Eventos que el bot no tiene en cuenta: no se apuntan, no se leen sus
# misiones y no salen en la ventana. (Estan en CONOCIDOS para que, aunque el
# OCR los lea mal, se reconozcan y se descarten.)
IGNORADOS = ("mision_en_predesarrollo", "explorar_galaxia", "santuario_de_la_hidra",
             "materiales_de_vacio", "corazon_carmesi", "la_ira_de_einherjar")


def ignorado(k: str) -> bool:
    """Tambien las variantes con texto pegado («Santuario de la Hidra Completado:»)."""
    return any(k == i or k.startswith(i + "_") for i in IGNORADOS)
# Cabeceras de la lista (no son eventos)
CABECERAS = ("eventos", "evento", "events", "event")
PARECIDO_NOMBRE = 0.82


def _compacto(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]", "", sin_acentos(nombre))


def nombre_canonico(nombre: str, existentes=()) -> str:
    """El nombre bueno de un evento: el conocido o el ya guardado que mas se
    parezca (si se parece lo bastante); si no, el mismo nombre limpio."""
    limpio = re.sub(r"\s+", " ", str(nombre or "")).strip()
    # el boton «Puedes unirte» a veces se pega al nombre
    limpio = re.sub(r"\s*p?uedes\s*unirte.*$", "", limpio, flags=re.I).strip() or limpio
    cmp_ = _compacto(limpio)
    if len(cmp_) < 4:
        return limpio
    mejor, puntos = limpio, 0.0
    for c in list(CONOCIDOS) + list(existentes):
        cc = _compacto(c)
        if not cc:
            continue
        r = 1.0 if cc == cmp_ else difflib.SequenceMatcher(None, cmp_, cc).ratio()
        if r > puntos:
            mejor, puntos = c, r
    if puntos >= PARECIDO_NOMBRE:
        return mejor
    return limpio[:1].upper() + limpio[1:]


def es_cabecera(nombre: str) -> bool:
    """La cabecera «EVENTOS» de la lista (tambien mal leida: «EENTOS», «ENENTOS»)."""
    c = _compacto(nombre)
    if len(c) < 4 or c in CABECERAS:
        return True
    return difflib.SequenceMatcher(None, c, "eventos").ratio() >= 0.8


def es_ruido(nombre: str) -> bool:
    """Un nombre mal leido que no es ningun evento: la cabecera pegada a otro
    nombre («EVENTOSales oe vacio», «EKENTQS», «WENTOS») o un trozo de un
    nombre conocido («Mesi», de Corazon Carmesi)."""
    c = _compacto(nombre)
    conocidos = [_compacto(x) for x in CONOCIDOS]
    if not c or c in conocidos:
        return False
    if len(c) <= 5 and any(c in k for k in conocidos):
        return True
    return difflib.SequenceMatcher(None, c[:7], "eventos").ratio() >= 0.7


#  subtitulos conocidos que a veces se leen como si fueran el nombre
SUBTITULOS = {"Extraccion de recursos": "Artefactos", "Galaxia Cuantica": "Cosmomante",
              "Iluminar las estrellas": "Bendicion celestial"}


def otro_nombre(nombre: str, existentes=(), subtitulos=None) -> str | None:
    """Si «nombre» es en realidad el subtitulo de otro evento («Extraccion de
    recursos» = Artefactos) o un trozo de su nombre («De intercambio» =
    Eventos de intercambio), el nombre bueno; si no, None."""
    c = _compacto(nombre)
    if len(c) < 8:
        return None
    for sub, ev in list(SUBTITULOS.items()) + list((subtitulos or {}).items()):
        cs = _compacto(sub)
        if cs and (c == cs or difflib.SequenceMatcher(None, c, cs).ratio() >= 0.85):
            return ev
    for n in list(CONOCIDOS) + [e for e in existentes if e]:
        cn = _compacto(n)
        if cn != c and len(cn) > len(c) and cn.endswith(c):
            return n
    return None


def nombre_tarjeta(t: dict, existentes=(), subtitulos=None) -> str | None:
    """El nombre bueno de una tarjeta de LISTA DE EVENTOS, o None si no es un
    evento. Si el titulo se lee como la cabecera («EVENTOS»), a veces el
    nombre de verdad esta en el subtitulo («-tefactos» -> Artefactos)."""
    existentes = [e for e in existentes if e]
    nombre = str(t.get("nombre") or "").strip()
    if len(nombre) >= 3 and not es_cabecera(nombre) and not es_ruido(nombre):
        return otro_nombre(nombre, existentes, subtitulos) or nombre_canonico(nombre, existentes)
    sub = str(t.get("subtitulo") or "").strip()
    if sub and not es_cabecera(sub):
        bueno = nombre_canonico(sub, existentes)
        if _compacto(bueno) in {_compacto(c) for c in list(CONOCIDOS) + existentes}:
            return bueno
        # o el subtitulo es el de un evento ya visto («Iluminar las estrellas»)
        cs = _compacto(sub)
        for otro_sub, su_nombre in (subtitulos or {}).items():
            co = _compacto(otro_sub)
            if len(co) >= 6 and len(cs) >= 6 and (co in cs or cs in co or
                                                 difflib.SequenceMatcher(None, cs, co).ratio() >= 0.8):
                return su_nombre
    return None


def subtitulos_de(ev: dict) -> dict:
    """{subtitulo: nombre} de los eventos guardados con nombre bueno."""
    return {e["subtitulo"]: e["nombre"] for e in ev.values()
            if e.get("subtitulo") and e.get("nombre") and not es_cabecera(e["nombre"])}


_T_DHMS = re.compile(r"(?:(\d+)\s*d\s*)?(\d{1,2})\s*:\s*(\d{2})(?:\s*:\s*(\d{2}))?")
_T_PARTES = re.compile(r"(\d+)\s*(d|h|m|s)\b")


def segundos(texto: str) -> int | None:
    """Cuenta atras del juego en segundos: "1d13:57:27", "13:57:27",
    "3d 17h", "17h 5m", "45m". None si no hay tiempo."""
    t = sin_acentos(texto).replace("dias", "d").replace("dia", "d")
    m = _T_DHMS.search(t)
    if m:
        d, h, mi, s = (int(x) if x else 0 for x in m.groups())
        if m.group(4) is None:                 # "13:57" = horas:minutos
            return d * 86400 + h * 3600 + mi * 60
        return d * 86400 + h * 3600 + mi * 60 + s
    partes = _T_PARTES.findall(t)
    if partes:
        mult = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        return sum(int(n) * mult[u] for n, u in partes)
    return None


def numero(texto: str) -> int | None:
    """"5.000.000" / "5,000,000" / "5M" / "6 millones" / "2.5K" -> entero."""
    t = sin_acentos(texto)
    m = re.search(r"(\d+(?:[.,]\d+)*)\s*(millones|millon|mill|kk|m|k|mil)?\b", t)
    if not m:
        return None
    cifra, suf = m.group(1), m.group(2)
    if suf in ("millones", "millon", "mill", "kk", "m", "k", "mil"):
        base = float(cifra.replace(",", ".")) if cifra.count(".") + cifra.count(",") <= 1 \
            else float(cifra.replace(".", "").replace(",", ""))
        return int(round(base * (1_000_000 if suf in ("millones", "millon", "mill", "kk", "m")
                                 else 1000)))
    return int(cifra.replace(".", "").replace(",", ""))


_PROG = re.compile(r"(\d[\d.,]*\s*[kKmM]?)\s*/\s*(\d[\d.,]*\s*[kKmM]?)")


def progreso(texto: str):
    """"2.345.000/5.000.000" -> (2345000, 5000000); None si no hay."""
    t = str(texto or "").replace("／", "/").replace("⁄", "/").replace("∕", "/")
    t = re.sub(r"(?<=\d)[oOØ]|[oOØ](?=\d)", "0", t)
    m = _PROG.search(t)
    if not m:
        return None
    a, b = numero(m.group(1)), numero(m.group(2))
    if a is None or not b:
        return None
    return a, b


# ---------------------------------------------------------- clasificar --
# Lo que el bot NUNCA hace (reglas fijas). Se mira primero.
_MANUAL = (("gec", "gasta GEC"), ("gasta", "gasta recursos"), ("spend", "gasta recursos"),
           ("constru", "construir naves"), ("build", "construir naves"),
           ("caja", "abrir cajas"), ("cofre", "abrir cajas"), ("chest", "abrir cajas"),
           ("box", "abrir cajas"), ("acelera", "acelerar"), ("speed", "acelerar"),
           ("academia", "academia"), ("academy", "academia"), ("compra", "comprar"),
           ("buy", "comprar"), ("purchase", "comprar"), ("recarga", "recargar"),
           ("mejora", "mejorar"), ("upgrade", "mejorar"), ("legion", "legiones"),
           ("masa de eco", "masas de eco"), ("eco mass", "masas de eco"),
           ("intercambi", "intercambio"), ("exchange", "intercambio"),
           ("elite", "piratas de élite"))


def clasificar(texto: str) -> dict:
    """Decide quien hace una mision: {"tipo", "accion", "meta", "motivo"}."""
    t = sin_acentos(texto)
    # el lector a veces pega las palabras ("eliminapiratasocultos"): se busca
    # tambien en el texto sin espacios
    t = t + " | " + t.replace(" ", "")
    meta = None
    for m in re.finditer(r"\d[\d.,]*(?:\s*(?:millones|millon)|\s*[mk](?![a-z]))?", t):
        n = numero(m.group(0))
        if n and (meta is None or n > meta):
            meta = n
    if "resto" in t or "recolect" in t or "mineral" in t or "cristal" in t or "aleacion" in t:
        if not any(x in t for x in ("gasta", "compra", "construy")):
            return {"tipo": "recolectar", "accion": "bot", "meta": meta,
                    "motivo": "Escombros de piratas normales: los recogen los drones"}
    if "suministros gratis" in t or "suministrosgratis" in t:
        return {"tipo": "gratis", "accion": "bot", "meta": meta,
                "motivo": "Suministros gratis (los recoge la Rutina)"}
    pirata = "pirat" in t
    sigilo = pirata and ("sigilo" in t or "stealth" in t or "ocult" in t)
    for palabra, motivo in _MANUAL:
        if palabra in t and not (palabra == "elite" and sigilo):
            return {"tipo": "manual", "accion": "manual", "meta": meta,
                    "motivo": f"Lo haces tú ({motivo})"}
    if sigilo:
        return {"tipo": "sigilo", "accion": "bot", "meta": meta,
                "motivo": "Piratas de sigilo"}
    if pirata and ("fuerza" in t or "power" in t or "strength" in t):
        return {"tipo": "fuerza_pirata", "accion": "bot", "meta": meta,
                "motivo": "Piratas normales hasta completar la fuerza"}
    if pirata:
        return {"tipo": "piratas", "accion": "bot", "meta": meta,
                "motivo": "Piratas normales"}
    if "simulac" in t or "simulation" in t:
        return {"tipo": "simulacion", "accion": "bot", "meta": meta, "motivo": "Simulación"}
    if "destacamento" in t or "detachment" in t or "expedici" in t:
        return {"tipo": "destacamento", "accion": "bot", "meta": meta,
                "motivo": "Destacamento de exploración"}
    if "ballena" in t or "whale" in t:
        return {"tipo": "ballenas", "accion": "bot", "meta": meta, "motivo": "Ballenas de éter"}
    if "explora" in t or "explore" in t or "planeta" in t or "planet" in t:
        return {"tipo": "explorar", "accion": "espera", "meta": meta,
                "motivo": "Explorar planetas: pendiente de que expliques cómo"}
    if ("arma" in t or "weapon" in t or "componente" in t or "component" in t) and \
            ("produc" in t or "fabric" in t):
        return {"tipo": "armas", "accion": "espera", "meta": meta,
                "motivo": "Producir armas: aún sin tarea en el bot"}
    return {"tipo": "otra", "accion": "manual", "meta": meta,
            "motivo": "No la reconozco: la dejo para ti"}


# ------------------------------------------------------------- memoria --
def _carpeta():
    from nucleo.rutas import carpeta_datos
    return carpeta_datos()


# Margen para decidir que un evento es una edicion nueva: si su fin se mueve
# mas de 6 h respecto al guardado, ha empezado otra vez.
NUEVA_EDICION = 6 * 3600
# version del lector de misiones: si sube, las misiones se vuelven a leer
LECTOR_V = 3
# Eventos cuyas misiones no se leen (tienen tarea propia o no tienen misiones)
# (Cosmomante si: sus misiones estan en el boton «Mision de Cosmomante» del tablero)
SIN_MISIONES = ("mision_en_predesarrollo", "mision_de_protocolo")


def fusionar(ev: dict) -> dict:
    """Junta las entradas que son el mismo evento leido distinto (por ejemplo
    «Eventosdeintercambio» y «Eventos de intercambio»). Se queda la que tiene
    mas misiones; la otra se borra."""
    orden = sorted(ev.items(), key=lambda kv: -len(kv[1].get("misiones") or []))
    principales = {}
    for k, e in orden:
        nombre = e.get("nombre") or k
        if es_cabecera(nombre) or (es_ruido(nombre) and not e.get("misiones")):
            continue
        if ignorado(clave(nombre_canonico(nombre))) or ignorado(k):
            continue
        encontrada = None
        for pk, pe in principales.items():
            otro = otro_nombre(nombre, [pe["nombre"]], {pe.get("subtitulo", ""): pe["nombre"]})
            if _compacto(nombre) == _compacto(pe["nombre"]) or \
               difflib.SequenceMatcher(None, _compacto(nombre), _compacto(pe["nombre"])).ratio() >= PARECIDO_NOMBRE or \
               (otro and _compacto(otro) == _compacto(pe["nombre"])):
                encontrada = pk
                break
        if encontrada is None:
            bueno = nombre_canonico(nombre, [p["nombre"] for p in principales.values()])
            nk = clave(bueno)
            if nk in principales:
                encontrada = nk
            else:
                principales[nk] = dict(e, nombre=bueno)
        if encontrada is not None:
            pe = principales[encontrada]
            if not pe.get("misiones") and e.get("misiones"):
                pe["misiones"] = e["misiones"]
                pe["lector_v"] = e.get("lector_v")
            if e.get("fin") and (not pe.get("fin") or e["fin"] > pe["fin"]):
                pe["fin"] = e["fin"]
    return principales


def misma_edicion(a, b) -> bool:
    """Dos horas de fin del mismo evento: la cuenta atras se lee con unos
    segundos de diferencia cada vez; solo es otra edicion si cambia horas."""
    if not a or not b:
        return a == b
    return abs(float(a) - float(b)) <= NUEVA_EDICION


def limpiar_evento(e: dict) -> dict:
    """Pone en limpio las misiones guardadas de un evento (leidas con una
    version anterior): separa las que el OCR junto, quita lo que no es una
    mision y arregla los textos. Cada mision conserva su id (y asi su
    progreso) si sale de un solo texto guardado."""
    viejas = [m for m in e.get("misiones") or [] if m.get("texto") or m.get("titulo")]
    limpias, info = tm.ordenar([tm.completo(m) for m in viejas], e.get("nombre", ""),
                               e.get("subtitulo", ""))
    usados, out = set(), []
    for m in limpias:
        vieja = viejas[m["origen"]]
        mid = vieja.get("id") if vieja.get("id") not in usados else None
        mid = mid or clave(tm.completo(m))[:40]
        while mid in usados:
            mid += "_"
        usados.add(mid)
        out.append({"id": mid, "titulo": m["titulo"], "texto": m["texto"]})
    e["misiones"] = out
    e["info"] = info or e.get("info", "")
    e["limpieza"] = tm.LIMPIEZA_V
    return e


class Memoria:
    """Eventos (comunes) y progreso de misiones (de una cuenta)."""

    def __init__(self, cuenta: str = "inst", carpeta: str | None = None):
        self.carpeta = carpeta or _carpeta()
        self.cuenta = str(cuenta).replace(":", "_")
        self.r_eventos = os.path.join(self.carpeta, "eventos_juego.json")
        self.r_prog = os.path.join(self.carpeta, f"misiones_{self.cuenta}.json")
        # con la carpeta de siempre se usa (y se amplia) el conocimiento del
        # programa: lo que pide cada evento, aprendido antes en este u otro PC
        self._con = carpeta is None

    # ---- lectura y guardado
    def eventos(self) -> dict:
        ev = _cfg.leer(self.r_eventos, defecto={}).get("eventos", {})
        if self._con:
            try:
                from nucleo import conocimiento
                sabido = conocimiento.eventos()
            except Exception:                                 # noqa: BLE001
                sabido = {}
            for k, e in ev.items():
                s = sabido.get(k) or {}
                if (e.get("misiones") is None or e.get("lector_v") != LECTOR_V) \
                        and s.get("misiones") and s.get("lector_v") == LECTOR_V:
                    e["misiones"] = [dict(m) for m in s["misiones"]]
                    e["lector_v"] = LECTOR_V
                    e["limpieza"] = s.get("limpieza")
                    e["info"] = s.get("info", "")
                elif e.get("misiones") and e.get("limpieza") != tm.LIMPIEZA_V \
                        and s.get("misiones") and s.get("lector_v") == e.get("lector_v") \
                        and not s.get("limpieza"):
                    # hay que repasar la limpieza: mejor desde el texto leido
                    # original (lo guardado ya limpio puede haber perdido algo)
                    e["misiones"] = [dict(m) for m in s["misiones"]]
        for e in ev.values():
            if e.get("misiones") and e.get("limpieza") != tm.LIMPIEZA_V:
                limpiar_evento(e)
            # las reglas pueden haber cambiado desde que se leyeron: reclasificar siempre
            for mis in e.get("misiones") or []:
                if mis.get("texto") or mis.get("titulo"):
                    mis.update(clasificar(tm.completo(mis)))
        return ev

    def _guardar_eventos(self, ev: dict, lista_t: float | None = None):
        datos = {"eventos": ev, "_v": 1}
        previo = _cfg.leer(self.r_eventos, defecto={}).get("lista_t")
        if lista_t or previo:
            datos["lista_t"] = lista_t or previo
        _cfg.guardar(self.r_eventos, datos, indent=1)

    def lista_t(self) -> float:
        """Cuando se leyo por ultima vez la LISTA DE EVENTOS (0 = nunca)."""
        return float(_cfg.leer(self.r_eventos, defecto={}).get("lista_t") or 0)

    def _prog(self) -> dict:
        return _cfg.leer(self.r_prog, defecto={})

    def _guardar_prog(self, d: dict):
        _cfg.guardar(self.r_prog, d, indent=1)

    # ---- lista de eventos
    def actualizar_lista(self, tarjetas, ahora: float | None = None) -> list[str]:
        """Apunta lo leido en LISTA DE EVENTOS: [{"nombre", "subtitulo",
        "estado", "tiempo"}]. Devuelve las claves de eventos nuevos o de
        ediciones nuevas."""
        ahora = time.time() if ahora is None else ahora
        ev = self.eventos()
        nuevos = []
        for t in tarjetas or []:
            nombre = nombre_tarjeta(t, [e.get("nombre") for e in ev.values()], subtitulos_de(ev))
            if not nombre:
                continue
            k = clave(nombre)
            if ignorado(k):
                continue
            seg = segundos(t.get("tiempo", ""))
            fin = ahora + seg if seg is not None else None
            e = ev.get(k, {"nombre": nombre, "misiones": None})
            if fin and e.get("fin") and abs(fin - e["fin"]) > NUEVA_EDICION:
                if e["fin"] <= ahora:
                    # el evento anterior ya cerro: es una edicion nueva
                    e["edicion_nueva"] = True
                    nuevos.append(k)
                elif ahora - e.get("visto", 0) < 1800:
                    # otra cuenta lo acaba de leer distinto: lectura dudosa, no se toca
                    continue
                else:
                    fin = e["fin"] if abs(fin - e["fin"]) > 2 * 86400 else fin
            elif k not in ev:
                nuevos.append(k)
            e.update({"nombre": nombre, "subtitulo": t.get("subtitulo", ""),
                      "estado": t.get("estado", ""), "visto": ahora})
            if fin:
                e["fin"] = round(fin)
            ev[k] = e
        ev = fusionar(ev)
        self._guardar_eventos(ev, lista_t=ahora if tarjetas else None)
        return nuevos

    def activos(self, ahora: float | None = None) -> list[dict]:
        """Eventos que siguen abiertos, del que acaba antes al que acaba despues."""
        ahora = time.time() if ahora is None else ahora
        out = []
        lista_t = self.lista_t()
        for k, e in fusionar(self.eventos()).items():    # sin duplicados mal leidos
            if e.get("fin") and e["fin"] <= ahora:
                continue
            # ya no sale en la lista de eventos (se leyo despues y no estaba,
            # y hace mas de 6 h que no se ve): ha terminado o ha cambiado
            visto = e.get("visto", 0)
            if lista_t and visto and visto < lista_t - 3600 and ahora - visto > 6 * 3600:
                continue
            out.append(dict(e, clave=k))
        return sorted(out, key=lambda e: e.get("fin") or 9e18)

    def necesita_leer(self, k: str) -> bool:
        if k in SIN_MISIONES:
            return False
        e = self.eventos().get(k, {})
        if time.time() - e.get("leyendo_t", 0) < 300:
            return False                    # otra cuenta lo esta leyendo ahora
        return e.get("misiones") is None or e.get("lector_v") != LECTOR_V

    def marcar_leyendo(self, k: str):
        ev = self.eventos()
        if k in ev:
            ev[k]["leyendo_t"] = round(time.time())
            self._guardar_eventos(ev)

    def guardar_misiones(self, k: str, textos, sumar: bool = False) -> list[dict]:
        """Guarda los requisitos de un evento (una sola vez). Con sumar, se
        añaden a los ya guardados (las que no estaban): en Artefactos cada
        cuenta solo ve las que le quedan por hacer."""
        ev = self.eventos()
        e = ev.setdefault(k, {"nombre": k})
        limpias, info = tm.ordenar(textos or [], e.get("nombre", ""), e.get("subtitulo", ""))
        misiones, ids = [], set()
        if sumar:
            misiones = [dict(m) for m in e.get("misiones") or []]
            ids = {m.get("id") for m in misiones}
            ya = {_compacto(tm.completo(m)) for m in misiones}
            limpias = [m for m in limpias if _compacto(tm.completo(m)) not in ya]
        for m in limpias:
            todo = tm.completo(m)
            mid = clave(todo)[:40]
            while mid in ids:
                mid += "_"
            ids.add(mid)
            misiones.append({"id": mid, "titulo": m["titulo"], "texto": m["texto"],
                             **clasificar(todo)})
        e["misiones"] = misiones
        e["info"] = info
        e["limpieza"] = tm.LIMPIEZA_V
        e["misiones_t"] = round(time.time())
        e["lector_v"] = LECTOR_V
        ev[k] = e
        self._guardar_eventos(ev)
        if self._con:                       # pasa a formar parte del programa
            try:
                from nucleo import conocimiento
                conocimiento.apuntar_eventos({k: e})
            except Exception:                                 # noqa: BLE001
                pass
        return misiones

    def mejorar_mision(self, k: str, mid: str, titulo: str, texto: str) -> bool:
        """Completa una mision guardada si ahora se ha leido entera (la
        primera vez el lector solo vio «Explorar galaxia» y no «Explora 20
        planetas»). Conserva su id (y asi su progreso)."""
        ev = self.eventos()
        e = ev.get(k) or {}
        for m in e.get("misiones") or []:
            if m.get("id") != mid:
                continue
            if len(tm.completo({"titulo": titulo, "texto": texto})) <= len(tm.completo(m)):
                return False
            m["titulo"] = titulo or m.get("titulo", "")
            m["texto"] = texto
            m.update(clasificar(tm.completo(m)))
            self._guardar_eventos(ev)
            if self._con:
                try:
                    from nucleo import conocimiento
                    conocimiento.apuntar_eventos({k: e})
                except Exception:                             # noqa: BLE001
                    pass
            return True
        return False

    # ---- progreso de esta cuenta
    def apuntar_progreso(self, k: str, mision_id: str, actual, meta=None, hecha=None):
        d = self._prog()
        ev = self.eventos().get(k, {})
        p = d.get(k, {})
        if not misma_edicion(p.get("fin"), ev.get("fin")):   # edicion nueva: empezar de cero
            p = {"fin": ev.get("fin"), "m": {}}
        m = p.setdefault("m", {}).setdefault(mision_id, {})
        m["t"] = round(time.time())
        if actual is not None:
            m["actual"] = int(actual)
        if meta:
            m["meta"] = int(meta)
        if hecha:
            m["hecha"] = True
        d[k] = p
        self._guardar_prog(d)

    def estado_mision(self, k: str, mis: dict) -> dict:
        """{"actual", "meta", "completa"} de una mision para esta cuenta."""
        ev = self.eventos().get(k, {})
        p = self._prog().get(k, {})
        if not misma_edicion(p.get("fin"), ev.get("fin")):
            p = {}
        m = p.get("m", {}).get(mis["id"], {})
        meta = m.get("meta") or mis.get("meta")
        actual = m.get("actual")
        hecha = bool(m.get("hecha")) or bool(meta and actual is not None and actual >= meta)
        return {"actual": actual, "meta": meta, "completa": hecha, "leida": bool(m)}

    def pendientes(self, tipo: str | None = None, ahora: float | None = None) -> list[dict]:
        """Misiones que hace el bot y que esta cuenta aun no ha completado,
        de los eventos activos (las del que acaba antes, primero)."""
        out = []
        for e in self.activos(ahora):
            for mis in e.get("misiones") or []:
                if mis.get("accion") != "bot" or (tipo and mis.get("tipo") != tipo):
                    continue
                st = self.estado_mision(e["clave"], mis)
                if st["completa"]:
                    continue
                out.append({"evento": e["clave"], "nombre": e.get("nombre"),
                            "fin": e.get("fin"), "mision": mis, **st})
        return out

    def misiones_leidas(self, k: str) -> bool:
        """Esta cuenta ya ha leido sus misiones de k (eventos de una sola lectura)."""
        p = self._prog().get(k, {})
        return bool(p.get("misiones_leidas")) and misma_edicion(p.get("fin"), self.eventos().get(k, {}).get("fin"))

    def marcar_misiones_leidas(self, k: str):
        d = self._prog()
        ev = self.eventos().get(k, {})
        p = d.get(k, {})
        if not misma_edicion(p.get("fin"), ev.get("fin")):
            p = {"fin": ev.get("fin"), "m": {}}
        p["misiones_leidas"] = True
        d[k] = p
        self._guardar_prog(d)

    def apuntar_lectura(self, k: str):
        """Esta cuenta acaba de mirar el progreso del evento k (aunque no
        haya cambiado nada)."""
        d = self._prog()
        ev = self.eventos().get(k, {})
        p = d.get(k, {})
        if not misma_edicion(p.get("fin"), ev.get("fin")):
            p = {"fin": ev.get("fin"), "m": {}}
        p["leido_t"] = round(time.time())
        d[k] = p
        self._guardar_prog(d)

    def leido_t(self, k: str) -> float:
        """Cuando miro esta cuenta por ultima vez el progreso del evento k (0 = nunca)."""
        p = self._prog().get(k, {})
        if not misma_edicion(p.get("fin"), self.eventos().get(k, {}).get("fin")):
            return 0
        ts = [p.get("leido_t", 0)] + [m.get("t", 0) for m in (p.get("m") or {}).values()]
        return max(ts)

    def con_misiones(self, ahora: float | None = None) -> list[str]:
        """Eventos activos con alguna mision (de quien sea)."""
        return [e["clave"] for e in self.activos(ahora)
                if e["clave"] not in SIN_MISIONES and e["clave"] not in LEER_UNA_VEZ
                and e.get("misiones")]

    def con_misiones_del_bot(self, ahora: float | None = None) -> list[str]:
        """Eventos activos con alguna mision que hace el bot."""
        return [e["clave"] for e in self.activos(ahora) if e["clave"] not in LEER_UNA_VEZ
                and any(m.get("accion") == "bot" for m in e.get("misiones") or [])]

    def resumen(self, ahora: float | None = None) -> list[dict]:
        """Para la ventana: cada evento activo con sus misiones y su estado."""
        out = []
        for e in self.activos(ahora):
            filas = []
            for mis in e.get("misiones") or []:
                st = self.estado_mision(e["clave"], mis)
                filas.append({"titulo": mis.get("titulo", ""), "texto": mis.get("texto", ""),
                              "accion": mis["accion"],
                              "motivo": mis.get("motivo", ""), **st})
            out.append({"clave": e["clave"], "nombre": e.get("nombre"),
                        "subtitulo": e.get("subtitulo", ""), "info": e.get("info", ""),
                        "fin": e.get("fin"),
                        "estado": e.get("estado", ""), "misiones": filas,
                        "leidas": e.get("misiones") is not None,
                        "leido_t": self.leido_t(e["clave"])})
        return out
