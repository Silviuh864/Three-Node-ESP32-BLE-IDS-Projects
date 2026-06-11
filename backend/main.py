import threading

import time

import dash

from dash import dcc, html, dash_table

from dash.dependencies import Input, Output

import plotly.graph_objects as go

from queue import Queue, Full
import random
import traceback
message_queue = Queue(maxsize=1000)

PROCESS_INTERVAL = 0.005
DEVICE_UPDATE_INTERVAL = 0.2

# --- IMPORTURI MODULE PROPRII ---

from serial_reader import conecteaza, citeste_linie, parseaza_linie

from alert_manager import proceseaza_alerta

from node_state import actualizeaza_dist, calculeaza_pozitie_wcl, calculeaza_pozitie_trl,calculeaza_pozitie_fuzzy_wcl, obtine_date_valide, seteaza_configuratie

from logger import initializeaza_log, log_alerta, log_calibrare_start, log_calibrare_final, log_distanta
import node_state 
from manufacturer_db import resolve_manufacturer, resolve_manufacturer_full, incarca_yaml



# --- IMPORT CONFIGURARE ---

import config



NODE_POSITIONS = {
    1: {'x': 4, 'y': 3},
    2: {'x': 2, 'y': 4},
    3: {'x': 0.3, 'y': 0.3}
}



seteaza_configuratie(

    positions={

        'NOD:1': (4, 3),

        'NOD:2': (2, 4),

        'NOD:3': (0.3, 0.3)

    },

    width=5,

    height=5

)



COLORS = {

    'background': '#0b0e14',

    'card': '#151921',

    'trl_color': '#ff9800',

    'wcl_color': '#ff3e3e',

    'fuzzy_wcl_color': '#00ff00',

    'node_color': '#00f2ff',

    'text': '#e6edf3'

}



ADDR_TYPES = {

    '0': 'Public (Static)',

    '1': 'Random Static',

    '2': 'Resolvable Private (Mobile)',

    '3': 'Non-Resolvable Private'

}



ALPHA = 0.3



# --- STARE SISTEM ---

device_registry = {}

system_logs = []

mac_activ = {}

lock = threading.Lock()



def add_log(text):

    global system_logs

    ts = time.strftime("%H:%M:%S")

    with lock:

        system_logs.append(f"[{ts}] {text}")

        if len(system_logs) > 50:

            system_logs.pop(0)



# --- MOTOR SERIAL ---

def serial_engine():

    initializeaza_log()

    try:

        ser = conecteaza()

        add_log(f"System Online on {config.PORT}")



        while True:

            linie = citeste_linie(ser)

            if linie:

                mesaj = parseaza_linie(linie)

                if mesaj:
                    try:
                        message_queue.put(mesaj, timeout=1)
                    except Full:
                        add_log("WARNING: Message queue full, dropping message")


            with lock:
                now = time.time()
                timeout_sec = config.WINDOW_ALERTA_MS / 1000.0
                inactive = [
                    m for m, d in device_registry.items()
                    if now - d['last_seen_ts'] > timeout_sec
                    and now - d.get('last_snapshot_ts', 0) > timeout_sec
                ]
                for m in inactive:
                    del device_registry[m]

            for m in inactive:   # ← logarea DUPĂ ce se eliberează lock-ul
                add_log(f"TIMEOUT: {m[-5:]} pierdut")



            time.sleep(0.01)

    except Exception as e:

        add_log(f"SERIAL ERROR: {e}")



