# NovaBot - guia para agentes

Bot en Python que automatiza tareas de Nova Empire en BlueStacks por ADB.
Todo local: sin nube ni IA externa. Python 3.12, tkinter, OpenCV 5, numpy 2.5.

## Mapa del codigo (todo bajo programa/)

- main.py        punto de entrada (ventana, menu texto, --activar-adb).
- nucleo/        lo que no sabe nada del juego: ADB, config, rutas, registro,
                 estadisticas, actualizador, empaquetador, diagnostico.
- vision/        ver la pantalla: plantillas PNG, mascaras de color, OCR
                 (rapidocr), lectura de cifras, pantallas conocidas.
- tareas/        actuar en el juego: una tarea por modulo o carpeta
                 (piratas/, ballenas/, cosmomante/, restos.py, roaming.py...).
- cerebro/       decidir: la Rutina, su planificador y lo que se sabe de los
                 eventos y sus misiones (textos_mision limpia el OCR crudo).
- interfaz/      mostrar: ventana y panel tkinter, menu de texto, tarjeta por
                 instancia, ajustes.
- recursos/      PNG de referencia que busca el bot en pantalla, e icono.
- pruebas/       regresion de vision y pruebas de humo.
- conocimiento/  lo aprendido que viaja con el programa: eventos.json,
                 experiencia.json y novabot_det.onnx (detector de objetos).

## Reglas que el codigo nunca se salta

- Nunca gasta GEC, no construye naves, no abre cajas ni acelera.
- El analisis de eventos es de solo lectura: no compra, no recoge, no ataca.
- Roaming Test: nunca el boton naranja con el tablero en pantalla (es
  "Restart") ni la X de arriba a la derecha; como mucho 3 Start por partida;
  si dos partidas seguidas se atascan, para y avisa.
- Los datos del usuario viven en %LOCALAPPDATA%\NovaBot: nunca se tocan al
  actualizar ni van en el paquete exportado.

## Probar antes de dar algo por hecho

Desde la carpeta programa/:

    python pruebas\regresion.py               # detectores de vision contra capturas reales
    python pruebas\pruebas_panel.py           # panel y ajustes sin abrir la ventana
    python pruebas\pruebas_ballenas_humo.py   # ballenas con un BlueStacks falso

regresion.py avisa si algun resultado ha cambiado. Tras tocar una plantilla o
un detector, pasala y acepta los resultados nuevos con --guardar solo si el
cambio era a proposito. Tarda unos 4 minutos.

## Calidad: ruff

Desde la carpeta programa/:

    ruff check .

La configuracion vive en pyproject.toml. Se ignoran a proposito las reglas
de estilo compacto del proyecto (punto y coma, if en una linea, imports
aplazados); las que importan son las de bugs (F, B, UP, SIM seleccionadas).

NUNCA ejecutes `ruff format`: reescribiria el estilo de 70 archivos. Solo
`ruff check`. Si un aviso es estilo y molesta, anade la regla a `ignore` en
pyproject.toml con un comentario del porque.

## Convenciones

- Toda mejora de una tarea suelta (ballenas, piratas, recogida...) se aplica
  tambien a la Rutina automatica, siempre que no corte su flujo: la Rutina y
  las tareas sueltas usan las mismas clases y los mismos ajustes, sin copias.

- Espanol en docstrings, comentarios y textos de la interfaz. LEEME.txt,
  los .bat y los mensajes de commit van SIN acentos.
- Commits de una linea con formato "Area: que cambio" (ver git log).
- Sin dependencias nuevas salvo necesidad real: el instalador automatico
  usa requirements.txt con versiones exactas probadas.
- version.py lleva la VERSION (mayor.menor); EMPAQUETAR.bat crea
  paquetes\NovaBot-<version>.zip. Subir version solo al empaquetar.
- Las capturas de diagnostico van a %LOCALAPPDATA%\NovaBot\diag (limite de
  200 por cuenta); el dataset de entrenamiento, a NovaBot\dataset.

## Glosario minimo del juego

- GEC: moneda premium. Jamas gastarla.
- Instancia: cada ventana de BlueStacks, una cuenta; el bot las maneja en paralelo.
- Ballenas, gemas y escombros: objetivos del mapa que se recogen con drones.
- Piratas de sigilo (radar) y piratas normales (sistema): los ataca con flotas.
- Destacamento: exploracion que se manda y se reclama.
- Cosmomante y Neural Roaming: minijuegos de eventos.
- Llamar flotas: traer de vuelta las flotas paradas.
