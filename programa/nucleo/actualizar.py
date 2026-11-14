"""Actualizador de NovaBot: instala un paquete NovaBot.zip sobre la carpeta `programa`.

    python -m nucleo.actualizar NovaBot.zip      (desde la carpeta programa; lo usa el bot al abrirse)

Pasos (si falla cualquiera, no se cambia nada o se deshace):
  1. Abre el zip y comprueba su manifiesto (manifiesto.json con el SHA-256 de cada archivo).
  2. Comprueba que los .py nuevos compilan.
  3. Guarda una copia de lo actual en  programa_copias/<fecha>  (conserva las 5 ultimas).
  4. Copia los archivos nuevos (solo codigo, iconos y textos; NUNCA datos).
Los datos del usuario (ajustes, rutinas, estadisticas, capturas, errores) viven en
%LOCALAPPDATA%\\NovaBot y no se tocan; las versiones nuevas migran su formato solas
(config.migrar). Despues, la ventana abierta detecta el cambio y se relanza sola.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

EXTENSIONES = (".py", ".ico", ".txt", ".bat", ".png", ".json", ".onnx")
#  .json solo en estas carpetas; .onnx solo en conocimiento/
CON_JSON = ("recursos/", "conocimiento/")
PROHIBIDOS = ("acceso.txt", "error_gui.log", "instalacion.log")
COPIAS = 5
#  archivos que van junto a la carpeta programa (fuera de ella)
RAIZ = ("BOT.bat", "EMPAQUETAR.bat", "LEEME.txt")
#  los .bat de antes: ahora todo lo hace BOT.bat (se apartan, no se borran)
BAT_ANTIGUOS = ("ACTUALIZAR.bat", "ADB.bat", "DIAGNOSTICO.bat", "INSTALAR.bat")


class ErrorActualizar(Exception):
    pass


def _sha(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _permitido(rel: str) -> bool:
    """Que archivos pueden ir en un paquete (nunca datos de nadie)."""
    f = rel.lower()
    if f == "experiencia.json":                 # el de versiones antiguas: va en conocimiento/
        return False
    if f.endswith(".json"):
        return rel.startswith(CON_JSON)
    if f.endswith(".onnx"):
        return rel.startswith("conocimiento/")
    return True


def _instalar_conocimiento(origen, destino_archivo, rel):
    """El conocimiento no se pisa: se junta con el de este PC."""
    import json as _json
    from nucleo import conocimiento as _con
    nombre = os.path.basename(rel)
    vieja = os.path.join(os.path.dirname(os.path.dirname(destino_archivo)), nombre)
    if nombre == _con.EXPERIENCIA and os.path.exists(vieja) and not os.path.exists(destino_archivo):
        shutil.move(vieja, destino_archivo)       # la de versiones antiguas: se junta, no se pierde
    if not os.path.exists(destino_archivo):
        shutil.copy2(origen, destino_archivo)
        return
    if nombre in (_con.EXPERIENCIA, _con.EVENTOS):
        def leer(r):
            try:
                with open(r, encoding="utf-8") as fh:
                    d = _json.load(fh)
                return d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                return {}
        local, llega = leer(destino_archivo), leer(origen)
        junto = (_con.fusionar_experiencia(local, llega) if nombre == _con.EXPERIENCIA
                 else _con.fusionar_eventos(local, llega))
        tmp = destino_archivo + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            _json.dump(junto, fh, indent=1, sort_keys=True, ensure_ascii=False)
        os.replace(tmp, destino_archivo)
    elif os.path.getmtime(origen) > os.path.getmtime(destino_archivo):
        shutil.copy2(origen, destino_archivo)     # el detector: solo si el del paquete es mas nuevo


def _instalar_raiz(z, raiz_zip, raiz_man, carpeta, copia):
    """BOT.bat, EMPAQUETAR.bat y LEEME.txt (junto a programa)."""
    for nombre, sha in (raiz_man or {}).items():
        if nombre not in RAIZ:
            continue
        try:
            datos = z.read(raiz_zip + "_raiz/" + nombre)
        except KeyError:
            continue
        if hashlib.sha256(datos).hexdigest() != sha:
            continue
        dst = os.path.join(carpeta, nombre)
        try:
            if os.path.isfile(dst):
                shutil.copy2(dst, os.path.join(copia, nombre))
            with open(dst, "wb") as fh:
                fh.write(datos)
        except OSError:
            pass
    apartar_bat_antiguos(carpeta)


def apartar_bat_antiguos(carpeta) -> list[str]:
    """Mueve los .bat que ya no se usan a programa_copias\\bat_antiguos."""
    movidos = []
    if not os.path.exists(os.path.join(carpeta, "BOT.bat")):
        return movidos
    dest = os.path.join(carpeta, "programa_copias", "bat_antiguos")
    for nombre in BAT_ANTIGUOS:
        p = os.path.join(carpeta, nombre)
        if os.path.isfile(p):
            try:
                os.makedirs(dest, exist_ok=True)
                shutil.move(p, os.path.join(dest, nombre))
                movidos.append(nombre)
            except OSError:
                pass
    return movidos


def crear_manifiesto(carpeta_origen, version):
    """Lista {archivo: sha256} de un paquete (lo usa empaquetar.py). El
    conocimiento (programa/conocimiento) va en su propia lista."""
    arch = {}
    for r, _, fs in os.walk(carpeta_origen):
        for f in fs:
            p = os.path.join(r, f)
            rel = os.path.relpath(p, carpeta_origen).replace("\\", "/")
            if f.lower().endswith(EXTENSIONES) and f not in PROHIBIDOS and "__pycache__" not in rel \
                    and _permitido(rel):
                arch[rel] = _sha(p)
    con = {k: v for k, v in arch.items() if k.startswith("conocimiento/")}
    arch = {k: v for k, v in arch.items() if k not in con}
    padre = os.path.dirname(os.path.abspath(carpeta_origen))
    raiz = {n: _sha(os.path.join(padre, n)) for n in RAIZ if os.path.isfile(os.path.join(padre, n))}
    return {"version": version, "creado": time.strftime("%Y-%m-%d %H:%M:%S"), "archivos": arch,
            "conocimiento": con, "raiz": raiz}


# ------------------------------------------------------- al abrir el bot --
def _num_version(v) -> tuple:
    import re
    return tuple(int(x) for x in re.findall(r"\d+", str(v))) or (0,)


def _leer_manifiesto(zip_path):
    try:
        with zipfile.ZipFile(zip_path) as z:
            man = next((n for n in z.namelist() if n.endswith("manifiesto.json")), None)
            return json.loads(z.read(man).decode("utf-8")) if man else None
    except (OSError, zipfile.BadZipFile, ValueError, KeyError):
        return None


def buscar_paquete(destino):
    """El NovaBot*.zip mas nuevo que haya en Descargas o junto a BOT.bat
    (los de la carpeta «paquetes» son los que exporta este PC: no cuentan)."""
    sitios = [os.path.join(os.path.expanduser("~"), "Downloads"), os.path.dirname(destino)]
    mejor = None
    for d in sitios:
        try:
            nombres = os.listdir(d)
        except OSError:
            continue
        for f in nombres:
            if f.lower().startswith("novabot") and f.lower().endswith(".zip"):
                p = os.path.join(d, f)
                man = _leer_manifiesto(p)
                # solo paquetes de esta forma del programa (version "mayor.menor"
                # y con main.py): nunca uno de las versiones antiguas sin carpetas
                if man and "main.py" in (man.get("archivos") or {}) \
                        and re.fullmatch(r"\d+\.\d+", str(man.get("version", ""))):
                    clave = (_num_version(man.get("version")), os.path.getmtime(p))
                    if mejor is None or clave > mejor[0]:
                        mejor = (clave, p, man)
    return (mejor[1], mejor[2]) if mejor else (None, None)


def automatica(destino, log=print):
    """Al abrir el bot: si hay un paquete con una version mas nueva, se instala.
    Si es la misma version pero su conocimiento aun no esta (porque lo
    instalo un actualizador antiguo), se instala solo el conocimiento.
    Devuelve "codigo", "conocimiento" o None."""
    try:
        apartar_bat_antiguos(os.path.dirname(destino))
    except Exception:                                            # noqa: BLE001
        pass
    zp, man = buscar_paquete(destino)
    if not zp:
        return None
    instalada = _version_instalada(destino)
    if _num_version(man.get("version")) > _num_version(instalada):
        aplicar(zp, destino, log)
        return "codigo"
    falta = [rel for rel in man.get("conocimiento", {})
             if not os.path.exists(os.path.join(destino, *rel.split("/")))]
    padre = os.path.dirname(destino)
    falta += [n for n, sha in man.get("raiz", {}).items()
              if not os.path.isfile(os.path.join(padre, n)) or _sha(os.path.join(padre, n)) != sha]
    if falta and _num_version(man.get("version")) == _num_version(instalada):
        aplicar(zp, destino, log, solo_conocimiento=True)
        return "conocimiento"
    return None


def _version_instalada(destino):
    try:
        ns = {}
        with open(os.path.join(destino, "version.py"), encoding="utf-8") as fh:
            exec(fh.read(), ns)                                  # noqa: S102
        return ns.get("VERSION", "?")
    except Exception:                                            # noqa: BLE001
        return "?"


def aplicar(zip_path, destino, log=print, solo_conocimiento=False):
    """Instala el paquete. Devuelve (version_vieja, version_nueva). Lanza ErrorActualizar.
    El conocimiento va aparte en el manifiesto ("conocimiento"): los
    actualizadores antiguos lo ignoran y el nuevo lo junta con el de este PC."""
    destino = os.path.abspath(destino)
    if not os.path.isfile(zip_path):
        raise ErrorActualizar(f"No encuentro el archivo {zip_path}")
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise ErrorActualizar("El archivo no es un zip valido (¿descarga incompleta?).") from e
    with z:
        if z.testzip() is not None:
            raise ErrorActualizar("El zip esta danado.")
        nombres = z.namelist()
        # el zip puede traer una carpeta raiz (NovaBot/programa/...) o ir directo
        man = next((n for n in nombres if n.endswith("manifiesto.json")), None)
        if man is None:
            raise ErrorActualizar("El paquete no trae manifiesto.json: no es un paquete de NovaBot.")
        raiz = man[:-len("manifiesto.json")]
        manifiesto = json.loads(z.read(man).decode("utf-8"))
        nuevos = {} if solo_conocimiento else dict(manifiesto.get("archivos", {}))
        nuevos.update(manifiesto.get("conocimiento", {}))
        if not nuevos:
            raise ErrorActualizar("El manifiesto esta vacio.")
        tmp = tempfile.mkdtemp(prefix="novabot_upd_")
        try:
            for rel, sha in nuevos.items():
                if rel.startswith("/") or ".." in rel.split("/") or os.path.basename(rel) in PROHIBIDOS \
                        or not rel.lower().endswith(EXTENSIONES) or not _permitido(rel):
                    raise ErrorActualizar(f"Archivo no permitido en el paquete: {rel}")
                try:
                    datos = z.read(raiz + rel)
                except KeyError as e:
                    raise ErrorActualizar(f"Falta {rel} en el zip.") from e
                if hashlib.sha256(datos).hexdigest() != sha:
                    raise ErrorActualizar(f"{rel} esta corrupto (no coincide su huella).")
                p = os.path.join(tmp, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as fh:
                    fh.write(datos)
                try:                            # conservar la fecha del archivo (el detector la usa)
                    info = z.getinfo(raiz + rel)
                    t = time.mktime(info.date_time + (0, 0, -1))
                    os.utime(p, (t, t))
                except (KeyError, OverflowError, ValueError):
                    pass
            for rel in nuevos:                                   # que el codigo compile
                if rel.endswith(".py"):
                    ruta_py = os.path.join(tmp, *rel.split("/"))
                    try:
                        with open(ruta_py, encoding="utf-8") as fh:
                            compile(fh.read(), rel, "exec")
                    except (SyntaxError, UnicodeDecodeError, ValueError) as e:
                        raise ErrorActualizar(f"{rel} tiene un error de sintaxis: {e}") from e
            vieja = _version_instalada(destino)
            # copia de seguridad de lo que se va a reemplazar
            copias = os.path.join(os.path.dirname(destino), "programa_copias")
            copia = os.path.join(copias, time.strftime("%Y%m%d_%H%M%S") + f"_{vieja}")
            os.makedirs(copia, exist_ok=True)
            for rel in nuevos:
                orig = os.path.join(destino, *rel.split("/"))
                if os.path.isfile(orig):
                    os.makedirs(os.path.dirname(os.path.join(copia, *rel.split("/"))), exist_ok=True)
                    shutil.copy2(orig, os.path.join(copia, *rel.split("/")))
            try:
                antiguas = sorted(os.listdir(copias))[:-COPIAS]
                for a in antiguas:
                    shutil.rmtree(os.path.join(copias, a), ignore_errors=True)
            except OSError:
                pass
            # instalar; si algo falla, se restaura la copia
            hechos = []
            try:
                # la ventana (interfaz/ y main.py) la ultima: al cambiar se relanza sola
                for rel in sorted(nuevos, key=lambda r: (r == "main.py" or r.startswith("interfaz/"), r)):
                    dst = os.path.join(destino, *rel.split("/"))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if rel.startswith("conocimiento/"):
                        _instalar_conocimiento(os.path.join(tmp, *rel.split("/")), dst, rel)
                    else:
                        shutil.copy2(os.path.join(tmp, *rel.split("/")), dst)
                    hechos.append(rel)
            except OSError as e:
                for rel in hechos:
                    b = os.path.join(copia, *rel.split("/"))
                    if os.path.isfile(b):
                        shutil.copy2(b, os.path.join(destino, *rel.split("/")))
                raise ErrorActualizar(f"No he podido copiar los archivos ({e}); he dejado todo como estaba.") from e
            _instalar_raiz(z, raiz, manifiesto.get("raiz", {}), os.path.dirname(destino), copia)
            log(f"Actualizado {vieja} -> {manifiesto.get('version', '?')} ({len(hechos)} archivos). "
                f"Copia de lo anterior en {copia}")
            return vieja, manifiesto.get("version", "?")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    if len(argv) < 2:
        print("Uso: python -m nucleo.actualizar NovaBot.zip")
        return 2
    destino = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # la carpeta programa
    try:
        aplicar(argv[1].strip('"'), destino)
        print("Listo. Si el bot esta abierto, se reiniciara solo en unos segundos.")
        return 0
    except ErrorActualizar as e:
        print(f"NO se ha actualizado: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
