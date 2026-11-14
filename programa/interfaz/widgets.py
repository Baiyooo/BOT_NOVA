"""Piezas pequenas de la ventana: zona desplazable, barra, ayuda emergente, boton plano."""
from __future__ import annotations

import tkinter as tk

from interfaz.tema import (ANCHO_LATERAL, BORDE, CLARO, ESP_L, ESP_M, ESP_XS, FONDO, FONDO_AYUDA, LATERAL,
                           PANEL2, SUAVE, TAM_M, TAM_S, TEAL, TEXTO, VERDE, fuente, titular)


#  ---- rueda del raton: un solo reparto para toda la aplicacion ----------
#  Cada zona desplazable se apunta aqui. La rueda mueve la zona que esta
#  debajo del raton (no la que tiene el foco, ni la de otra ventana), y los
#  cuadros de texto (registro) se bajan solos.
_ZONAS: dict = {}            # nombre del lienzo -> funcion que lo desplaza
_RUEDA_PUESTA = set()        # raices (Tk) que ya tienen el reparto


def registrar_rueda(lienzo, desplazar):
    """desplazar(pasos) se llama al girar la rueda encima del lienzo."""
    _ZONAS[str(lienzo)] = desplazar
    lienzo.bind("<Destroy>", lambda e: _ZONAS.pop(str(lienzo), None)
                if str(e.widget) == str(lienzo) else None, add="+")
    try:
        raiz = lienzo._root()
    except AttributeError:
        return
    if raiz is None:                   # lienzo de prueba sin raiz real
        return
    if str(raiz) + str(id(raiz)) not in _RUEDA_PUESTA:
        _RUEDA_PUESTA.add(str(raiz) + str(id(raiz)))
        raiz.bind_all("<MouseWheel>", _rueda, add="+")


def _rueda(e):
    try:
        w = e.widget.winfo_containing(e.x_root, e.y_root)
    except (tk.TclError, AttributeError, KeyError):
        return
    while w is not None:
        if isinstance(w, (tk.Text, tk.Listbox)):
            return                                    # se bajan solos
        f = _ZONAS.get(str(w))
        if f is not None:
            f(-e.delta / 120)
            return
        w = w.master


class BarraDesp(tk.Canvas):
    """Barra de desplazamiento fina con los colores del tema (la de Windows
    no se deja pintar). Se esconde cuando todo cabe."""

    ANCHO = 8

    def __init__(self, master, fondo, comando):
        super().__init__(master, width=self.ANCHO + 4, bg=fondo, highlightthickness=0, bd=0)
        self.comando = comando
        self.ini, self.fin = 0.0, 1.0
        self._agarre = None
        self._encima = False
        self.bind("<Configure>", lambda e: self._pintar())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", self._pulsar)
        self.bind("<B1-Motion>", self._arrastrar)
        self.bind("<ButtonRelease-1>", lambda e: self._soltar())

    def set(self, ini, fin):                           # yscrollcommand
        self.ini, self.fin = float(ini), float(fin)
        self._pintar()

    def _hover(self, si):
        self._encima = si
        self._pintar()

    def _soltar(self):
        self._agarre = None
        self._pintar()

    def _pintar(self):
        self.delete("all")
        if self.ini <= 0 and self.fin >= 1:
            return                                       # todo cabe: sin barra
        h = self.winfo_height()
        y0 = max(0, int(h * self.ini))
        y1 = min(h, max(y0 + 24, int(h * self.fin)))
        activo = self._encima or self._agarre is not None
        x0 = 2 if activo else 3
        x1 = self.ANCHO + 2 if activo else self.ANCHO + 1
        color = TEAL if activo else BORDE
        r = (x1 - x0) // 2
        self.create_rectangle(x0, y0 + r, x1, y1 - r, fill=color, outline="")
        self.create_oval(x0, y0, x1, y0 + 2 * r, fill=color, outline="")
        self.create_oval(x0, y1 - 2 * r, x1, y1, fill=color, outline="")

    def _pulsar(self, e):
        h = max(1, self.winfo_height())
        if self.ini * h <= e.y <= self.fin * h:
            self._agarre = (e.y, self.ini)                # arrastrar la barra
        else:
            self.comando("scroll", -1 if e.y < self.ini * h else 1, "pages")
        self._pintar()

    def _arrastrar(self, e):
        if self._agarre is None:
            return
        y, ini = self._agarre
        self.comando("moveto", ini + (e.y - y) / max(1, self.winfo_height()))


