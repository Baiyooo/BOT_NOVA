"""Reparto de piratas entre cuentas: reclamos y turnos compartidos por archivo."""
from __future__ import annotations

import time

from nucleo.rutas import carpeta_diag


class _Reparto:
    """Reparto de piratas entre cuentas: reclamos y turnos compartidos por archivo."""

    def _ruta_reclamos(self):
        import os
        return os.path.join(os.path.dirname(carpeta_diag()), "piratas_reclamados.json")

    def _leer_reclamos(self) -> list:
        import json
        try:
            with open(self._ruta_reclamos(), encoding="utf-8") as fh:
                d = json.load(fh)
            ahora = time.time()
            return [r for r in d if isinstance(r, list) and len(r) == 4
                    and ahora - r[2] < self.RECLAMO_SEG]
        except (OSError, ValueError):
            return []

    def _reclamar(self, p, seg=None):
        import json
        import os
        yo = str(getattr(self.ctrl, "name", ""))
        d = [r for r in self._leer_reclamos()
             if not (r[3] == yo and abs(r[0] - p[0]) < 45 and abs(r[1] - p[1]) < 45)]
        # seg: cuanto dura la reserva (corta mientras se intenta)
        d.append([int(p[0]), int(p[1]),
                  time.time() - self.RECLAMO_SEG + (seg or self.RECLAMO_SEG), yo])
        try:
            os.makedirs(os.path.dirname(self._ruta_reclamos()), exist_ok=True)
            tmp = f"{self._ruta_reclamos()}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(d, fh)
            os.replace(tmp, self._ruta_reclamos())
        except OSError:
            pass

    def _de_otra_cuenta(self, p, reclamos) -> bool:
        yo = str(getattr(self.ctrl, "name", ""))
        return any(r[3] != yo and abs(r[0] - p[0]) < 45 and abs(r[1] - p[1]) < 45
                   for r in reclamos)

    def _limpiar_recientes(self):
        ahora = time.time()
        self.recientes = [r for r in self.recientes if ahora - r[2] < self.RECIENTE_SEG]

    def _reciente(self, p):
        return any(abs(p[0] - x) < 45 and abs(p[1] - y) < 45 for x, y, _ in self.recientes)

    def _ruta_turno(self):
        import os
        return self._ruta_turno_f or os.path.join(os.path.dirname(carpeta_diag()),
                                                  "piratas_turno.json")

    def _turno_io(self, fn):
        """Lee, cambia (fn(estado) -> resultado) y guarda el archivo de turnos,
        con un cerrojo de archivo para que dos procesos no se pisen."""
        import json
        import os
        ruta = self._ruta_turno()
        cerrojo = ruta + ".lock"
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
        except OSError:
            pass
        fd = None
        fin = time.time() + 3.0
        while time.time() < fin:
            try:
                fd = os.open(cerrojo, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:                                   # cerrojo huerfano
                    if time.time() - os.path.getmtime(cerrojo) > 10:
                        os.remove(cerrojo)
                except OSError:
                    pass
                time.sleep(0.05)
            except OSError:
                break
        try:
            try:
                with open(ruta, encoding="utf-8") as fh:
                    est = json.load(fh)
                if not isinstance(est, dict):
                    est = {}
            except (OSError, ValueError):
                est = {}
            est.setdefault("activas", {})
            est.setdefault("dueno", None)
            est.setdefault("desde", 0)
            est.setdefault("ultimo", "")
            est.setdefault("libre", 0)
            res = fn(est)
            try:
                tmp = f"{ruta}.{os.getpid()}.tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(est, fh)
                os.replace(tmp, ruta)
            except OSError:
                pass
            return res
        finally:
            if fd is not None:
                os.close(fd)
                try:
                    os.remove(cerrojo)
                except OSError:
                    pass

    def _yo(self):
        return str(getattr(self.ctrl, "name", ""))

    def _poda(self, est, ahora):
        est["activas"] = {k: v for k, v in est["activas"].items()
                          if ahora - v < self.LATIDO_SEG}
        d = est["dueno"]
        if d and (d not in est["activas"] or ahora - est["desde"] > self.TURNO_MAX):
            est["dueno"], est["ultimo"], est["libre"] = None, d, ahora

    def turno_latido(self):
        yo, ahora = self._yo(), time.time()

        def f(est):
            est["activas"][yo] = ahora
            self._poda(est, ahora)
        self._turno_io(f)

    def turno_otras_activas(self) -> bool:
        yo, ahora = self._yo(), time.time()

        def f(est):
            est["activas"][yo] = ahora
            self._poda(est, ahora)
            return len(est["activas"]) > 1
        return self._turno_io(f)

    def turno_pedir(self) -> bool:
        """True si ahora le toca a esta cuenta mandar una flota."""
        yo, ahora = self._yo(), time.time()

        def f(est):
            est["activas"][yo] = ahora
            self._poda(est, ahora)
            if est["dueno"] == yo:
                return True
            if est["dueno"]:
                return False
            est["dueno"], est["desde"] = yo, ahora         # libre: lo coge quien llegue primero
            return True
        return self._turno_io(f)

    def turno_soltar(self):
        yo, ahora = self._yo(), time.time()

        def f(est):
            if est["dueno"] == yo:
                est["dueno"], est["ultimo"], est["libre"] = None, yo, ahora
        self._turno_io(f)

    def turno_salir(self):
        yo = self._yo()

        def f(est):
            est["activas"].pop(yo, None)
            if est["dueno"] == yo:
                est["dueno"], est["ultimo"], est["libre"] = None, yo, time.time()
        try:
            self._turno_io(f)
        except Exception:                                  # noqa: BLE001
            pass
