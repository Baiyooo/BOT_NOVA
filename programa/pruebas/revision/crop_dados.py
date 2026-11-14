import cv2
img = cv2.imread(__import__("os").path.expandvars(r"%LOCALAPPDATA%\NovaBot\cosmomante_log\127.0.0.1_5565_20261031_002451_baliza_desconocida.png"))
crop = img[790:880, 0:520]
crop = cv2.resize(crop, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_NEAREST)
cv2.imwrite(__import__("os").path.expanduser(r"~\Documents\NovaBot\_revision\crop_dados.png"), crop)
print(crop.shape)
