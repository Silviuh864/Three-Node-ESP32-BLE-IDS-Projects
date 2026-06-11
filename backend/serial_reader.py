import serial
import time
from config import PORT, BAUD_RATE

def conecteaza():
    try:
        # dsrdtr=True este crucial pentru anumite convertoare USB-Serial de pe ESP32
        ser = serial.Serial(PORT, BAUD_RATE, timeout=0.1, dsrdtr=True)
        # Curățăm buffer-ul la conectare pentru a evita date reziduale
        ser.reset_input_buffer() 
        return ser
    except Exception as e:
        print(f"EROARE CONECTARE SERIALĂ: {e}")
        return None

def citeste_linie(ser):
    if ser and ser.in_waiting > 0:
        try:
            linie = ser.readline().decode('utf-8', errors='ignore').strip()
            if linie:
                # Debug: util pentru a vedea fluxul brut de date de la Master
                print(f"RAW: {linie}") 
                return {
                    'linie': linie,
                    'timestamp': time.time()
                }
        except Exception as e:
            print(f"Eroare citire: {e}")
    return None

def parseaza_linie(pachet):
    """
    Transformă liniile primite de la Master în dicționare procesabile.
    Formate așteptate:
    Tip 2 (Snapshot): "2|NOD:X|MAC:XX:XX:XX...|DIST:0.00"
    Tip 3 (Alertă):   "3|NOD:X|MAC:XX:XX:XX...|TYPE:0|MFG:0x0000"
    """
    if not pachet:
        return None
    
    try:
        parti = pachet['linie'].split('|')
        
        # Validare minimă
        if len(parti) < 3:
            print(f"[PARSE WARN] Pachet prea scurt: {pachet['linie']}")
            return None
        
        tip = parti[0].strip()
        nod = parti[1].strip()
        
        # Verificare format tip
        if tip not in ['0', '1', '2', '3']:
            print(f"[PARSE WARN] Tip necunoscut '{tip}': {pachet['linie']}")
            return None
        
        # Verificare format nod
        if not nod.startswith('NOD:'):
            print(f"[PARSE WARN] Format nod invalid '{nod}': {pachet['linie']}")
            return None
        
        # Datele brute (MAC:..., DIST:... sau TYPE:...)
        date_brute = "|".join(parti[2:])
        
        return {
            'tip': tip,
            'nod': nod,
            'date': date_brute,
            'timestamp': pachet['timestamp']
        }
        
    except Exception as e:
        print(f"[PARSE ERR] {e} | Linie: {pachet.get('linie', 'N/A')}")
        return None