def proceseaza_backend(mesaj):

    global device_registry, mac_activ

    tip, nod, date = mesaj['tip'], mesaj['nod'], mesaj['date']


    if tip == '1':
        try:
            parts = date.split('|')
        
            rssi_1m_val = None
            for p in parts:
                if p.strip().startswith('RSSI_1M:'):
                    rssi_1m_val = float(p.strip().split('RSSI_1M:')[1])
                    break
        
            if rssi_1m_val is not None:
                from node_state import seteaza_rssi_1m
                seteaza_rssi_1m(nod, rssi_1m_val)
                add_log(f"Calibrare {nod}: RSSI_1M={rssi_1m_val:.2f} dBm")
            else:
                add_log(f"Calibrare {nod}: RSSI_1M lipsa, folosesc fallback")
            
        except Exception as e:
            print(f"[ERR TIP1] {e} | date='{date}'")
        
    elif tip == '3':

        try:

            parts = date.split('|')

            mac = parts[0].split('MAC:')[1]

            raw_type = parts[1].split('TYPE:')[1]

            mfg = parts[2].split('MFG:')[1]

            dev_name = ''
            for p in parts[3:]:
                if p.startswith('NAME:'):
                    dev_name = p.split('NAME:', 1)[1].strip()
                    break

            mac_activ[nod] = mac



            is_new = False

            with lock:

                if mac not in device_registry:

                    is_new = True

                    device_registry[mac] = {

                        'addr_type': ADDR_TYPES.get(raw_type, 'Unknown'),

                        'mfg_id': mfg,

                        'device_name': dev_name,

                        'x_trl': 0, 'y_trl': 0,

                        'x_wcl': 0, 'y_wcl': 0,
                        'x_fuzzy': 0, 'y_fuzzy': 0,

                        'last_seen_ts': time.time(),

                        'first_seen_ts': time.time()

                    }

                else:

                     device_registry[mac]['last_seen_ts'] = time.time()
                     if dev_name and dev_name != '[unnamed]' and not device_registry[mac].get('device_name'):
                        device_registry[mac]['device_name'] = dev_name
                     if mfg and device_registry[mac].get('mfg_id') in ('N/A', '', None):
                        device_registry[mac]['mfg_id'] = mfg
                     if raw_type and device_registry[mac].get('addr_type') == 'Unknown':
                        device_registry[mac]['addr_type'] = ADDR_TYPES.get(raw_type, 'Unknown')


            if is_new:

                name_str = f" [{dev_name}]" if dev_name else ""
                mfg_resolved = resolve_manufacturer(mfg)
                add_log(f"Intrusion! {mac[-5:]} Type:{raw_type} Mfg:{mfg_resolved}{name_str}")



        except Exception as e:

            print(f"[ERR TIP3] {e} | date='{date}'")



    elif tip == '2':
        try:
            # Parsare defensive - poate veni în diverse formate
            parts = date.split('|')
            
            # Verificăm fiecare pereche MAC:xxx|DIST:yyy
            i = 0
            while i < len(parts) - 1:
                try:
                    # Găsim prima parte care conține MAC:
                    if 'MAC:' not in parts[i]:
                        i += 1
                        continue
                    
                    # Verificăm că următoarea parte conține RSSI:
                    if i + 1 >= len(parts) or 'RSSI:' not in parts[i + 1]:
                        i += 1
                        continue
                    
                    # Extragem MAC și RSSI
                    mac = parts[i].split('MAC:')[1].strip()
                    rssi = float(parts[i + 1].split('RSSI:')[1].strip())
                    
                    # Validare MAC (format XX:XX:XX:XX:XX:XX sau XX-XX-XX...)
                    if len(mac) < 12:
                        i += 2
                        continue
                    
                    # Validare RSSI (pozitiv și rezonabil)
                    if rssi >= 0 or rssi <-100:
                        i += 2
                        continue
                    
                    # --- ACTUALIZARE ---
                    actualizeaza_dist(mac, nod, rssi, mesaj['timestamp'])
                    
                    with lock:
                        if mac not in device_registry:
                            device_registry[mac] = {
                                'addr_type': 'Unknown', 'mfg_id': 'N/A', 'device_name': '',
                                'x_wcl': 0, 'y_wcl': 0, 'x_trl': 0, 'y_trl': 0,'x_fuzzy': 0, 'y_fuzzy': 0,
                                'last_seen_ts': time.time(), 'first_seen_ts': time.time(),
                                'last_snapshot_ts': time.time()
                            }
                        
                        device_registry[mac]['last_seen_ts'] = time.time()
                        device_registry[mac]['last_snapshot_ts'] = time.time()
                        
                        # CALCUL WCL
                        res_wcl = calculeaza_pozitie_wcl(mac)
                        if res_wcl is not None:
                            nx, ny = res_wcl
                            device_registry[mac]['x_wcl'] = round(
                                ALPHA * nx + (1 - ALPHA) * device_registry[mac]['x_wcl'], 2)
                            device_registry[mac]['y_wcl'] = round(
                                ALPHA * ny + (1 - ALPHA) * device_registry[mac]['y_wcl'], 2)
                        
                        # CALCUL TRILATERAȚIE
                        nodes_data_debug = obtine_date_valide(mac)
                        print(f"[TRL DEBUG] {mac[-5:]} nodes available: {list(nodes_data_debug.keys())}")
                        res_trl = calculeaza_pozitie_trl(mac)
                        res_trl = calculeaza_pozitie_trl(mac)
                        print(f"[TRL RESULT] {mac[-5:]}: {res_trl}")
                        if res_trl is not None:
                            tx, ty = res_trl
                            device_registry[mac]['x_trl'], device_registry[mac]['y_trl'] = tx, ty
                        
                        # CALCUL FUZZY WCL
                        res_fuzzy = calculeaza_pozitie_fuzzy_wcl(mac)
                        if res_fuzzy is not None:
                            fx, fy = res_fuzzy
                            device_registry[mac]['x_fuzzy'] = round(
                                ALPHA * fx + (1 - ALPHA) * device_registry[mac]['x_fuzzy'], 2)
                            device_registry[mac]['y_fuzzy'] = round(
                                ALPHA * fy + (1 - ALPHA) * device_registry[mac]['y_fuzzy'], 2)
                    
                    i += 2  # Sărim peste perechea MAC|DIST procesată
                    
                except (ValueError, IndexError, AttributeError) as parse_err:
                    # Eroare la parsarea acestei perechi - sărim peste ea
                    print(f"[TIP2 SKIP] {parse_err} | part={parts[i] if i < len(parts) else 'N/A'}")
                    i += 1
                    continue

        except Exception as e:
            print(f"[DEBUG TIP2] {e} | Date: {date}")


