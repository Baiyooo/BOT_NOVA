"""Pone en limpio lo que el lector de texto (OCR) saca de las misiones de un
evento. Sin tocar el juego; todo puro, para poder probarlo.

El OCR suele:
  - pegar palabras ("Construyeunafuerza", "GalaxiadelaHidra", "armas40veces");
  - confundir 0 con O ("5.000.0o0", "Eliminate3OStealthPirates");
  - juntar dos tarjetas en una ("Naves Construye ... Usa GEC Gasta 2.000 GEC");
  - colar cosas que no son misiones: el nombre del evento, temporizadores
    ("Fase de enfrentamiento: 1d23:53:48"), el texto de ambientacion, listas
    de facciones, etiquetas sueltas ("¡GRATIS!", "Vista previa del bote").

Cada mision queda como {"titulo", "texto"}: el titulo de la tarjeta ("Usa
GEC") y lo que pide ("Gasta 10.000 GEC"). El texto de ambientacion se guarda
aparte como "info" del evento.
"""
from __future__ import annotations

import re
import unicodedata

# version de la limpieza: si cambia, lo guardado se vuelve a limpiar
LIMPIEZA_V = 3


def _llano(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


# ------------------------------------------------------------ vocabulario --
#  Palabras que salen en los textos del juego (sin acentos). Sirven para
#  despegar las que el OCR junta: solo se separa una palabra desconocida si
#  se puede partir entera en palabras de esta lista.
_PALABRAS = """
a al el la lo los las un una unos unas de del y e o u en con por para sin sus su se que
es son le les mas menos muy cada todo toda todos todas otro otra este esta estos estas
aqui ahi alli como cuando donde cual hasta desde entre sobre tras ya no si
total veces vez dia dias hora horas minuto minutos segundo segundos punto puntos
mision misiones evento eventos recompensa recompensas regular regulares objeto objetos
caja cajas cofre cofres nave naves flota flotas fuerza fuerzas pirata piratas oculto
ocultos sigilo elite ballena ballenas eter gec arma armas componente componentes
produccion destacamento destacamentos exploracion explorar explora explorando galaxia
galaxias planeta planetas academia actualizar actualiza actualizacion mejora mejorar
acelerar acelera aceleracion construye construir construccion gasta gastar usa usar
abre abrir elimina eliminar destruye destruir completa completar obtener obten obtiene
consigue conseguir alcanza alcanzar invoca invocar recolecta recolectar gana ganar
simulacion energia oscura oscuros oscuras oscuro materiales material vacio rayos gamma
modo unico unica desvelar desvelando desvela secreto secretos misterio misterios
medida avanza avanzar avanzan llegan llega finalmente corazon corte carmesi hidra
santuario continuaran continuar continua fase preparacion enfrentamiento experiencia
frente aliado comite gestion reliquias union conservacion civilizacion vista previa
bote nucleo deformacion intercambio modulo coleccion bendicion celestial reflejo
artefactos iluminar estrellas estrella cuantos mejor gratis protocolo predesarrollo
neural roaming cuantica extraccion recursos recurso tickets ticket tablero
use spend build destroy eliminate kill open speed up upgrade upgrades for of the
to and stealth pirates pirate fleets fleet power total minutes boxes chests explore
planets complete missions mission detachment exchange collection module free
""".split()
VOCAB = frozenset(_PALABRAS)
_SUELTAS = {"a", "y", "e", "o", "u"}         # unicas palabras de una letra

# Acentos para ensenar los textos bien escritos (el OCR los pierde)
ACENTOS = {
    "produccion": "producción", "exploracion": "exploración", "mision": "misión",
    "corazon": "corazón", "carmesi": "carmesí", "unico": "único", "unica": "única",
    "energia": "energía", "vacio": "vacío", "dia": "día", "dias": "días",
    "comite": "comité", "gestion": "gestión", "union": "unión",
    "conservacion": "conservación", "deformacion": "deformación", "nucleo": "núcleo",
    "civilizacion": "civilización", "continuaran": "continuarán", "aqui": "aquí",
    "mas": "más", "bendicion": "bendición", "preparacion": "preparación",
    "extraccion": "extracción", "cuantica": "cuántica", "cuantos": "cuántos",
    "simulacion": "simulación", "actualizacion": "actualización",
    "aceleracion": "aceleración", "construccion": "construcción", "obten": "obtén",
    "eter": "éter", "elite": "élite", "modulo": "módulo", "coleccion": "colección",
    "ahi": "ahí", "alli": "allí", "despues": "después", "facil": "fácil",
}


def _segmentar(pal: str) -> list[str] | None:
    """Parte una palabra pegada en palabras del vocabulario (las menos
    posibles). None si no se puede partir entera."""
    n = len(pal)
    mejor = [None] * (n + 1)
    mejor[0] = []
    for i in range(1, n + 1):
        for j in range(max(0, i - 16), i):
            if mejor[j] is None:
                continue
            w = pal[j:i]
            if w in VOCAB and (len(w) > 1 or w in _SUELTAS):
                cand = mejor[j] + [w]
                if mejor[i] is None or len(cand) < len(mejor[i]):
                    mejor[i] = cand
    return mejor[n]


def _como(original: str, nuevo: str) -> str:
    """nuevo con las mayusculas de original (Todo, TODO o todo)."""
    if original.isupper() and len(original) > 1:
        return nuevo.upper()
    if original[:1].isupper():
        return nuevo[:1].upper() + nuevo[1:]
    return nuevo


def _despegar(palabra: str) -> str:
    base = _llano(palabra)
    if base.isalpha() and base not in VOCAB:
        for mal, bien in (("q", "g"), ("rn", "m"), ("0", "o")):
            arreglo = base.replace(mal, bien)
            if arreglo != base and arreglo in VOCAB:
                return _como(palabra, arreglo)
    if not base.isalpha() or base in VOCAB or len(base) < 4:
        # "lluminar" (la I leida como l)
        if base.startswith("ll") and "i" + base[1:] in VOCAB:
            return "I" + palabra[1:]
        return palabra
    if palabra != palabra.lower() and palabra.upper() != palabra and not palabra[1:].islower():
        return palabra                                    # mezcla rara: no tocar
    partes = _segmentar(base)
    if partes is None and base.startswith("ll"):          # "lluminarlasestrellas"
        partes = _segmentar("i" + base[1:])
        palabra = "I" + palabra[1:]                       # la I leida como l
    if not partes or len(partes) == 1 or len(partes) > max(2, len(base) // 2):
        return palabra
    out = " ".join(partes)
    return _como(palabra, out)


def _acentuar(texto: str) -> str:
    def cambia(m):
        w = m.group(0)
        bueno = ACENTOS.get(w.lower())
        return _como(w, bueno) if bueno else w
    return re.sub(r"[A-Za-z]+", cambia, texto)


def pulir(texto: str) -> str:
    """Arregla un texto del OCR: espacios, ceros, palabras pegadas, acentos."""
    t = str(texto or "")
    t = t.replace("／", "/")
    t = re.sub(r"^[iíl!¡](?=[A-ZÁÉÍÓÚ]{3,}!)", "¡", t)          # "iGRATIS!"
    # O u o metidas en una cifra: "5.000.0o0", "5.00OGEC", "3OStealth"
    for _ in range(3):
        t = re.sub(r"(?<=\d)[oO](?=[\d.,]|[A-Z]|\b)", "0", t)
        t = re.sub(r"(?<=[\d][.,])[oO]", "0", t)
    t = re.sub(r"\b(\d)s(?= puntos)", r"\g<1>5", t)                # "1s puntos" = 15
    t = re.sub(r"\b[Ss](?=[.,]\d{3}\b)", "5", t)                   # "S.000.000" = 5.000.000
    t = re.sub(r"(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])", " ", t)       # GalaxiadelaHidra
    t = re.sub(r"(?<=[A-Za-zñÑ])(?=\d)", " ", t)                 # armas40
    t = re.sub(r"(?<=\d)(?=[A-Za-zñÑ]{2})", " ", t)              # 40veces, 2.000GEC
    t = re.sub(r"(?<=\d)(?=[A-Za-zñÑ]\b)(?!s\b)", " ", t)
    t = re.sub(r"\)(?=\w)", ") ", t)                             # (HUF)Frente
    t = re.sub(r"(?<=\w)\(", " (", t)
    t = re.sub(r"(?<=\w)\((?=s\))", "(", t)
    t = re.sub(r"\bdia \(s\)", "día(s)", t, flags=re.I)
    t = re.sub(r"(?<=[a-z])\"(?=\w)", ' "', t)                    # por"Materiales
    t = re.sub(r"\"\.(?=\w)", '". ', t)
    t = re.sub(r"(?<=[a-z])[.:,](?=[A-Za-z])", lambda m: m.group(0) + " ", t)
    t = re.sub(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]+", lambda m: _despegar(m.group(0)), t)
    t = re.sub(r"\s+", " ", t).strip()
    # tras una coma no va mayuscula ("..., Finalmente llegan")
    t = re.sub(r"(?<=, )([A-Z][a-z]+)\b",
               lambda m: m.group(1).lower() if m.group(1).lower() in _COMUNES else m.group(1), t)
    return _acentuar(t)


#  palabras del vocabulario que no son nombres propios
_COMUNES = VOCAB - {"hidra", "corte", "carmesi", "galaxia", "corazon", "santuario"}


# --------------------------------------------------------------- misiones --
#  Titulos de las tarjetas de mision (como salen en el juego)
TITULOS = ("Usa GEC", "Usar objetos", "Naves", "Destacamento de exploración",
           "Producción de componentes", "Producción de armas", "Actualizar Academia",
           "Explorar galaxia", "Elimina piratas ocultos", "Speed Up", "Acelerar")
#  Verbos con los que empieza lo que pide una mision
VERBOS = ("recoge", "recolecta", "construye", "construir", "gasta", "gastar", "completa", "completar", "abrir",
          "abre", "actualiza", "explora", "elimina", "eliminate", "destruye", "destruir",
          "consigue", "obten", "alcanza", "invoca", "recolecta", "gana", "usa", "usar",
          "speed up", "acelera", "mata", "derrota", "kill", "destroy", "build", "spend",
          "open", "collect", "reach", "upgrade", "produce", "fabrica")
#  Palabras que hacen que algo sea una mision (si no hay ninguna, no lo es)
_ACCION = ("recoge ", "recoger suministros", "construy", "constru", "gast", "complet", "abri", "abre", "actualiz", "explor",
           "elimin", "destru", "consigu", "obten", "alcanz", "invoc", "recolect", "usa ",
           "usar", "speed", "aceler", "mata", "derrot", "kill", "destroy", "build",
           "spend", "open", "collect", "reach", "upgrade", "produc", "fabric", "pirat",
           "ballena", "whale", "simulac", "destacamento")
#  De que va cada mision, por si el OCR no ha leido el titulo
_TITULO_DE = (("gec", "Usa GEC"), ("caja", "Usar objetos"), ("cofre", "Usar objetos"),
              ("box", "Usar objetos"), ("flotas de naves", "Naves"),
              ("destacamento", "Destacamento de exploración"),
              ("detachment", "Destacamento de exploración"),
              ("academia", "Actualizar Academia"), ("planeta", "Explorar galaxia"),
              ("ocult", "Elimina piratas ocultos"), ("stealth", "Elimina piratas ocultos"),
              ("sigilo", "Elimina piratas ocultos"), ("speed up", "Speed Up"),
              ("acelera", "Acelerar"), ("produccion de arma", "Producción de armas"),
              ("produccion de componente", "Producción de componentes"),
              ("flotas pirata", "Fuerza pirata"), ("pirat", "Piratas"),
              ("simulac", "Simulación"), ("ballena", "Ballenas de éter"))


def _es_tiempo(t: str) -> bool:
    return bool(re.search(r"\d+\s*d?\s*\d{1,2}:\d{2}", t))


def _cortes(texto: str) -> list[str]:
    """Parte un texto que junta varias tarjetas: corta delante de cada
    titulo conocido."""
    llano = _llano(texto)
    pos = set()
    for tit in TITULOS:
        for m in re.finditer(r"\b" + re.escape(_llano(tit)) + r"\b", llano):
            pos.add(m.start())
    # "Destacamento de" / "Producción de" cortados: tambien son titulos si
    # justo despues viene lo que piden ("Destacamento de Completa 15 ...")
    for m in re.finditer(r"\b(destacamento de|produccion de) (?=(completa|elimina|gasta)\b)", llano):
        pos.add(m.start())
    # solo donde empieza una tarjeta: el titulo va en mayuscula ("Naves"),
    # no en medio de una frase ("... flotas de naves")
    pos = sorted(p for p in pos if p > 0 and len(llano) == len(texto) and texto[p].isupper())
    # no cortar dentro de otro titulo que empieza antes y lo contiene
    trozos, ini = [], 0
    for p in pos:
        if p - ini < 3:
            continue
        previo = llano[ini:p]
        if any(_llano(t).startswith(previo.strip()) and len(previo.strip()) > 2 and
               llano[ini:].startswith(_llano(t)) for t in TITULOS):
            continue
        trozos.append(texto[ini:p].strip())
        ini = p
    trozos.append(texto[ini:].strip())
    return [t for t in trozos if t]


def _separar(trozo: str) -> tuple[str, str]:
    """(titulo, lo que pide) de un trozo."""
    llano = _llano(trozo)
    # titulo con nivel y luego lo que pide («Actualizar Academia 3 Actualiza
    # la academia 10 veces», en Artefactos)
    m = re.match(r"^(.{3,45}?\s\d{1,2})\s+(.+)$", trozo)
    if m and any(_llano(m.group(2)).startswith(v) for v in VERBOS) and \
            not re.search(r"\d", m.group(1)[:-2]):
        return m.group(1).strip(), m.group(2).strip()
    for tit in sorted(TITULOS, key=len, reverse=True):
        lt = _llano(tit)
        if llano.startswith(lt) and (len(llano) == len(lt) or not llano[len(lt)].isalpha()):
            return tit, trozo[len(tit):].strip(" :-·")
    m = re.match(r"(destacamento de|produccion de)\s+(?=(completa|elimina|gasta)\b)", llano)
    if m:
        return "", trozo[m.end():].strip()               # titulo cortado: se deduce
    # lo que va antes del primer verbo, si es corto, es el titulo
    for v in VERBOS:
        m = re.search(r"\b" + re.escape(v) + r"\b", llano)
        if m and 0 < m.start() <= 30:
            antes = trozo[:m.start()].strip(" :-·")
            pide = trozo[m.start():].strip()
            # basura del OCR ("USOUCL"): una palabra en mayusculas que no existe
            if re.fullmatch(r"[A-Z0-9]{3,}", antes) and _llano(antes) not in VOCAB:
                antes = ""
            if antes and antes.split()[0].lower() not in ("de", "la", "el", "y", "minutos"):
                return antes, pide
            return "", pide
    return "", trozo


def _titulo_para(pide: str) -> str:
    llano = _llano(pide)
    for clave_, tit in _TITULO_DE:
        if clave_ in llano:
            return tit
    return ""


def _completar_titulo(titulo: str, pide: str) -> str:
    """'Producción de' -> 'Producción de armas' si lo que pide habla de armas."""
    lt = _llano(titulo).strip()
    candidatos = [t for t in TITULOS if _llano(t).startswith(lt) and len(_llano(t)) > len(lt)]
    if not titulo or candidatos == []:
        return titulo or _titulo_para(pide)
    for t in candidatos:
        if _llano(t).split()[-1].rstrip("s") in _llano(pide):
            return t
    return candidatos[0]


#  Las pocas que salen en ingles, en espanol
_TRADUCIR = ((r"^Eliminate (\d[\d.,]*) Stealth Pirates$", r"Elimina \1 piratas ocultos"),
             (r"^Speed up upgrades for a total of (\d[\d.,]*) minutes$",
              r"Acelera mejoras durante un total de \1 minutos"),
             (r"^Speed Up$", "Acelerar"))


def traducir(texto: str) -> str:
    for patron, cambio in _TRADUCIR:
        texto = re.sub(patron, cambio, texto, flags=re.I)
    return texto


def es_mision(texto: str) -> bool:
    t = _llano(texto).replace("collection", "") + " "
    return any(a in t for a in _ACCION)


def _es_info(texto: str) -> bool:
    """Texto de ambientacion o de como se ganan puntos (no es una mision)."""
    t = _llano(texto)
    return len(t) > 70 and (t.count(".") + t.count(",") >= 1) and \
        not re.search(r"\b(completa|gasta|elimina|destruye|construye|abrir|explora)\b \d", t)


def _info_limpia(texto: str) -> str:
    """Una descripcion leida a medias: empieza en la primera frase entera
    y acaba en la ultima frase entera."""
    t = texto.strip()
    if t[:1].islower():
        m = re.search(r"[.!?]\s+(?=[A-ZÁÉÍÓÚ¡¿])", t)
        if m:
            t = t[m.end():]
    if not re.search(r"[.!?]\"?$", t):
        m = list(re.finditer(r"[.!?]\"?(?=\s|$)", t))
        if m:
            t = t[:m[-1].end()]
        else:
            t = t.rstrip(" ,;:") + "…"
    return t.strip()


def ordenar(textos, nombre: str = "", subtitulo: str = "") -> tuple[list[dict], str]:
    """De lo leido en una pantalla de misiones saca ([{"titulo", "texto",
    "origen"}], info). "origen" es el indice del texto leido del que sale
    cada mision (para conservar su progreso)."""
    ev = _llano(nombre).strip()
    sub = _llano(subtitulo).strip()
    misiones, vistas, infos = [], set(), []
    for i, crudo in enumerate(textos or []):
        t = pulir(crudo)
        llano = _llano(t)
        if len(llano) < 4 or _es_tiempo(llano):
            continue
        if re.fullmatch(r"(fase de [a-z ]+|activo|abierto|proximamente)[: ]*", llano):
            continue
        # el nombre del evento (con o sin su subtitulo)
        compacto = re.sub(r"[^a-z]", "", llano)
        if ev and compacto in (re.sub(r"[^a-z]", "", ev),
                               re.sub(r"[^a-z]", "", ev + sub), re.sub(r"[^a-z]", "", ev + "santuario de la hidra")):
            continue
        # lista de facciones o clasificacion: varios codigos entre parentesis
        if len(re.findall(r"\([A-Z]{2,4}\w?\)", t)) >= 2:
            continue
        if _es_info(t) and not es_mision(t.split(".")[0]) or \
                _es_info(t) and not re.search(r"\d", t) and "gana" not in llano:
            infos.append(t)
            continue
        if _es_info(t):
            infos.append(t)
            continue
        for trozo in _cortes(t):
            titulo, pide = _separar(trozo)
            if not pide and titulo and not es_mision(titulo):
                continue
            if not es_mision(titulo + " " + pide):
                continue
            if pide[:1].islower() and not titulo:
                continue                                  # final de otra tarjeta
            titulo = _completar_titulo(titulo, pide)
            if titulo and _llano(pide) == _llano(titulo):
                pide = ""
            firma = re.sub(r"[^a-z0-9]", "", _llano(pide or titulo))
            if firma in vistas:
                continue
            vistas.add(firma)
            pide = traducir(pide[:1].upper() + pide[1:])
            titulo = traducir(titulo)
            misiones.append({"titulo": titulo, "texto": pide, "origen": i})
    # de varias lecturas de la misma descripcion, la mas larga
    info = ""
    if infos:
        info = _info_limpia(max(infos, key=len))
    return misiones, info


def completo(m: dict) -> str:
    """Titulo y texto juntos (para clasificar y comparar)."""
    return " ".join(x for x in (m.get("titulo"), m.get("texto")) if x).strip()
