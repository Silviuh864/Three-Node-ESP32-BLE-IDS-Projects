
def wcl(nodes_data, node_positions, room_width, room_height):
    
    noduri_valide = {
        nod: dist for nod, dist in nodes_data.items()
        if nod in node_positions and dist > 0
    }
    
    if len(noduri_valide) < 2:
        return None
    
    total_weight = 0.0
    x_sum = 0.0
    y_sum = 0.0

    for nod, dist in noduri_valide.items():
        x, y = node_positions[nod]
        weight = 1.0 / (dist ** 2)

        x_sum += weight * x
        y_sum += weight * y
        total_weight += weight

    x_est = x_sum / total_weight
    y_est = y_sum / total_weight

    x_est = max(0.0, min(x_est, room_width))
    y_est = max(0.0, min(y_est, room_height))

    return (round(x_est, 2), round(y_est, 2))