# --- DASHBOARD UI ---

app = dash.Dash(__name__, title="IDS Terminal v2.0")



app.index_string = '''

<!DOCTYPE html><html><head>{%metas%}<title>IDS Terminal</title>{%css%}

<meta name="viewport" content="width=device-width, initial-scale=1.0">

<style>

    * { box-sizing: border-box; }

    body { margin: 0; padding: 0; background-color: #0b0e14; overflow-x: hidden; }

    ::-webkit-scrollbar { width: 4px; }

    ::-webkit-scrollbar-thumb { background: #333; border-radius: 10px; }



    .main-container {

        display: flex;

        flex-direction: row;

        flex: 1;

        gap: 10px;

        padding: 10px;

    }

    .left-panel {

        flex: 1.7;

        display: flex;

        flex-direction: column;

        gap: 10px;

        overflow: hidden;

    }

    .right-panel {

        flex: 1.3;

        background-color: #151921;

        padding: 15px;

        border-radius: 4px;

        display: flex;

        flex-direction: column;

    }



    @media (max-width: 768px) {

        body { overflow-y: auto; }

        .main-container {

            flex-direction: column;

            height: auto;

        }

        .left-panel {

            flex: none;

            width: 100%;

            overflow: visible;

        }

        .right-panel {

            flex: none;

            width: 100%;

            height: 60vh;

        }

        h4 { font-size: 0.75rem !important; letter-spacing: 1px !important; }

    }

</style>

</head><body>{%app_entry%}{%config%}{%scripts%}{%renderer%}</body></html>

'''



