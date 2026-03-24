import time
from serial_reader import conecteaza, citeste_linie, parseaza_linie
from alert_manager import proceseaza_alerta
from node_state import actualizeaza_dist, calculeaza_pozitie_wcl
from logger import (initializeaza_log, log_calibrare_start,
                    log_calibrare_final, log_distanta,
                    log_alerta, log_alerta_confirmata)
from visualizer import (porneste_harta, deseneaza_harta,
                        actualizeaza_pozitie, actualizeaza_alerta,
                        seteaza_pozitie_wcl)

mac_activ = {}

def proceseaza_mesaj(mesaj):
    tip = mesaj['tip']
    nod = mesaj['nod']
    date = mesaj['date']

    if tip == '0':
        print(f"[CALIBRARE START] {nod}")
        log_calibrare_start(nod)

    elif tip == '1':
        print(f"[CALIBRARE FINAL] {nod}")
        log_calibrare_final(nod)

    elif tip == '2':
        try:
            dist = float(date.split(':')[1])
            pozitie = actualizeaza_dist(nod, dist, mesaj['timestamp'])
            timp_formatat = time.strftime('%H:%M:%S',
                            time.localtime(mesaj['timestamp']))
            print(f"[DIST] {nod} → {dist:.2f}m | t={timp_formatat}")
            log_distanta(nod, dist, mesaj['timestamp'])

            if nod in mac_activ:
                actualizeaza_pozitie(mac_activ[nod], nod, dist)

            if pozitie and nod in mac_activ:
                print(f"[WCL] x={pozitie[0]:.2f}m y={pozitie[1]:.2f}m")
                seteaza_pozitie_wcl(mac_activ[nod], pozitie[0], pozitie[1])

        except ValueError:
            print(f"[EROARE] Distanta invalida: {date}")

    elif tip == '3':
        try:
            mac = date.split('MAC:')[1]
            print(f"[ALERTA] {nod} → {mac}")
            log_alerta(nod, mac)
            mac_activ[nod] = mac
            if proceseaza_alerta(mac, nod):
                log_alerta_confirmata(mac)
                actualizeaza_alerta(mac)
        except IndexError:
            print(f"[EROARE] MAC invalid: {date}")


def main():
    initializeaza_log()
    fig, ax = porneste_harta()

    try:
        ser = conecteaza()
        print(f"[*] Sistem pornit\n")
        last_draw = time.time()

        while True:
            linie = citeste_linie(ser)
            if linie:
                mesaj = parseaza_linie(linie)
                if mesaj:
                    proceseaza_mesaj(mesaj)

            if time.time() - last_draw > 0.5:
                deseneaza_harta(ax)
                fig.canvas.flush_events()
                last_draw = time.time()

    except KeyboardInterrupt:
        print("\n[!] Oprit de utilizator.")
    except Exception as e:
        print(f"Eroare: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()
