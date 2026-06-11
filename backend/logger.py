import csv
import os
import time

def initializeaza_log():
    global LOG_FILE
    LOG_FILE = f"sesiune_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    with open(LOG_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timp', 'tip', 'nod', 'valoare', 'extra'])

def log_calibrare_start(nod):
    _scrie_linie(nod, 'CALIBRARE_START', '-', '-')

def log_calibrare_final(nod):
    _scrie_linie(nod, 'CALIBRARE_FINAL', '-', '-')

def log_distanta(nod, dist, timestamp):
    timp_formatat = time.strftime('%H:%M:%S', time.localtime(timestamp))
    _scrie_linie(nod, 'DISTANTA', f'{dist:.2f}', timp_formatat)

def log_alerta(nod, mac):
    _scrie_linie(nod, 'ALERTA', mac, '-')

def log_alerta_confirmata(mac):
    _scrie_linie('SISTEM', 'ALERTA_CONFIRMATA', mac, '-')

def _scrie_linie(nod, tip, valoare, extra):
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            time.strftime('%H:%M:%S'),
            tip,
            nod,
            valoare,
            extra
        ])