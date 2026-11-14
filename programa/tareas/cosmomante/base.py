"""Cosmomante: dados, multiplicadores, metas y su estrategia (parte comun)."""
from __future__ import annotations

import time

import cv2
import numpy as np

from nucleo import config as _cfg
from tareas.recompensas import Recompensas
from tareas.cosmomante import mapa as cm
from vision.detectores import buscar_cerrar_x
from nucleo.rutas import carpeta_diag
from vision.cifras import leer_cifras
from vision.plantillas import localizar, localizar_todos


class _CosmomanteBase(Recompensas):
    """Parte comun de Cosmomante: abrir el evento, leer el progreso semanal,
    tirar dados, reclamar metas y leer el tablero. La tarea publica es
    `Cosmomante`, que anade el mapa, los multiplicadores y el ascenso."""

    NOMBRE = "Cosmomante"
    NORMALES = True
    # filas "Usa 10 / 30 / 50 / 100 dados normales" de Mision de protocolo >
    # Cosmomante (y del numero "10/100"), en una captura de 1600x900
    FILAS_META = (335, 485, 632, 780)

    def _en_tablero(self, img) -> bool:
        return localizar(img, "inicio")[0] >= 0.75

    def _abrir_lista(self) -> bool:
        if not self.ir_a_base():
            return False
        img = self.cap("base")
        p, c, _ = localizar(img, "eventos")
        if p < 0.80:
            self.log("  No veo el boton Eventos.")
            return False
        self.ctrl.tap((c[0], c[1] - int(img.shape[0] * 0.06)))
        time.sleep(2.5)
        return True

    def _buscar_en_lista(self, nombre, umbral):
        for _ in range(5):
            img = self.cap("lista")
            p, c, _ = localizar(img, nombre)
            if p >= umbral:
                return c
            h, w = img.shape[:2]       # bajar la lista
            self.ctrl.drag((int(w * 0.55), int(h * 0.75)), (int(w * 0.55), int(h * 0.35)))
            time.sleep(1.2)
        return None

    def _abrir(self) -> bool:
        if not self._abrir_lista():
            return False
        c = self._buscar_en_lista("cosmo_lista", 0.70)
        if c is None:
            self.log("  No encuentro Cosmomante en la lista de eventos.")
            return False
        self.ctrl.tap(c)
        return self.esperar(self._en_tablero, 8.0, etiqueta="tablero") is not None

    def _cerrar_todo(self):
        for _ in range(4):
            img = self.cap("salir")
            if self.en_base(img) or localizar(img, "eventos")[0] >= 0.80:
                return
            x = buscar_cerrar_x(img)
            if x is None:
                self.volver_a_base()
                return
            self.ctrl.tap(x)
            time.sleep(1.8)

    def _abrir_protocolo_cosmo(self):
        """Abre Mision de protocolo > Cosmomante. Devuelve la captura o None."""
        if not self._abrir_lista():
            return None
        c = self._buscar_en_lista("protocolo", 0.85)
        if c is None:
            self.log("  No encuentro Mision de protocolo en la lista.")
            self._cerrar_todo()
            return None
        self.ctrl.tap(c)
        time.sleep(3.0)
        for _ in range(3):
            img = self.cap("protocolo")
            h, w = img.shape[:2]
            p, cp, _ = localizar(img, "cosmo_pestana")
            if p >= 0.85 and cp[0] < w * 0.25:
                self.ctrl.tap(cp)
                time.sleep(2.0)
                return self.cap("protocolo_cosmo")
            self.ctrl.drag((int(w * 0.12), int(h * 0.80)), (int(w * 0.12), int(h * 0.35)))
            time.sleep(1.2)
        self.log("  No encuentro la pestana Cosmomante en Mision de protocolo.")
        self._cerrar_todo()
        return None

    def _leer_metas(self, img):
        h, w = img.shape[:2]
        kx, ky = w / 1600.0, h / 900.0
        lecturas = {}
        for y in self.FILAS_META:
            nums = leer_cifras(img, (1415 * kx, (y - 17) * ky, 1545 * kx, (y + 17) * ky))
            if len(nums) == 2 and nums[1] in (10, 30, 50, 100, 150, 200):
                lecturas[nums[1]] = nums[0]
        return lecturas

    def progreso_semana(self):
        """Dados normales usados esta semana (Mision de protocolo >
        Cosmomante). None si no se puede leer con seguridad."""
        img = self._abrir_protocolo_cosmo()
        if img is None:
            return None
        lecturas = self._leer_metas(img)
        self._cerrar_todo()
        if not lecturas:
            self.log("  No he podido leer el progreso de los dados normales.")
            return None
        usados = max(lecturas.values())
        # todas las filas cuentan lo mismo (capado a su meta): si no cuadra, no fiarse
        if any(v != min(usados, meta) for meta, v in lecturas.items()):
            self.log(f"  Lectura dudosa del progreso ({lecturas}); no tiro dados normales.")
            return None
        self.log(f"  Dados normales usados esta semana: {usados} ({lecturas}).")
        return usados

    def recoger_metas(self) -> int:
        """Recoge las recompensas de "Usa N dados normales" ya completas."""
        img = self._abrir_protocolo_cosmo()
        if img is None:
            return 0
        n = 0
        for _ in range(6):
            rec = localizar_todos(img, "recoger_ev", 0.78)
            if not rec:
                break
            self.ctrl.tap(rec[0][1])
            n += 1
            time.sleep(1.8)
            i = self.cap("aviso")
            self.ctrl.tap((int(i.shape[1] * 0.30), int(i.shape[0] * 0.04)))
            time.sleep(1.2)
            img = self.cap("protocolo_cosmo")
        self._cerrar_todo()
        if n:
            self.log(f"  {n} recompensa(s) de dados normales recogida(s).")
        return n

    def disponibles(self, img):
        """Dados normales que quedan ("Disponible: N" encima de Inicio)."""
        p, c, _ = localizar(img, "inicio")
        if p < 0.75 or localizar(img, "free")[0] >= 0.75:
            return None
        k = img.shape[1] / 1600.0
        nums = leer_cifras(img, (c[0] + 5 * k, c[1] - 85 * k, c[0] + 115 * k, c[1] - 48 * k), s_max=90)
        return nums[-1] if nums else None

    PLAN_LOG = True            # observar y registrar el plan de multiplicadores (no gasta nada)

    def leer_nivel(self):
        """Abre el panel de Ascender, lo recorre entero y devuelve
        (mapa, completo, frames). No gasta nada. Cierra el panel al acabar."""
        if cm is None:
            return None
        img = self.cap("tablero")
        p, c, _ = localizar(img, "inicio")
        if p < 0.75:
            return None
        k = img.shape[1] / 1600.0
        self.ctrl.tap((int(c[0] - 335 * k), int(c[1] - 20 * k)))      # boton Ascender
        time.sleep(3.0)
        frames = [self.cap("panel")]
        if localizar(frames[0], "inicio")[0] >= 0.75 or not cm.filas_panel(frames[0]):
            self.log("  No reconozco el panel de Ascender; sigo sin leer el mapa.")
            return None
        nivel = self.nivel_actual(frames[0])
        if nivel is not None:
            if nivel != self.status.get("nivel"):
                self.log(f"  Nivel de Cosmomante: {nivel}.")
            self.status["nivel"] = nivel
        lento = getattr(self.ctrl, "drag_ms", None)
        if lento is not None:
            self.ctrl.drag_ms = 1100          # arrastre lento: sin inercia
        for _ in range(16):
            if self.parado():
                break
            self.ctrl.drag((int(650 * k), int(740 * k)), (int(650 * k), int(500 * k)))
            time.sleep(2.0)
            nuevo = self.cap("panel")
            if float(np.abs(nuevo[118:808].astype(np.int16) - frames[-1][118:808]).mean()) < 0.6:
                break                          # ya no se mueve: final de la lista
            frames.append(nuevo)
        if lento is not None:
            self.ctrl.drag_ms = lento
        self._tipos_mem = {}
        mapa, completo = cm.unir(frames, self._tipos_mem)
        desp = [cm.desplazamiento(x, y) for x, y in zip(frames, frames[1:], strict=False)]
        self.log(f"  Panel recorrido: {len(frames)} capturas, desplazamientos {desp}.")
        self._cerrar_panel(frames[-1])
        return mapa, completo, frames

    def observar_plan(self):
        """Lee el mapa del nivel y apunta en el registro que haria la estrategia
        (posicion = casilla recogida mas avanzada). No pulsa multiplicadores."""
        import json
        import os
        try:
            res = self.leer_nivel()
            if not res:
                return
            mapa, completo, _ = res
            recogidas = [i for i, (_, r) in mapa.items() if r]
            pos = max(recogidas) if recogidas else 0
            jugada = cm.plan(mapa, pos, 99, 99, 99)
            resumen = {c: sum(1 for v, _ in mapa.values() if v == c)
                       for c in ("nave", "octa", "x2", "iman_dorado", "iman_azul")}
            if not completo:       # guardar las capturas para poder afinar el recorrido
                for i, f in enumerate(res[2]):
                    self._registrar(f"panel{i}", f)
            self.log(f"  Mapa del nivel: {len(mapa)}/50 casillas ({'completo' if completo else 'incompleto'}), "
                     f"posicion ~{pos}, objetivos {resumen}; jugada sugerida: {jugada}.")
            base = os.path.join(os.path.dirname(carpeta_diag()), "cosmomante_log")
            os.makedirs(base, exist_ok=True)
            fila = {"hora": time.strftime("%Y%m%d_%H%M%S"), "etiqueta": "plan", "completo": completo,
                    "pos": pos, "jugada": jugada, "mapa": {str(i): [c, r] for i, (c, r) in sorted(mapa.items())}}
            with open(os.path.join(base, "cosmomante_log.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(fila) + "\n")
        except Exception as e:
            self.log(f"  No he podido leer el mapa del nivel: {e}")

    def _registrar(self, etiqueta, img=None):
        """Modo observacion: guarda la captura del tablero y una linea en
        cosmomante_log.jsonl (hora, etiqueta, dados disponibles). No pulsa
        nada. Sirve para estudiar donde cae la baliza y afinar la estrategia
        de multiplicadores con datos reales. Conserva las ultimas 60."""
        import json
        import os
        try:
            base = os.path.join(os.path.dirname(carpeta_diag()), "cosmomante_log")
            nombre = str(getattr(self.ctrl, "name", "inst")).replace(":", "_")
            os.makedirs(base, exist_ok=True)
            if img is None:
                img = self.cap("registro")
            marca = time.strftime("%Y%m%d_%H%M%S")
            fich = f"{nombre}_{marca}_{etiqueta}.png"
            cv2.imwrite(os.path.join(base, fich), img)
            fila = {"hora": marca, "cuenta": nombre, "etiqueta": etiqueta,
                    "disponibles": self.disponibles(img), "captura": fich}
            with open(os.path.join(base, "cosmomante_log.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(fila) + "\n")
            pngs = sorted(f for f in os.listdir(base) if f.endswith(".png"))
            for viejo in pngs[:-60]:
                os.remove(os.path.join(base, viejo))
        except Exception:
            pass

    def _tirar(self, c_ini, antes=None) -> bool:
        """Una tirada. Si se da "antes" (dados disponibles), espera a que el
        contador baje uno. Si el toque no entra (el tablero aun no estaba
        listo) y el contador sigue igual, vuelve a pulsar (hasta 3 veces);
        nunca pulsa otra vez si el contador ya ha cambiado."""
        time.sleep(1.2)                   # que acabe la animacion anterior
        self.ctrl.tap(c_ini)
        toques, ultimo = 1, time.time()
        fin = time.time() + 20.0
        while time.time() < fin and not self.parado():
            time.sleep(1.0)
            img = self.cap("tirada")
            if not self._en_tablero(img):
                # recompensa u otra ventanita encima: tocar arriba en el centro
                self.ctrl.tap((img.shape[1] // 2, int(img.shape[0] * 0.15)))
                ultimo = time.time()
                continue
            if antes is None:
                return True
            d = self.disponibles(img)
            if d is not None and d < antes:
                return d == antes - 1
            if d == antes and toques < 3 and time.time() - ultimo > 4.0:
                self.ctrl.tap(c_ini)      # el toque no entro: otra vez
                toques += 1
                ultimo = time.time()
        return antes is None

    def fuerza_pirata(self):
        """Progreso de "Destruye una fuerza de mas de N flotas piratas" en
        Mision de Cosmomante > Mision de actividad: [(hecho, meta), ...]."""
        if not self._abrir():
            return []
        img = self.cap("tablero")
        p, c, _ = localizar(img, "mision_cosmo")
        if p < 0.85:
            self.log("  No veo el boton Mision de Cosmomante.")
            self._cerrar_todo()
            return []
        self.ctrl.tap(c)
        time.sleep(2.5)
        img = self.cap("mision_cosmo")
        h, w = img.shape[:2]
        k = w / 1600.0
        res = []
        for _, (x, y) in localizar_todos(img, "flotas_piratas", 0.85):
            nums = leer_cifras(img, (1250 * k, y + 78 * k, 1560 * k, y + 112 * k))
            if len(nums) == 2 and nums[1] >= 100000:
                res.append((nums[0], nums[1]))
        self._cerrar_todo()
        return res

    # dados que dan las metas de "Usa N dados normales" (Mision de protocolo)
    DADOS_META = {30: 3, 50: 5}
    META = 100

    def _aprendido(self):
        import os
        ruta = os.path.join(os.path.dirname(carpeta_diag()), "cosmomante.json")
        return ruta, _cfg.leer(ruta)

    def _guardar_aprendido(self, d):
        ruta, _ = self._aprendido()
        _cfg.guardar(ruta, d)

    def _bonus(self, desde, cuentan=True, hasta=None):
        """Dados de recompensa de las metas entre 'desde' y 'hasta' (100)."""
        if not cuentan:
            return 0
        hasta = self.META if hasta is None else hasta
        return sum(v for m, v in self.DADOS_META.items() if desde < m <= hasta)

    def _tirar_hasta(self, objetivo, hechos_ref):
        """Tira dados normales hasta llevar 'objetivo' usados (cuenta en
        hechos_ref['usados']). Devuelve False si algo no cuadra."""
        while hechos_ref["usados"] < objetivo and not self.parado():
            d, p, c_ini = None, 0.0, None
            for _ in range(8):            # quitar recompensas que tapen el tablero
                img = self.cap("tablero")
                d = self.disponibles(img)
                p, c_ini, _ = localizar(img, "inicio")
                if d is not None and p >= 0.75:
                    break
                self.ctrl.tap((img.shape[1] // 2, int(img.shape[0] * 0.15)))
                time.sleep(1.5)
            if d is None or p < 0.75:
                self.log("  Pierdo el contador de dados; paro por seguridad.")
                return False
            if d == 0:
                self.log("  No quedan dados normales.")
                return False
            self._registrar("normal_antes", img)
            if not self._tirar(c_ini, antes=d):
                self.log("  El contador no ha bajado tras tirar; paro por seguridad.")
                return False
            self._registrar("normal_despues")
            hechos_ref["usados"] += 1
            hechos_ref["tiradas"] += 1
            self.status["estado"] = f"dados normales {hechos_ref['usados']}/{self.META}"
            # si se ha llenado la barra, hay que ascender antes de seguir
            if self.ASCENDER and self.puede_ascender(self.cap("tablero")):
                self.ascender()
        return True

    def normales_con_metas(self, usados):
        """Tira dados normales hasta la meta mas alta que sea alcanzable
        (100, 50 o 30), recogiendo las metas que se completen por el camino.
        Si no llega ni a 30, no gasta ninguno."""
        if usados >= self.META:
            self.log(f"  Meta de {self.META} dados ya cumplida esta semana.")
            return 0
        img = self.cap("tablero")
        disp = self.disponibles(img)
        if disp is None:
            self.log("  No leo los dados disponibles; no tiro dados normales.")
            return 0
        ruta, aprendido = self._aprendido()
        # los dados que dan las metas solo cuentan si ya se ha visto que suman
        # (si no, podria gastar dados y quedarse sin llegar)
        cuentan = aprendido.get("recompensa_suma", False) is True
        objetivo = None
        for meta in (30, 50, self.META):
            if meta <= usados:
                continue
            bonus = self._bonus(usados, cuentan, meta)
            if disp + bonus >= meta - usados:
                objetivo = meta
        if objetivo is None:
            self.log(f"  Tengo {disp} dados y no llegan ni a la meta de 30; "
                     "no tiro dados normales.")
            return 0
        bonus = self._bonus(usados, cuentan, objetivo)
        self.log(f"  Tengo {disp} dados (+{bonus} de recompensa) y voy a por "
                 f"{objetivo} usados.")
        ref = {"usados": usados, "tiradas": 0}
        for meta in sorted(m for m in list(self.DADOS_META) + [self.META]
                           if usados < m <= objetivo):
            if not self._tirar_hasta(meta, ref):
                break
            if meta == self.META or self.parado():
                continue
            # meta con dados de recompensa: recogerla y comprobar que suman
            antes = self.disponibles(self.cap("tablero")) or 0
            self._cerrar_todo()
            self.recoger_metas()
            if not self._abrir():
                self.log("  No puedo volver al tablero.")
                break
            despues = self.disponibles(self.cap("tablero"))
            if despues is None:
                break
            if despues < antes + self.DADOS_META[meta]:
                # los dados de recompensa no son dados normales: aprenderlo
                aprendido["recompensa_suma"] = False
                cuentan = False
                self.log("  Los dados de recompensa no suman a los normales; lo apunto.")
            else:
                aprendido["recompensa_suma"] = True
                cuentan = True
                self.log("  Los dados de recompensa suman a los normales; lo apunto.")
            self._guardar_aprendido(aprendido)
            resto = objetivo - ref["usados"]
            if despues + self._bonus(ref["usados"], cuentan, objetivo) < resto:
                self.log(f"  Ya no llegan a {objetivo} ({despues} dados, faltan {resto}); "
                         "paro aqui.")
                break
        self.log(f"  {ref['tiradas']} dado(s) normal(es) tirado(s); llevo "
                 f"{ref['usados']} de {objetivo}.")
        return ref["tiradas"]

    def run(self, ciclos: int = 1):
        """Cosmomante: primero comprueba si los dados llegan al nivel 6.

        Si la probabilidad no llega al umbral, NO gasta ningun dado y los
        guarda para el proximo evento. Si llega, usa gratis, remotos/azules,
        imanes y despues los normales; asciende y reclama las metas.
        """
        self.log("Cosmomante: primero nivel 6; si no llega, guardo los dados.")
        self.status["estado"] = "abriendo Cosmomante"
        jugadas = gratis = tiradas = metas = 0
        usados = self.progreso_semana() if self.NORMALES else None
        if not self._abrir():
            self._cerrar_todo()
            self.status["estado"] = "terminado"
            return

        # 1) tiradas gratis: no gastan dados
        for _ in range(6):
            if self.parado():
                break
            img = self.cap("tablero")
            p_free = localizar(img, "free")[0]
            p_ini, c_ini, _ = localizar(img, "inicio")
            if p_free < 0.75 or p_ini < 0.75:
                break
            self.status["estado"] = "tiradas gratis"
            self._tirar(c_ini)
            gratis += 1
        if gratis:
            self._perder_pos()
        self.log(f"  {gratis} tirada(s) gratis." if gratis else "  No quedan tiradas gratis hoy.")
        self._quitar_avisos()
        if self.ASCENDER and self.puede_ascender(self.cap("tablero")):
            self.ascender()

        # 2) estado actual y decision estadistica
        estado = self.leer_estado_nivel()
        nivel = (estado or {}).get("nivel")
        if nivel is not None:
            self.status["nivel"] = nivel
        gastar = False
        if estado is None:
            self.log("  No puedo leer nivel/progreso; no gasto dados por seguridad.")
        elif nivel is not None and nivel >= self.NIVEL_MAX:
            self.log(f"  Nivel {nivel}: ya esta en {self.NIVEL_MAX}; no gasto dados.")
        else:
            img = self.cap("tablero")
            recursos = self.recursos(img)
            if recursos is not None and (not self.NORMALES or usados is None):
                recursos["normales"] = 0
            if recursos is not None and not self.MULTIPLICADORES:
                recursos["remoto"] = recursos["azul"] = 0
                recursos["dorado"] = 0
            prob = self.probabilidad_nivel6(estado, recursos)
            if prob is not None:
                self.log(f"  Estimacion: ~{getattr(self, '_est_necesarias', '?')} "
                         f"casillas; tengo {getattr(self, '_est_remotos', '?')} "
                         f"remotos/azules, {getattr(self, '_est_magnetos', '?')} imanes "
                         f"y {getattr(self, '_est_normales', '?')} normales.")
            if prob is None:
                self.log("  No puedo leer los dados disponibles; no gasto ninguno.")
            elif prob < self.UMBRAL_NIVEL:
                self.log(f"  Probabilidad de llegar a nivel {self.NIVEL_MAX} con estos "
                         f"dados: {prob:.0%}; no gasto ninguno (los guardo).")
            else:
                self.log(f"  Probabilidad de llegar a nivel {self.NIVEL_MAX}: {prob:.0%}; "
                         "uso los dados.")
                gastar = True
                self._remotos = recursos.get("remoto") or 0
                self._azules = recursos.get("azul") or 0
                self._magnetos = recursos.get("dorado") or 0
                self._x2 = recursos.get("x2") or 0
                self._sin_remoto = self._remotos <= 0
                self._sin_dados = False

        if gastar and self.MULTIPLICADORES and not self.parado():
            # 3) remotos/azules, nivel a nivel, ascendiendo al llenar la barra
            for ronda in range(self.NIVEL_MAX + 1):
                if self.parado():
                    break
                nivel = self.status.get("nivel")
                if nivel is not None and nivel >= self.NIVEL_MAX:
                    break
                self.status["estado"] = f"nivel {nivel if nivel is not None else '?'}"
                hechas = self.jugar(modo_nivel=True)
                jugadas += hechas
                img = self.cap("tablero")
                if self.ASCENDER and self.puede_ascender(img):
                    self.ascender()
                if hechas == 0 or self._sin_dados:
                    break

        if gastar and usados is not None and not self.parado():
            # 4) dados normales: sirven para el nivel y para las metas 50/100
            self.status["estado"] = "dados normales"
            tiradas = self.normales_con_metas(usados + gratis)
            if tiradas:
                self._perder_pos()
            if self.ASCENDER and self.puede_ascender(self.cap("tablero")):
                self.ascender()

        # si la baliza era desconocida, las tiradas normales dejan una casilla
        # nueva en "Recogido": con eso se deduce y se puede seguir con remotos
        if gastar and self._pos_pendiente and not self.parado():
            self._pos_pendiente = False
            jugadas += self.jugar(modo_nivel=True)

        # 5) ultimo ascenso si quedo iluminado
        if self.ASCENDER and not self.parado():
            nivel = self.status.get("nivel")
            if (nivel is None or nivel < self.NIVEL_MAX) and \
                    self.puede_ascender(self.cap("tablero")):
                self.ascender()

        # 6) metas de dados (30, 50 y 100) siempre que esten completas
        if not self.parado():
            self.status["estado"] = "reclamando metas de dados"
            self.log("  Reclamo las metas de dados completadas.")
            metas = self.recoger_metas()
        self._cerrar_todo()
        self.status["recogidas"] = self.status.get("recogidas", 0) + gratis + tiradas + jugadas + metas
        self.status["estado"] = "terminado"
        self.log(f"Cosmomante: {jugadas} jugada(s) con dado remoto, {gratis} gratis, "
                 f"{tiradas} normales, {metas} meta(s) reclamada(s), "
                 f"nivel {self.status.get('nivel') if self.status.get('nivel') is not None else '?'}.")
