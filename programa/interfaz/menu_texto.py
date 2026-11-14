"""Menu en modo texto (BOT.bat texto) y linea de comandos del Roaming Test.
Hace lo mismo que la ventana, con el mismo motor.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time

import cv2

from nucleo.adb import AdbController, activar_adb, buscar_adb, leer_instancias
from tareas.roaming import Bot, SYMBOLS, board_str, detect_grid, read_board, unknown_count


def menu_texto() -> None:
    """Menu en modo texto. Las instancias salen de bluestacks.conf, asi que
    se adapta solo al BlueStacks de cada ordenador."""
    adb = buscar_adb()
    while True:
        inst = leer_instancias()
        if not inst:
            print("\n  No encuentro bluestacks.conf.")
            print("  Comprueba que BlueStacks este instalado.\n")
            input("  Pulsa Intro para salir...")
            return

        print("\n" + "=" * 52)
        print("   Bot del Roaming Test - Nova Empire   (por ADB)")
        print("=" * 52)
        print("\n  Instancias encontradas:\n")
        for i, (nombre, puerto) in enumerate(inst, 1):
            print(f"    {i}  {nombre:<30} puerto {puerto}")
        print("\n  Acciones:")
        print("    C  Comprobar que ve el tablero  (no toca nada)")
        print("    J  Jugar en UNA instancia")
        print("    T  Jugar en TODAS a la vez")
        print("    S  Salir\n")

        acc = input("  Elige C, J, T o S: ").strip().lower()
        if acc == "s":
            return
        if acc not in ("c", "j", "t"):
            continue

        if acc == "t":
            elegidas = inst
        else:
            try:
                n = int(input(f"  Numero de instancia (1-{len(inst)}): "))
                elegidas = [inst[n - 1]]
                if n < 1:
                    raise ValueError
            except (ValueError, IndexError):
                print("  Numero no valido.")
                continue

        if acc == "c":
            print("\n  Deja el tablero a la vista en esa instancia.")
            input("  Pulsa Intro cuando lo tengas...")
            for nombre, puerto in elegidas:
                dev = f"127.0.0.1:{puerto}"
                print(f"\n  --- {nombre} ({dev}) ---")
                try:
                    cmd_check(AdbController(dev, adb))
                except Exception as e:                  # noqa: BLE001
                    print(f"  ERROR: {e}")
            input("\n  Pulsa Intro para volver al menu...")
            continue

        texto = input("  Cuantas partidas POR INSTANCIA (0 = sin limite): ").strip()
        try:
            partidas = max(0, int(texto))
        except ValueError:
            partidas = 1
        print("\n  Deja el Roaming Test abierto en esas instancias.")
        print("  Vale con el tablero a la vista o en la pantalla de inicio.")
        print("  No hace falta que BlueStacks este en primer plano.")
        print("  Para parar: Ctrl+C.\n")
        input("  Pulsa Intro para empezar...")

        bots = []
        for nombre, puerto in elegidas:
            try:
                bots.append(Bot(AdbController(f"127.0.0.1:{puerto}", adb)))
            except Exception as e:                      # noqa: BLE001
                print(f"  {nombre}: ERROR: {e}")
        try:
            if len(bots) == 1:
                bots[0].run(games=partidas)
            else:
                hilos = [threading.Thread(target=b.run, kwargs={"games": partidas},
                                          daemon=True) for b in bots]
                for h in hilos:
                    h.start()
                while any(h.is_alive() for h in hilos):
                    time.sleep(0.5)
        except KeyboardInterrupt:
            for b in bots:
                b.stop.set()
            print("\n  Detenido.")
        input("\n  Pulsa Intro para volver al menu...")


def cmd_check(ctrl):
    img = ctrl.capture()
    grid = detect_grid(img)
    print(f"Captura: {img.shape[1]}x{img.shape[0]} px")
    if grid is None:
        cv2.imwrite("nova_check.png", img)
        print("No se ha encontrado el tablero. Revisa nova_check.png: el juego "
              "debe estar visible y sin tapar.")
        return False
    board = read_board(img, grid)
    print(f"Tablero {grid.rows}x{grid.cols}, casilla {grid.dx:.1f}x{grid.dy:.1f} px, "
          f"origen ({grid.x0:.0f}, {grid.y0:.0f})")
    print(board_str(board))
    print(f"Casillas sin identificar: {unknown_count(board)}")
    vis = img.copy()
    for r in range(grid.rows):
        for c in range(grid.cols):
            x, y = grid.center(r, c)
            hw, hh = int(grid.dx / 2), int(grid.dy / 2)
            cv2.rectangle(vis, (x - hw, y - hh), (x + hw, y + hh), (0, 255, 0), 1)
            s = SYMBOLS.get(board[r][c], "?")
            cv2.putText(vis, s, (x - 10, y + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
            cv2.putText(vis, s, (x - 10, y + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imwrite("nova_check.png", vis)
    print("Guardado nova_check.png: comprueba que cada letra coincide con su ficha.")
    return True


def main():
    p = argparse.ArgumentParser(description="Bot del Roaming Test de Nova Empire")
    p.add_argument("--mode", choices=["adb"], default="adb",
                   help="solo ADB (se mantiene por compatibilidad)")
    p.add_argument("-d", "--device", action="append",
                   help="dispositivo ADB, repetible (p. ej. 127.0.0.1:5555)")
    p.add_argument("--adb-bin", default=None,
                   help="ruta a HD-Adb.exe; si no se indica, se busca solo")
    p.add_argument("--check", action="store_true", help="comprobar la deteccion y salir")
    p.add_argument("--activar-adb", action="store_true",
                   help="activar ADB en bluestacks.conf y salir")
    p.add_argument("--menu", action="store_true",
                   help="menu de texto interactivo")
    p.add_argument("--dry", action="store_true", help="mostrar el movimiento sin hacerlo")
    p.add_argument("--moves", type=int, default=30, help="movimientos por partida (30)")
    p.add_argument("--games", type=int, default=1,
                   help="partidas seguidas; 0 = hasta que se acaben los tickets")
    p.add_argument("--settle", type=float, default=0.45, help="pausa entre capturas")
    p.add_argument("--input", choices=["drag", "click"], default="drag",
                   help="arrastrar la ficha (por defecto) o pulsar las dos casillas")
    args = p.parse_args()

    if args.activar_adb:
        raise SystemExit(activar_adb())

    if args.menu:
        try:
            menu_texto()
        except KeyboardInterrupt:
            print("\nDetenido.")
        return

    adb = args.adb_bin or buscar_adb()
    devices = args.device or [f"127.0.0.1:{p}" for _, p in leer_instancias()[:1]] \
        or ["127.0.0.1:5555"]
    ctrls = [AdbController(d, adb, style=args.input) for d in devices]

    try:
        if args.check:
            for c in ctrls:
                cmd_check(c)
            return
        bots = [Bot(c, max_moves=args.moves, settle=args.settle) for c in ctrls]
        if len(bots) == 1:
            bots[0].run(dry=args.dry, games=args.games)
        else:
            ts = [threading.Thread(target=b.run,
                                   kwargs={"dry": args.dry, "games": args.games},
                                   daemon=True)
                  for b in bots]
            for t in ts:
                t.start()
            while any(t.is_alive() for t in ts):
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDetenido.")
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