app.layout = html.Div(

    style={

        'backgroundColor': COLORS['background'],

        'minHeight': '100vh',

        'width': '100vw',

        'display': 'flex',

        'flexDirection': 'column',

        'color': COLORS['text'],

        'fontFamily': 'sans-serif'

    },

    children=[



        # Header

        html.Div(

            style={

                'backgroundColor': COLORS['card'],

                'padding': '5px 25px',

                'display': 'flex',

                'justifyContent': 'space-between',

                'alignItems': 'center',

                'borderBottom': '1px solid #222',

                'height': '45px',

                'flexShrink': '0'

            },

            children=[

                html.H4(

                    f"SECURITY TERMINAL - {config.PORT}",

                    style={'margin': '0', 'color': '#00f2ff', 'letterSpacing': '2px'}

                ),

                html.H4(

                    id='live-clock',

                    style={'margin': '0', 'fontFamily': 'monospace', 'color': '#00f2ff'}

                )

            ]

        ),



        # Container principal

        html.Div(

            className='main-container',

            children=[



                # Stânga: Registry + Logs

                html.Div(

                    className='left-panel',

                    children=[



                        # Registry

                        html.Div(

                            style={

                                'backgroundColor': COLORS['card'],

                                'padding': '15px',

                                'borderRadius': '4px',

                                'flex': '2',

                                'display': 'flex',

                                'flexDirection': 'column',

                                'minHeight': '200px'

                            },

                            children=[

                                html.Div([
                                html.H6(
                                "ACTIVE DEVICE REGISTRY",
                                style={'marginTop': '0', 'opacity': '0.6', 'fontSize': '0.7rem', 'display': 'inline'}
                                ),
                                html.Span(
                                id='device-count-badge',
                                children='(0)',
                                style={
                                    'marginLeft': '8px',
                                    'backgroundColor': '#00f2ff',
                                    'color': '#0a0a1a',
                                    'borderRadius': '10px',
                                    'padding': '1px 8px',
                                    'fontSize': '0.7rem',
                                    'fontWeight': 'bold'
                                    }
                                )
                            ], style={'marginBottom': '8px'}),

                                dash_table.DataTable(

                                    id='device-table',

                                    columns=[

                                        {"name": "MAC ADDRESS", "id": "mac"},

                                        {"name": "DEVICE NAME", "id": "device_name"},

                                        {"name": "ADDRESS TYPE", "id": "type"},

                                        {"name": "MANUFACTURER ID", "id": "mfg"},

                                        {"name": "LAST SEEN", "id": "last_seen"},

                                        {"name": "DWELL TIME", "id": "dwell"}

                                    ],

                                    style_header={

                                        'backgroundColor': '#1c1f26',

                                        'color': '#00f2ff',

                                        'border': 'none',

                                        'fontSize': '11px'

                                    },

                                    style_cell={

                                        'backgroundColor': 'transparent',

                                        'color': '#fff',

                                        'borderBottom': '1px solid #282c34',

                                        'padding': '8px',

                                        'fontSize': '11px',

                                        'textOverflow': 'ellipsis',

                                        'overflow': 'hidden'

                                    },

                                    style_data_conditional=[
                                    {
                                    'if': {'column_id': 'type', 'filter_query': '{type} contains "Public"'},
                                    'color': '#00f2ff'
                                     },
                                    {           
                                    'if': {'column_id': 'type', 'filter_query': '{type} contains "Random Static"'},
                                    'color': '#00ff88'
                                    },
                                    {
                                    'if': {'column_id': 'type', 'filter_query': '{type} contains "Resolvable Private"'},
                                    'color': '#ffea00'
                                    },
                                    {
                                    'if': {'column_id': 'type', 'filter_query': '{type} contains "Non-Resolvable"'},
                                    'color': '#ff3e3e'
                                    }
                                    ],

                                    style_table={

                                        'overflowY': 'scroll',

                                        'height': '200px',

                                        'minWidth': '100%'

                                    }

                                )

                            ]

                        ),



                        # Logs

                        html.Div(

                            style={

                                'backgroundColor': COLORS['card'],

                                'padding': '15px',

                                'borderRadius': '4px',

                                'flex': '1',

                                'display': 'flex',

                                'flexDirection': 'column',

                                'minHeight': '150px'

                            },

                            children=[

                                html.H6(

                                    "SYSTEM LIVE LOGS",

                                    style={'marginTop': '0', 'opacity': '0.6', 'fontSize': '0.7rem'}

                                ),

                                html.Div(

                                    id='log-terminal',

                                    style={

                                        'fontFamily': 'monospace',

                                        'fontSize': '0.75rem',

                                        'overflowY': 'scroll',

                                        'color': '#777',

                                        'backgroundColor': '#0d1117',

                                        'padding': '8px',

                                        'height': '150px',

                                        'boxSizing': 'border-box'

                                    }

                                )

                            ]

                        )

                    ]

                ),



                # Dreapta: Hartă

                html.Div(

                    className='right-panel',

                    children=[

                        html.H6(

                            "LIVE SPATIAL VIEW",

                            style={'textAlign': 'center', 'margin': '0 0 5px 0', 'fontSize': '0.7rem'}

                        ),

                        html.Div(

                            style={

                                'display': 'flex',

                                'justifyContent': 'center',

                                'gap': '15px',

                                'marginBottom': '10px',

                                'fontSize': '0.6rem'

                            },

                            children=[

                                html.Div([html.Span("● ", style={'color': COLORS['node_color']}), "NODE"]),

                                html.Div([html.Span("● ", style={'color': COLORS['trl_color']}), "TRL (LST)"]),

                                html.Div([html.Span("● ", style={'color': COLORS['wcl_color']}), "WCL (Weighted)"]),

                                html.Div([html.Span("● ", style={'color': COLORS['fuzzy_wcl_color']}), "FUZZY WCL"])
                                

                            ]

                        ),

                        dcc.Graph(

                            id='live-map',

                            config={'displayModeBar': False},

                            style={'flex': '1', 'minHeight': '300px'}

                        )

                    ]

                )

            ]

        ),



        dcc.Interval(id='ui-update', interval=250)

    ]

)





