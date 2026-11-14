"""Piratas de sigilo: buscarlos con el radar, comprobar el objetivo y atacar."""
from __future__ import annotations

import time

import cv2
import numpy as np

from vision.detectores import barras_de_flota, caja_boton_radar
from vision.plantillas import buscar_rotulo, localizar
from vision.experiencia import experiencia
from tareas.base import TareaBase
from tareas.piratas.defensa import _Defensa
from tareas.piratas.envio import _EnvioFlotas
from tareas.piratas.radar import _Radar


class PiratasSigilo(_Radar, _Defensa, _EnvioFlotas, TareaBase):
    ESPERAR_BUSQUEDAS = True     # sin limite: esperar a que se recarguen (la Rutina no)
    NOMBRE = "Piratas de sigilo"

    # Posiciones medidas sobre capturas reales, en proporcion de la pantalla
    P_BUSCAR_PIRATA = (0.387, 0.947)   # boton de abajo al centro
    P_CENTRO = (0.500, 0.500)          # tras "Ir a", el pirata queda aqui
    P_ATACAR = (0.713, 0.287)          # opcion Atacar del menu radial

    UMBRAL_SIGILO = 0.78    # "Sigilo pirata": 0.87 por ADB, como mucho 0.49 en lo demas (jugadores incluidos)
    # si el centro no acierta (el pirata queda tapado), se prueban estos
    # desplazamientos alrededor, en proporcion de la pantalla
    ALREDEDORES = [(0.0, 0.0), (0.03, 0.0), (-0.03, 0.0), (0.0, 0.04),
                   (0.0, -0.04), (0.03, 0.04), (-0.03, -0.04)]

    UMBRAL_RADAR = 0.70     # titulo "Radar": 0.87-1.00 abierto, ~0.45 cerrado
    UMBRAL_ICONO = 0.65     # mira / Mas / entrada del menu
    UMBRAL_ATACAR = 0.70    # por ADB da 0.84; se exige ademas que este en su sitio
    DX_ATACAR, DY_ATACAR = 507, -157   # respecto a "Sigilo pirata", a escala 1
    UMBRAL_DIALOGO = 0.75   # Seleccionar todo / OK / Salto: 0.81-1.00 vs <=0.53
    # posiciones relativas al texto "Seleccionar todo", en pixeles a escala 1
    DX_CASILLA = -113       # su casilla, a la izquierda
    DY_CABECERAS = 56       # fila "Base"/"Inactivo"/"Moviendose" de las tarjetas
    MAX_REINTENTOS = 3      # intentos seguidos sin atacar antes de parar
    ANCHO_FUERZA_MIN = 130  # largo minimo del numero de Fuerza (1.000 millones)
    ESPERA_INICIO_COMBATE = 300  # tope para que lleguen las flotas (viaje sin salto)
    ESPERA_MAX_COMBATE = 480     # tope total de viaje + combate
    DEFENSA = True               # retirar flotas si un jugador entra en combate
    ESPERA_TRAS_SALTO = 1   # segundos para que las flotas lleguen tras saltar
    DX_GRUPO, DY_GRUPO = 44, 94
    # huecos para saltar al lado del pirata (fraccion del ancho, del alto)
    HUECOS = [(0, 0.20), (0, -0.24), (-0.16, 0.08), (0, 0.32), (0.17, 0.20)]
    UMBRAL_MOVIMIENTO = 0.80  # 'Movimiento en grupo': 1.00 vs <=0.71 (y en otra fila)
    DY_TARJETAS = 66        # cabeceras Inactivo/Moviendose bajo "Elige tu flota"
    DY_CARA_TARJETA = 220   # donde se pulsa la tarjeta

    # ---------------------------------------------------------------- util --

    # ------------------------------------------------------------ defensa --
    # filas de la lista "Flota aliada" de la vista de batalla (ADB, 1600x900)
    FILAS_ALIADAS = (220, 304, 388, 472, 555, 639)

    # --------------------------------------------------------------- ciclo --
    def un_ciclo(self) -> str:
        """Un ciclo completo. Devuelve un codigo de resultado."""
        # 0) si el pirata ya esta seleccionado en pantalla (por ejemplo de un
        #    intento anterior), atacarlo directamente sin gastar busqueda
        img = self.cap("inicio")
        p0, c0, e0 = localizar(img, "sigilo")
        if (p0 >= self.UMBRAL_SIGILO
                and self.ancho_fuerza(img, c0, e0) >= self.ANCHO_FUERZA_MIN):
            self.log("  El pirata ya esta seleccionado; voy directo a atacarlo.")
            self.status["encontrados"] += 1
            return self._rematar(img, c0, e0)

        # 0) si sigue un combate de antes, esperar a que termine
        if self.en_combate(self.ctrl.capture()):
            self.log("  Hay un combate en marcha; espero a que termine.")
            self.esperar_fin_combate()
        # 1) abrir el radar (y comprobar que de verdad esta abierto)
        self.status["estado"] = "abriendo radar"
        if not self.abrir_radar():
            return "parado" if self.parado() else "sin_radar"
        img = self.esperar(lambda i: caja_boton_radar(i) is not None, 5.0,
                           etiqueta="radar")
        if img is None:
            self.log("  Radar abierto, pero no encuentro el boton Buscar.")
            return "sin_radar"

        # 2-5) El radar puede abrirse en dos estados: listo para "Buscar", o
        #      con una busqueda anterior ya hecha y el boton en "Ir a". En vez
        #      de adivinar cual es, se pulsa y se OBSERVA lo que pasa:
        #        - el radar se cierra        -> era "Ir a": ya estamos en el mapa
        #        - el boton desaparece       -> esta buscando; cuando vuelva
        #                                       sera "Ir a" y se pulsa
        #        - no cambia nada en 8 s     -> no quedan busquedas
        self.status["estado"] = "buscando"
        caja = caja_boton_radar(img)
        # si el boton ya dice "Ir a", es un pirata buscado antes: al ir otra
        # vez, la camara lo deja arriba en vez de en el centro
        self.pirata_arriba = self.texto_boton_radar(img, caja) == "ir_a"
        if self.pirata_arriba:
            self.log("  El radar ya tenia un pirata localizado: voy a por el.")
        self.ctrl.tap((caja[0] + caja[2] // 2, caja[1] + caja[3] // 2))
        t_tap, fase, pulsaciones_ir_a = time.time(), "inicial", 0
        fin = time.time() + 35.0
        en_mapa = False
        while time.time() < fin and not self.parado():
            time.sleep(0.5)
            img = self.cap("radar_obs")
            if not self.radar_abierto(img):
                en_mapa = True
                break
            c = caja_boton_radar(img)
            if fase == "ir_a_pulsado":
                # "Ir a" se pulsa UNA sola vez: una segunda pulsacion mueve la
                # camara y el pirata queda arriba en vez de en el centro.
                # Aqui solo se espera a que el radar se cierre.
                continue
            if c is None:
                fase = "buscando"
            elif fase == "buscando":
                self.pirata_arriba = False   # busqueda nueva: queda en el centro
                self.status["estado"] = "yendo al pirata"
                self.ctrl.tap((c[0] + c[2] // 2, c[1] + c[3] // 2))
                pulsaciones_ir_a += 1
                fase = "ir_a_pulsado"
                fin = max(fin, time.time() + 15.0)
            elif fase == "inicial" and time.time() - t_tap > 8.0:
                self.log("  El radar no reacciona; puede que no queden busquedas.")
                self.atras(img)
                return "sin_busquedas"
        if self.parado():
            return "parado"
        if not en_mapa:
            self.log("  La busqueda no ha llevado al mapa a tiempo.")
            self.atras(img)
            return "sin_ir_a"
        self.status["estado"] = "yendo al pirata"
        time.sleep(0.5)
        self.esperar_quieto(3.0, "carga_mapa")

        # 6) Buscar el pirata y confirmarlo por su cartel.
        self.status["estado"] = "buscando el objetivo"
        res = self._buscar_pirata()
        if res == "parado":
            return "parado"
        if res is None:
            self.log("  No he reconocido el objetivo en ningun punto. Lo dejo.")
            return "no_identificado"
        img, c_sig, e_sig = res
        self.status["encontrados"] += 1
        return self._rematar(img, c_sig, e_sig)

    def _buscar_pirata(self, etiqueta=""):
        """Con el mapa en la vista del pirata (tras "Ir a"), lo selecciona y
        lo confirma por su cartel "Sigilo pirata". Candidatos: el centro
        (tras "Ir a" suele quedar ahi) y luego debajo de cada barra
        cian/naranja de flota, de la mas cercana al centro a la mas lejana.
        Dos pasadas por si el mapa aun no habia cargado.
        Devuelve (img, centro del cartel, escala), None o "parado"."""
        n = 0
        propias = []          # sitios donde un toque abrio una flota nuestra
        for pasada in (1, 2):
            if pasada == 2:
                self.log("  No lo veo aun; espero a que cargue el mapa y repito.")
                time.sleep(2.0)
                self.esperar_quieto(4.0, etiqueta + "carga_mapa2")
            for punto in self._candidatos(self.cap(etiqueta + "mapa")):
                if self.parado():
                    return "parado"
                if any(abs(punto[0] - q[0]) < 70 and abs(punto[1] - q[1]) < 70 for q in propias):
                    continue
                n += 1
                self.ctrl.tap(punto)
                # en cuanto sale el cartel o un menu se sigue (antes: 1,4 s fijos)
                time.sleep(0.3)
                img = self.esperar(self._toque_resuelto, 1.1, 0.2,
                                   etiqueta + "objetivo")
                if img is None:
                    img = self.cap(etiqueta + "objetivo")
                else:
                    time.sleep(0.15)             # que acabe de dibujarse
                    img = self.cap(etiqueta + "objetivo")
                parecido, c_sig, e_sig = localizar(img, "sigilo")
                if parecido >= self.UMBRAL_SIGILO:
                    largo = self.ancho_fuerza(img, c_sig, e_sig)
                    if largo >= self.ANCHO_FUERZA_MIN:
                        self.log(f"  Sigilo pirata confirmado ({parecido:.2f}, "
                                 f"fuerza de 1.000 millones o mas, intento {n}).")
                        ref, modo = getattr(self, "_ref_candidatos", ((0, 0), ""))
                        if modo:
                            h_, w_ = img.shape[:2]
                            exp = experiencia()
                            exp.pirata_encontrado(modo, (punto[0] - ref[0]) / w_,
                                                  (punto[1] - ref[1]) / h_)
                            exp.contar("sigilo_primer_toque", n == 1)
                            exp.guardar()
                        return img, c_sig, e_sig
                    self.log(f"  No es el sigiloso: su fuerza es menor de "
                             f"1.000 millones ({largo:.0f}). Sigo buscando.")
                # No era. Si el toque abrio el menu de OTRA cosa, cerrarlo; si
                # no abrio nada, no tocar: "Atras" sin menu abierto saca de la
                # vista del pirata y quita el zoom del mapa. Si abrio la vista
                # de una batalla en curso, salir de ella.
                if localizar(img, "llamar")[0] >= 0.80:
                    # menu de una flota propia (Llamar / Atacar flota / Ver):
                    # no tocar mas por esa zona
                    propias.append(punto)
                    self.cerrar_menu(img)
                    time.sleep(0.6)
                    continue
                if (self.en_vista_batalla(img) and not self.menu_abierto(img)
                        and self._batalla_confirmada()):
                    img = self.cap(etiqueta + "objetivo")
                    self.vigilar_defensa(img)
                    self.log("  He abierto una batalla en curso; salgo.")
                    self.atras(img)
                    time.sleep(1.5)
                else:
                    self.cerrar_menu(img)
        return None

    def _batalla_confirmada(self) -> bool:
        """Vista de batalla en dos capturas seguidas (una sola puede ser dudosa)."""
        time.sleep(0.3)
        return self.en_vista_batalla(self.cap("batalla_confirma"))

    def _toque_resuelto(self, img) -> bool:
        """Tras tocar el mapa: ya salio algo reconocible (cartel del sigiloso,
        un menu o una batalla), asi que no hace falta esperar mas."""
        ps, c, e = localizar(img, "sigilo")
        if ps >= self.UMBRAL_SIGILO:
            return self.ancho_fuerza(img, c, e) >= self.ANCHO_FUERZA_MIN
        return self.menu_abierto(img)

    def _rematar(self, img, c_sig=None, e_sig=1.0) -> str:
        if not self.atacar:
            self.log("  Modo prueba: no ataco.")
            self.atras(img)
            return "encontrado"
        # Atacar compromete las flotas: se exige reconocer el boton Y que este
        # donde le toca respecto al rotulo "Sigilo pirata". Medido igual en la
        # grabacion de la ventana y por ADB: +507, -157 a escala 1.
        parecido, donde = buscar_rotulo(img, "atacar")
        if c_sig is not None:
            esperado = (c_sig[0] + self.DX_ATACAR * e_sig,
                        c_sig[1] + self.DY_ATACAR * e_sig)
            en_su_sitio = (abs(donde[0] - esperado[0]) < 70 * e_sig
                           and abs(donde[1] - esperado[1]) < 50 * e_sig)
        else:
            en_su_sitio = parecido >= 0.90
        if parecido < self.UMBRAL_ATACAR or not en_su_sitio:
            self.log(f"  No veo el boton Atacar en su sitio ({parecido:.2f}); "
                     "no ataco.")
            self.atras(img)
            return "sin_boton_atacar"
        self.status["estado"] = "atacando"
        cg = self._boton_grupo(img, donde)
        if cg is None:
            pg = localizar(img, "grupo")[0]
            self.log(f"  No veo 'Ataque de grupo' en su sitio ({pg:.2f}); "
                     "no ataco.")
            self.atras(img)
            return "sin_boton_atacar"

        if not self.usar_salto:
            if not self._pulsar_ataque_grupo():
                return "objetivo_no_seguro"
            return self._dialogo_flotas("ok", comprobar_libres=True)

        # Con salto: al pirata no se puede saltar. Se salta a un hueco
        # vacio a su lado (Movimiento en grupo > Seleccionar todo > Salto de
        # flota) y despues se vuelve a pulsar el pirata y se ataca en grupo
        # con OK: como las flotas ya estan al lado, llegan enseguida.
        h, w = img.shape[:2]
        centro = (w // 2, h // 2)       # al seleccionar algo, el juego lo centra
        saltado, desplaz = self._saltar_al_lado(img, donde, cg, e_sig)
        if not saltado:
            self.log("  No he podido saltar al lado; ataco en grupo sin salto.")
        # volver a seleccionar el pirata: tras moverse la camara al hueco, el
        # pirata queda desplazado lo contrario que el hueco
        pistas = [centro]
        if desplaz is not None:
            pistas.insert(0, (int(centro[0] - desplaz[0]), int(centro[1] - desplaz[1])))
        res = self._volver_al_pirata(pistas)
        if res is None:
            self.log("  No consigo volver a seleccionar el pirata.")
            return "sin_boton_atacar"
        if not self._pulsar_ataque_grupo():
            return "objetivo_no_seguro"
        return self._dialogo_flotas("ok", comprobar_libres=False,
                                    como="salto + ataque de grupo")

    def _objetivo_seguro(self, img):
        """REGLA PRINCIPAL: nunca atacar flotas ni bases de jugadores.
        Solo se ataca si, en la MISMA captura, se cumplen todas:
          - el cartel "Sigilo pirata" (0.87; jugadores y todo lo demas <=0.49)
          - su Fuerza es de 1.000 millones o mas
          - el menu es el del pirata: "Atacar" y "Ataque de grupo" justo en
            su sitio respecto al cartel. Los menus de jugadores son otros
            ("Atacar flota", "Defender", "Llamar", "Ver") y no encajan.
        Devuelve (centro de 'Ataque de grupo', '') o (None, motivo)."""
        ps, c_sig, e_sig = localizar(img, "sigilo")
        if ps < self.UMBRAL_SIGILO:
            return None, f"no es un Sigilo pirata ({ps:.2f})"
        if self.ancho_fuerza(img, c_sig, e_sig) < self.ANCHO_FUERZA_MIN:
            return None, "su fuerza es menor de 1.000 millones"
        pa, donde = buscar_rotulo(img, "atacar")
        esperado = (c_sig[0] + self.DX_ATACAR * e_sig, c_sig[1] + self.DY_ATACAR * e_sig)
        if not (pa >= self.UMBRAL_ATACAR and abs(donde[0] - esperado[0]) < 70 * e_sig
                and abs(donde[1] - esperado[1]) < 50 * e_sig):
            return None, "el menu no es el de un pirata"
        cg = self._boton_grupo(img, donde)
        if cg is None:
            return None, "no veo 'Ataque de grupo' en su sitio"
        return cg, ""

    @staticmethod
    def _estorbos(img):
        """Cosas del mapa que no hay que pulsar al buscar un hueco: el pirata
        (barra cian/naranja) y nuestras flotas (barra verde y aro verde).
        Devuelve (x, y, radio a evitar)."""
        h, w = img.shape[:2]
        res = [(bx, by + bw, 1.6 * bw + 40) for bx, by, bw in barras_de_flota(img)]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        t = hsv[:, :, 0].astype(np.float32) * 2.0
        verde = ((t > 90) & (t < 150) & (hsv[:, :, 1] > 120)
                 & (hsv[:, :, 2] > 120)).astype(np.uint8)
        n, _, st, cen = cv2.connectedComponentsWithStats(verde)
        for i in range(1, n):
            x, y, bw, bh, area = st[i]
            if area < 25 or not (0.10 * w < cen[i][0] < 0.82 * w):
                continue
            if bw >= 30 and bh <= 10:            # barra de vida de una flota nuestra
                res.append((int(cen[i][0]), int(cen[i][1] + 60), 150))
            elif bw >= 8 and bh >= 5:            # aro verde bajo una flota nuestra
                res.append((int(cen[i][0]), int(cen[i][1]), 130))
        return res

    def _volver_al_pirata(self, pistas=None):
        """Tras el salto el juego vuelve a la vista general del mapa. Para
        volver al pirata sin gastar otra busqueda se abre el radar, que sigue
        mostrando "Ir a" con el mismo pirata, y se pulsa UNA vez.
        Antes espera a que las flotas acaben de saltar: mientras pasan por
        encima del pirata, los toques caen en ellas y no en el."""
        # primero que se vea el movimiento (max 3 s), luego dos lecturas
        # seguidas sin el: asi no se confunde "aun no ha empezado" con "ya llego"
        self.esperar(lambda i: localizar(i, "flota_mov")[0] >= 0.70, 3.0,
                     intervalo=0.2, etiqueta="salto_saliendo")
        quietas, fin = 0, time.time() + 25.0
        while quietas < 2 and time.time() < fin and not self.parado():
            img = self.cap("salto_llegando")
            quietas = quietas + 1 if localizar(img, "flota_mov")[0] < 0.70 else 0
            if quietas < 2:
                time.sleep(0.5)
        if quietas < 2:
            self.log("  Las flotas siguen en movimiento; sigo igualmente.")
        if not self.abrir_radar():
            return None
        img = self.esperar(lambda i: caja_boton_radar(i) is not None, 5.0,
                           etiqueta="re_radar")
        if img is None:
            self.atras()
            return None
        caja = caja_boton_radar(img)
        if self.texto_boton_radar(img, caja) != "ir_a":
            self.log("  El radar ya no muestra 'Ir a' (no gasto otra busqueda).")
            self.atras(img)
            return None
        self.pirata_arriba = True        # "Ir a" repetido: el pirata queda arriba
        self.ctrl.tap((caja[0] + caja[2] // 2, caja[1] + caja[3] // 2))
        if self.esperar(lambda i: not self.radar_abierto(i), 12.0,
                        etiqueta="re_ir_a") is None:
            self.atras()
            return None
        time.sleep(0.5)
        self.esperar_quieto(3.0, "re_carga")
        res = self._buscar_pirata("re_")
        if res is None or res == "parado":
            return None
        img, c_sig, e_sig = res
        pa, donde = buscar_rotulo(img, "atacar")
        esperado = (c_sig[0] + self.DX_ATACAR * e_sig, c_sig[1] + self.DY_ATACAR * e_sig)
        if (pa >= self.UMBRAL_ATACAR and abs(donde[0] - esperado[0]) < 70 * e_sig
                and abs(donde[1] - esperado[1]) < 50 * e_sig):
            self.log("  Pirata seleccionado otra vez.")
            return img, c_sig, e_sig, donde
        return None

    # ---------------------------------------------------------------- run ---
    def run(self, ciclos: int = 1):
        self.status.update({"ciclos": ciclos, "ciclo": 0})
        # La Rutina reutiliza el status acumulado: para el resumen de ESTA
        # pasada se restan los contadores con los que se empieza.
        enc0 = self.status.get("encontrados", 0)
        atac0 = self.status.get("atacados", 0)
        modo = (("atacando con SALTO DE FLOTA" if self.usar_salto
                 else "atacando con OK (sin salto)") if self.atacar
                else "en prueba (no ataca)")
        self.log(f"Piratas de sigilo, {modo}. Ciclos: "
                 f"{'sin limite' if ciclos == 0 else ciclos}.")
        # Un ciclo solo cuenta si ha atacado al pirata (o, en modo prueba, si
        # lo ha reconocido). Si falla, se repite el MISMO ciclo: el radar
        # sigue con "Ir a" hacia el mismo pirata, asi que no se gasta otra
        # busqueda. Tras varios fallos seguidos se para para no atascarse.
        exito = "atacado" if self.atacar else "encontrado"
        hechos, fallos, intento = 0, 0, 0
        while (ciclos == 0 or hechos < ciclos) and not self.parado():
            intento += 1
            self.status["ciclo"] = hechos + 1
            self.log(f"--- Ciclo {hechos + 1}"
                     f"{'' if ciclos == 0 else f' de {ciclos}'}"
                     f"{'' if fallos == 0 else f' (reintento {fallos})'} ---")
            r = self.un_ciclo()
            if self.parado():
                r = "parado"
            if r == "sin_busquedas" and ciclos == 0 and self.ESPERAR_BUSQUEDAS:
                # sin limite: las busquedas se recargan (1 por hora). Cerrar el
                # radar, esperar y seguir solo.
                img = self.cap("sin_busquedas")
                if self.radar_abierto(img):
                    self.atras(img)
                self.log("No quedan busquedas: espero 1 hora a que se recargue una y sigo.")
                fin = time.time() + 3600
                while time.time() < fin and not self.parado():
                    self.status["estado"] = f"sin busquedas, sigo en {int((fin - time.time()) // 60) + 1} min"
                    time.sleep(5)
                fallos = 0
                continue
            if r in ("sin_busquedas", "sin_radar"):
                self.log({"sin_busquedas": "No quedan busquedas disponibles.",
                          "sin_radar": "No he podido abrir el radar. "
                                       "Deja el juego en la vista de la base."}[r])
                self.status["estado"] = r
                break
            if r == "parado":
                break
            if r == exito:
                hechos += 1
                fallos = 0
                if r == "atacado":
                    # no buscar otro hasta que este este destruido
                    self.esperar_fin_combate()
            else:
                fallos += 1
                if fallos >= self.MAX_REINTENTOS:
                    self.log(f"{fallos} intentos seguidos sin atacar al pirata; "
                             "paro. Revisa %LOCALAPPDATA%\\NovaBot\\diag.")
                    self.status["estado"] = r
                    break
                self.log(f"  No ha atacado ({r}); repito el ciclo {hechos + 1}.")
                time.sleep(1.0)
                continue
            time.sleep(0.5)
        if self.status["estado"] not in ("sin_busquedas", "sin_radar") \
                and not (fallos >= self.MAX_REINTENTOS):
            self.status["estado"] = "parado" if self.parado() else "terminado"
        self.log(f"Hecho. {hechos} ciclo(s) completos ({intento} intentos): "
                 f"{self.status['encontrados'] - enc0} reconocidos, "
                 f"{self.status['atacados'] - atac0} atacados.")
