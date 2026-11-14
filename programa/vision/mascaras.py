"""Mascaras de color (HSV) con las que se aislan los textos y botones del juego."""
from __future__ import annotations

import cv2
import numpy as np


def mascara_texto(bgr: np.ndarray) -> np.ndarray:
    """Turquesa con que el juego escribe el nombre del objetivo."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    tono = hsv[:, :, 0].astype(np.float32) * 2.0
    return (((tono > 175) & (tono < 235))
            & (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 100)).astype(np.uint8)


def mascara_blanco(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 2] > 175) & (hsv[:, :, 1] < 70)).astype(np.uint8)


def mascara_ambar(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    tono = hsv[:, :, 0].astype(np.float32) * 2.0
    return (((tono > 20) & (tono < 55))
            & (hsv[:, :, 1] > 90) & (hsv[:, :, 2] > 110)).astype(np.uint8)


def mascara_rojo(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    tono = hsv[:, :, 0].astype(np.float32) * 2.0
    return (((tono < 15) | (tono > 340))
            & (hsv[:, :, 1] > 90) & (hsv[:, :, 2] > 110)).astype(np.uint8)


def mascara_verde(bgr: np.ndarray) -> np.ndarray:
    """Texto verde de los botones "Recoger" de las misiones."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    tono = hsv[:, :, 0].astype(np.float32) * 2.0
    return (((tono > 70) & (tono < 160))
            & (hsv[:, :, 1] > 90) & (hsv[:, :, 2] > 120)).astype(np.uint8)


def mascara_gris(bgr: np.ndarray) -> np.ndarray:
    """Texto gris apagado ("Puntos actuales" de las barras de cajas)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 2] > 110) & (hsv[:, :, 1] < 60)).astype(np.uint8)


def mascara_ambar_claro(bgr: np.ndarray) -> np.ndarray:
    """Texto ambar muy claro sobre boton ambar (Roaming Test)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    tono = hsv[:, :, 0].astype(np.float32) * 2.0
    return (((tono > 25) & (tono < 55)) & (hsv[:, :, 2] > 195)).astype(np.uint8)


def mascara_claro(bgr: np.ndarray) -> np.ndarray:
    """Iconos y textos blancos o gris claro."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 90)).astype(np.uint8)
