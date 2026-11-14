import cv2
import numpy as np

RUTA = __import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\captura_5585.png")
img = cv2.imread(RUTA)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
t = hsv[:, :, 0].astype(np.float32) * 2.0
# zonas alrededor de simbolos de pirata normales visibles
puntos = [(500, 320), (680, 505), (530, 540), (800, 560), (1080, 505), (1160, 555), (720, 520)]
for x, y in puntos:
    r = 18
    z = hsv[y - r:y + r, x - r:x + r].reshape(-1, 3)
    z = z[(z[:, 1] > 150) & (z[:, 2] > 150)]
    if len(z) == 0:
        print((x, y), "sin pixeles vivos")
        continue
    hues = (z[:, 0].astype(np.float32) * 2.0)
    print((x, y), "n", len(z), "hue min/med/max", round(hues.min(), 1),
          round(float(np.median(hues)), 1), round(hues.max(), 1),
          "sat", int(np.median(z[:, 1])), "val", int(np.median(z[:, 2])))

# mascara actual y ampliada, cuantos pixeles
for nombre, m in (
        ("actual 8-30", (t >= 8) & (t <= 30)),
        ("rojo <=35", (t <= 35)),
        ("rojo <=35 o >=340", (t <= 35) | (t >= 340)),
        ("rojo <=45 o >=330", (t <= 45) | (t >= 330))):
    mask = (m & (hsv[:, :, 1] > 170) & (hsv[:, :, 2] > 170))
    print(nombre, int(mask.sum()))