class Desplazable(tk.Frame):
    """Zona que se puede bajar con la rueda del raton y con su barra. Lo que
    se monta dentro va en self.dentro. El registro (Text) se baja solo."""

    PASO = 22            # pixeles por paso
    PASOS_RUEDA = 3      # pasos por golpe de rueda

    def __init__(self, master, fondo, texto=None):
        super().__init__(master, bg=fondo)
        self.texto = texto
        self.lienzo = tk.Canvas(self, bg=fondo, bd=0, highlightthickness=0,
                                yscrollincrement=self.PASO)
        self.barra = BarraDesp(self, fondo, self.lienzo.yview)
        self.lienzo.configure(yscrollcommand=self.barra.set)
        self.barra.pack(side="right", fill="y")
        self.lienzo.pack(side="left", fill="both", expand=True)
        self.dentro = tk.Frame(self.lienzo, bg=fondo)
        self.ventana = self.lienzo.create_window((0, 0), window=self.dentro, anchor="nw")
        self.dentro.bind("<Configure>", self._ajustar)
        self.lienzo.bind("<Configure>", self._ajustar)
        self._resto = 0.0
        registrar_rueda(self.lienzo, self._rueda)
        self._alto_visto = None
        self.after(300, self._vigilar_alto)

    def _vigilar_alto(self):
        """Lo de dentro tiene su alto fijado por el lienzo, asi que si crece o
        encoge (plegar un evento) no avisa: se mira cada poco."""
        try:
            alto = self.dentro.winfo_reqheight()
            if alto != self._alto_visto:
                self._alto_visto = alto
                self._ajustar()
            self.after(300, self._vigilar_alto)
        except tk.TclError:
            pass

    def _ajustar(self, _e=None):
        vista = self.lienzo.winfo_height()
        alto = max(vista, self.dentro.winfo_reqheight())
        self.lienzo.itemconfigure(self.ventana, width=self.lienzo.winfo_width(), height=alto)
        self.lienzo.configure(scrollregion=(0, 0, self.lienzo.winfo_width(), alto))
        # si lo de dentro ha encogido (un evento plegado), no dejar hueco abajo
        arriba = self.lienzo.canvasy(0)
        if arriba + vista > alto:
            self.lienzo.yview_moveto(max(0.0, (alto - vista) / alto) if alto else 0.0)

    def _rueda(self, golpes):
        if self.dentro.winfo_reqheight() <= self.lienzo.winfo_height():
            return
        # los touchpads mandan medios golpes: se acumulan
        self._resto += golpes * self.PASOS_RUEDA
        pasos = int(self._resto + (1e-6 if self._resto > 0 else -1e-6))
        self._resto -= pasos
        if pasos:
            self.lienzo.yview_scroll(pasos, "units")       # golpes > 0 = hacia abajo


