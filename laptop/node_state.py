import time
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'localization'))

from wcl import wcl
noduri = {}
node_positions = {} 
room_width = 0
room_height = 0

def seteaza_configuratie(positions, width, height):
    global node_positions, room_width, room_height
    node_positions = positions
    room_width = width
    room_height = height

def actualizeaza_dist(nod, dist, timestamp):
    noduri.setdefault(nod, {})
    noduri[nod]['dist'] = dist
    noduri[nod]['timestamp'] = timestamp
    
   
    return calculeaza_pozitie_wcl()

def calculeaza_pozitie_wcl():
    acum = time.time() * 1000
    
    nodes_data = {}
    for nod, data in noduri.items():
        if 'dist' in data:
            vechime = acum - data.get('timestamp', 0) * 1000
            if vechime < 500:
                nodes_data[nod] = data['dist']
    
    if len(nodes_data) < 2:
        return None
    
    return wcl(nodes_data, node_positions, room_width, room_height)