@app.callback(

    [Output('live-map', 'figure'), Output('device-table', 'data'),
    Output('device-count-badge', 'children'),
    
    Output('live-clock', 'children'), Output('log-terminal', 'children')],

    [Input('ui-update', 'n_intervals')]

)

def update_ui(n):

    with lock:

        devices = list(device_registry.items())

        current_logs = list(system_logs)



    curr_time = time.strftime("%H:%M:%S")

    table_data = []

    fig = go.Figure()



    # Noduri fixe

    node_x = [p['x'] for p in NODE_POSITIONS.values()]

    node_y = [p['y'] for p in NODE_POSITIONS.values()]

    fig.add_trace(go.Scatter(

        x=node_x, y=node_y,

        mode='markers+text',

        text=["N1", "N2", "N3"],

        textposition="bottom center",

        marker=dict(

            size=12, symbol='diamond',

            color=COLORS['node_color'],

            line=dict(width=1, color='white')

        )

    ))



    # Dispozitive

    for mac, d in devices:

        last_seen_str = time.strftime("%H:%M:%S", time.localtime(d['last_seen_ts']))

        dwell_sec = int(time.time() - d['first_seen_ts'])

        dwell_str = f"{dwell_sec // 60}m {dwell_sec % 60}s"



        table_data.append({

            'mac': mac,

            'type': d['addr_type'],

            'device_name': d.get('device_name', ''),

            'mfg': resolve_manufacturer(d['mfg_id']),

            'last_seen': last_seen_str,

            'dwell': dwell_str

        })



        # TRL

        fig.add_trace(go.Scatter(

            x=[d['x_trl']], y=[d['y_trl']],

            mode='markers',

            name=f"{mac[-5:]} TRL",

            marker=dict(

                size=14, color=COLORS['trl_color'],

                line=dict(width=1, color='white')

            )

        ))



        # WCL

        fig.add_trace(go.Scatter(

            x=[d['x_wcl']], y=[d['y_wcl']],

            mode='markers',

            name=f"{mac[-5:]} WCL",

            marker=dict(size=10, color=COLORS['wcl_color'], symbol='x')

        ))

        fig.add_trace(go.Scatter(
            x=[d['x_fuzzy']], y=[d['y_fuzzy']],
            mode='markers',
            name=f"{mac[-5:]} FUZZY WCL",
            marker=dict(size=10, color=COLORS['fuzzy_wcl_color'], symbol='cross')
        ))



    fig.update_layout(
        
        template="plotly_dark",

        paper_bgcolor='rgba(0,0,0,0)',

        plot_bgcolor='rgba(0,0,0,0)',

        margin=dict(l=10, r=10, t=10, b=10),

        xaxis=dict(range=[-1, node_state.room_width], showgrid=True, gridcolor='#222', zeroline=False),

        yaxis=dict(range=[-1, node_state.room_height], showgrid=True, gridcolor='#222',

                   zeroline=False, scaleanchor="x", scaleratio=1),

        showlegend=False,



    )

    fig.add_shape(
    type='rect',
    x0=0, y0=0,
    x1=node_state.room_width, y1=node_state.room_height,
    line=dict(color="#ff0000", width=2, dash='dot'),
    fillcolor='rgba(0, 242, 255, 0.03)'
)



    formatted_logs = [html.P(log, style={'margin': '2px 0'}) for log in reversed(current_logs)]

    return fig, table_data, f"({len(table_data)})", curr_time, formatted_logs




def processing_engine():
    while True:
        try:
            mesaj = message_queue.get()
            proceseaza_backend(mesaj)
            time.sleep(PROCESS_INTERVAL)
        except Exception as e:
            print("[PROCESS ERROR]", e)
            print(traceback.format_exc())

if __name__ == "__main__":

    threading.Thread(target=serial_engine, daemon=True).start()
    threading.Thread(target=processing_engine, daemon=True).start()
    app.run(debug=False, host='0.0.0.0', port=8050)