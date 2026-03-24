import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import time
from node_state import seteaza_configuratie
room_width = 0
room_height = 0
node_positions = {}
detected_devices = {}
alerte_active = {}

def initializeaza_harta():
    global room_width, room_height, node_positions

    print("\n--- CONFIGURARE CAMERA ---")
    room_width = float(input("Latimea camerei (m): "))
    room_height = float(input("Lungimea camerei (m): "))

    print("\n--- POZITII NODURI ---")
    print(f"Camera: {room_width}m x {room_height}m")
    print("Nodurile sunt dispuse in triunghi:")
    print("  NOD:1 si NOD:2 la intrare (y=0)")
    print("  NOD:3 in fundul camerei (y=lungime)")

    print("\nNOD:1 (stanga intrare):")
    x1 = float(input(f"  X (0 - {room_width}): "))
    y1 = float(input(f"  Y (0 - {room_height}): "))

    print("NOD:2 (dreapta intrare):")
    x2 = float(input(f"  X (0 - {room_width}): "))
    y2 = float(input(f"  Y (0 - {room_height}): "))

    print("NOD:3 (fund camera):")
    x3 = float(input(f"  X (0 - {room_width}): "))
    y3 = float(input(f"  Y (0 - {room_height}): "))

    node_positions = {
        'NOD:1': (x1, y1),
        'NOD:2': (x2, y2),
        'NOD:3': (x3, y3)
    }

    print("\n--- CONFIGURARE COMPLETA ---")
    print(f"NOD:1 → ({x1}, {y1})")
    print(f"NOD:2 → ({x2}, {y2})")
    print(f"NOD:3 → ({x3}, {y3})")
    print("----------------------------\n")
    seteaza_configuratie(node_positions, room_width, room_height)
def deseneaza_harta(ax):
    ax.clear()

    # --- Camera ---
    camera = plt.Rectangle(
        (0, 0), room_width, room_height,
        linewidth=2, edgecolor='black',
        facecolor='#f0f0f0'
    )
    ax.add_patch(camera)

    # --- Intrare ---
    ax.annotate(
        '▼ INTRARE',
        xy=(room_width/2, 0),
        fontsize=9, ha='center', va='top',
        color='green', fontweight='bold'
    )

    # --- Noduri ---
    acum = time.time()
    for nod, (x, y) in node_positions.items():
        # Cerc acoperire pentru fiecare device activ
        for mac, data in detected_devices.items():
            if nod in data and 'dist' in data[nod]:
                dist = data[nod]['dist']
                cerc = plt.Circle(
                    (x, y), dist,
                    color='#2196F3', alpha=0.08,
                    linestyle='--', fill=True
                )
                ax.add_patch(cerc)

        # Marker nod
        ax.plot(x, y, 's',
                markersize=18,
                color='#2196F3',
                zorder=5)
        ax.annotate(
            nod.replace('NOD:', 'N'),
            xy=(x, y),
            fontsize=7, ha='center', va='center',
            color='white', fontweight='bold',
            zorder=6
        )

    # --- Dispozitive detectate ---
    for mac, data in list(detected_devices.items()):
        # Elimini dispozitive vechi > 15s
        if acum - data.get('timestamp', 0) > 15:
            del detected_devices[mac]
            continue

        if 'x' in data and 'y' in data:
            # Rosu daca in alerta, portocaliu altfel
            culoare = '#F44336' if mac in alerte_active else '#FF9800'

            ax.plot(data['x'], data['y'], 'o',
                    markersize=14,
                    color=culoare,
                    zorder=7)

    # --- Alerte active — curata doar fara afisare text ---
    for mac, ts in list(alerte_active.items()):
        if acum - ts > 30:  # 30s timeout alerta
            del alerte_active[mac]

    # --- Legenda ---
    legenda = [
        mpatches.Patch(color='#2196F3', label='Nod ESP32'),
        mpatches.Patch(color='#FF9800', label='Device detectat'),
        mpatches.Patch(color='#F44336', label='Device in alerta'),
    ]
    ax.legend(handles=legenda, loc='upper right', fontsize=8)

    # --- Formatare ---
    ax.set_xlim(-0.5, room_width + 0.5)
    ax.set_ylim(-1.0, room_height + 0.5)
    ax.set_xlabel('X (metri)', fontsize=9)
    ax.set_ylabel('Y (metri)', fontsize=9)
    ax.set_title(
        f'IDS — Harta Camera | {time.strftime("%H:%M:%S")}',
        fontsize=11
    )
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)

def actualizeaza_pozitie(mac, nod, dist):
    if mac not in detected_devices:
        detected_devices[mac] = {}
    detected_devices[mac][nod] = {'dist': dist}
    detected_devices[mac]['timestamp'] = time.time()

def actualizeaza_alerta(mac):
    alerte_active[mac] = time.time()

def seteaza_pozitie_wcl(mac, x, y):
    if mac in detected_devices:
        detected_devices[mac]['x'] = x
        detected_devices[mac]['y'] = y

def porneste_harta():
    initializeaza_harta()
    fig, ax = plt.subplots(figsize=(8, 7))
    plt.ion()
    plt.show(block=False)
    return fig, ax