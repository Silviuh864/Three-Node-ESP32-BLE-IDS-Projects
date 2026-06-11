import numpy as np
from scipy.optimize import minimize

def trilat(nodes_data, node_positions, room_width, room_height):
    try:
        valid_points = []
        for nod, dist in nodes_data.items():
            if nod in node_positions and dist is not None:
                try:
                    d = float(dist)
                    if d <= 0: continue
                    pos_x = float(node_positions[nod][0])
                    pos_y = float(node_positions[nod][1])
                    valid_points.append(((pos_x, pos_y), d))
                except (ValueError, TypeError, IndexError):
                    continue

        if len(valid_points) < 3:
            return None

        # Initial guess: the geometric center of the active anchors
        x0 = np.mean([p[0][0] for p in valid_points])
        y0 = np.mean([p[0][1] for p in valid_points])

        # Loss function: Minimize the squared difference between physical distance and RSSI distance
        def loss_function(guess):
            x, y = guess
            error = 0
            for (nx, ny), r in valid_points:
                dist_calc = np.sqrt((x - nx)**2 + (y - ny)**2)
                error += (dist_calc - r)**2
            return error

        # Constrain the solver to mathematically stay inside the room boundaries
        bounds = [(0.0, float(room_width)), (0.0, float(room_height))]
        
        # L-BFGS-B is highly efficient for bounded spatial optimization
        res = minimize(loss_function, [x0, y0], bounds=bounds, method='L-BFGS-B')

        if res.success:
            return (round(res.x[0], 2), round(res.x[1], 2))
        else:
            return None

    except Exception as e:
        print(f"LST Debug Error: {e}")
        return None