class Pestanas(tk.Frame):
    """Barra lateral con una pestana por pagina (icono + texto). Cada pagina
    es un Frame; solo se ve la elegida. Las paginas se crean con anadir()."""

    def __init__(self, master, al_cambiar=None):
        super().__init__(master, bg=FONDO)
        self.lateral = tk.Frame(self, bg=LATERAL, width=ANCHO_LATERAL)
        self.lateral.pack(side="left", fill="y")
        self.lateral.pack_propagate(False)
        self.pie = tk.Frame(self.lateral, bg=LATERAL)          # hueco bajo las pestanas
        self.pie.pack(side="bottom", fill="x", padx=ESP_M, pady=ESP_M)
        self.sitio = tk.Frame(self, bg=FONDO)
        self.sitio.pack(side="left", fill="both", expand=True)
        self.paginas: dict[str, tk.Frame] = {}
        self.botones: dict[str, tk.Button] = {}
        self.titulos: dict[str, tuple[str, str]] = {}
        self.actual = ""
        self.al_cambiar = al_cambiar

    def anadir(self, clave: str, icono: str, titulo: str) -> tk.Frame:
        pagina = tk.Frame(self.sitio, bg=FONDO)
        b = tk.Button(self.lateral, text=f" {icono}  {titulo}", anchor="w", bd=0, relief="flat",
                      cursor="hand2", bg=LATERAL, fg=SUAVE, activebackground=PANEL2,
                      activeforeground=TEXTO, font=fuente(TAM_M, True), padx=ESP_L, pady=ESP_M,
                      command=lambda: self.mostrar(clave))
        b.pack(fill="x", pady=(ESP_XS, 0))
        self.paginas[clave], self.botones[clave], self.titulos[clave] = pagina, b, (icono, titulo)
        if not self.actual:
            self.mostrar(clave)
        return pagina

    def mostrar(self, clave: str):
        if clave not in self.paginas:
            return
        for k, p in self.paginas.items():
            if k == clave:
                p.pack(fill="both", expand=True)
            else:
                p.pack_forget()
            self.botones[k].config(bg=PANEL2 if k == clave else LATERAL,
                                   fg=TEAL if k == clave else SUAVE)
        self.actual = clave
        if self.al_cambiar:
            self.al_cambiar(clave)

    def etiqueta(self, clave: str, sufijo: str = ""):
        """Anade un texto corto al nombre de una pestana (p.ej. un numero)."""
        if clave in self.botones:
            icono, titulo = self.titulos[clave]
            self.botones[clave].config(text=f" {icono}  {titulo}" + (f"  {sufijo}" if sufijo else ""))


class Barra(tk.Canvas):
    """Barra de progreso dibujada a mano, para controlar el color."""

    def __init__(self, master, ancho=260, alto=8):
        super().__init__(master, width=ancho, height=alto, bg=PANEL2,
                         highlightthickness=0)
        self.ancho, self.alto = ancho, alto
        self.create_rectangle(0, 0, ancho, alto, fill=BORDE, outline="")
        self.relleno = self.create_rectangle(0, 0, 0, alto, fill=VERDE, outline="")

    def set(self, fraccion: float, color=VERDE):
        f = max(0.0, min(1.0, fraccion))
        self.coords(self.relleno, 0, 0, self.ancho * f, self.alto)
        self.itemconfig(self.relleno, fill=color)


class Ayuda:
    """Texto de ayuda al pasar el raton por encima."""

    def __init__(self, widget, texto):
        self.w, self.texto, self.tip = widget, texto, None
        widget.bind("<Enter>", self._ver, add="+")
        widget.bind("<Leave>", self._quitar, add="+")

    def _ver(self, _e=None):
        if self.tip or not self.texto:
            return
        x = self.w.winfo_rootx() + 10
        y = self.w.winfo_rooty() + self.w.winfo_height() + 4
        self.tip = tk.Toplevel(self.w)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.texto, bg=FONDO_AYUDA, fg=TEXTO, padx=8, pady=4,
                 font=fuente(TAM_S), justify="left", wraplength=320, highlightthickness=1,
                 highlightbackground=BORDE).pack()

    def _quitar(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def _plano(master, texto, cmd, bg=PANEL2, fg=TEXTO, negrita=False, **kw):
    """Boton plano con cambio de color al pasar el raton."""
    claro = CLARO.get(bg, bg)
    b_ = tk.Button(master, text=texto, command=cmd, bg=bg, fg=fg, activebackground=claro,
                   activeforeground=fg, bd=0, relief="flat", cursor="hand2",
                   font=titular(TAM_M) if negrita else fuente(TAM_M), **kw)
    b_.bind("<Enter>", lambda e: b_.cget("state") != "disabled" and b_.config(bg=claro))
    b_.bind("<Leave>", lambda e: b_.config(bg=b_._bg))
    b_._bg = bg

    def color(nuevo_bg, nuevo_fg=None):
        b_._bg = nuevo_bg
        b_.config(bg=nuevo_bg, activebackground=CLARO.get(nuevo_bg, nuevo_bg), fg=nuevo_fg or b_.cget("fg"),
                  activeforeground=nuevo_fg or b_.cget("fg"))
    b_.color = color
    return b_


def titulo_seccion(master, texto, bg, **pack):
    """Titulo de seccion: rombo cian y texto en mayusculas con letra de titulares."""
    lbl = tk.Label(master, text="◆  " + texto.upper(), bg=bg, fg=TEAL, font=titular(TAM_M))
    if pack is not None:
        lbl.pack(**pack)
    return lbl
