import serial
import time
from config import PORT, BAUD_RATE

def conecteaza():
    return serial.Serial(PORT, BAUD_RATE, timeout=0.1)

def citeste_linie(ser):
    if ser.in_waiting > 0:
        linie = ser.readline().decode('utf-8', errors='ignore').strip()
        if linie:
            return {
                'linie': linie,
                'timestamp': time.time()
            }
    return None

def parseaza_linie(pachet):
    if not pachet:
        return None
    
    parti = pachet['linie'].split('|')
    if len(parti) < 3:
        return None
    
    return {
        'tip': parti[0],
        'nod': parti[1],
        'date': parti[2],
        'timestamp': pachet['timestamp']  # adaugat aici
    }