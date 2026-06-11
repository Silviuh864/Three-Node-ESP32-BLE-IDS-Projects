import time
from config import WINDOW_ALERTA_MS, NOD_INTRARE, MIN_CONFIRMARI

alerte = {}

def proceseaza_alerta(mac, nod):
    acum = time.time() * 1000

    if mac not in alerte:
        alerte[mac] = {}
    alerte[mac][nod] = acum

    for m in list(alerte.keys()):
        for n in list(alerte[m].keys()):
            if acum - alerte[m][n] > WINDOW_ALERTA_MS:
                del alerte[m][n]
        if not alerte[m]:
            del alerte[m]

    confirmari = []
    if mac in alerte:
        confirmari = [n for n in NOD_INTRARE if n in alerte[mac]]
    if len(confirmari) >= MIN_CONFIRMARI:
        print(f"\n ALERTA CONFIRMATA!")
        print(f"   MAC:  {mac}")
        print(f"   Confirmat de: {confirmari}")
        print(f"   Timp: {time.strftime('%H:%M:%S')}\n")
        del alerte[mac]
        return True
    return False