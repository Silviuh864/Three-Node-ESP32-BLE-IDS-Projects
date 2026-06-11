import time
import sys
import os

# Asigurăm calea către modulele de localizare
sys.path.append(os.path.join(os.path.dirname(__file__), 'localization'))

from wcl import wcl
from trilateration import trilat
from fuzzy_wcl import compute_weight
from config import PATH_LOSS_INDEX, RSSI_DELTA_THRESHOLD, RSSI_1M

# Configurații globale de mediu
node_positions = {} 
room_width = 0
room_height = 0

# Structura centrală: { MAC: { NOD_ID: {'dist': float, 'timestamp': float} } }
dispozitive_active = {}
rssi_1m_per_nod = {}

def seteaza_rssi_1m(nod, rssi_1m):
    rssi_1m_per_nod[nod] = rssi_1m

def seteaza_configuratie(positions, width, height):
    global node_positions, room_width, room_height
    node_positions = positions
    room_width = width
    room_height = height


def actualizeaza_dist(mac, nod, rssi, timestamp):
    """
    Salvează distanța raportată de un nod specific pentru un anumit MAC.
    """
    rssi_1m = rssi_1m_per_nod.get(nod, RSSI_1M)
    dist = 10 ** ((rssi_1m - rssi) / (10 * PATH_LOSS_INDEX))
    dist = max(0.1, min(dist, 50.0))
    if mac not in dispozitive_active:
        dispozitive_active[mac] = {}
    
    dispozitive_active[mac][nod] = {
        'dist': float(dist),
        'rssi': rssi,
        'timestamp': timestamp
    }

def obtine_date_valide(mac):
    """
    Filtrează nodurile care au raportat date recente (sub 1 secundă) pentru un MAC specific.
    """
    acum = time.time() * 1000  # Timp curent în milisecunde
    if mac not in dispozitive_active:
        return {}

    nodes_data = {}
    for nod, data in dispozitive_active[mac].items():
        # Verificăm vechimea pachetului raportat de nodul respectiv
        vechime = acum - (data.get('timestamp', 0) * 1000)
        
        # Validăm doar datele care au o vechime mai mică de 1000ms
        if vechime < 7000:  # 7 secunde pentru a fi mai permisivi
            nodes_data[nod] = data['dist']
            
    return nodes_data

def calculeaza_pozitie_wcl(mac):
    """
    Calculează poziția prin Weighted Centroid Localization pentru un MAC specific.
    Necesită minim 2 noduri.
    """
    nodes_data = obtine_date_valide(mac)
    
    if len(nodes_data) < 2:
        return None
    
    return wcl(nodes_data, node_positions, room_width, room_height)
def calculeaza_pozitie_fuzzy_wcl(mac):
    nodes_data = obtine_date_valide(mac)
    
    if len(nodes_data) < 2:
        return None
    
    fuzzy_weights = {
        nod: compute_weight(dispozitive_active[mac][nod]['rssi'], dist)
        for nod, dist in nodes_data.items()
    }
    
    return wcl(nodes_data, node_positions, room_width, room_height, weights=fuzzy_weights)

def calculeaza_pozitie_trl(mac):
    """
    Calculează poziția prin Trilaterație (LST) pentru un MAC specific.
    Necesită minim 3 noduri pentru o soluție stabilă în 2D.
    """
    nodes_data = obtine_date_valide(mac)
    
    # Trilaterația matematică necesită cel puțin 3 cercuri care să se intersecteze
    if len(nodes_data) < 3:
        return None
    
    return trilat(nodes_data, node_positions, room_width, room_height)