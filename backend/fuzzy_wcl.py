import numpy as np
import skfuzzy as fuzz
import math

rssi_universe = np.arange(-100, -20, 0.1)
dist_universe = np.arange(0, 12, 0.01)
output_constants = [0.05, 0.25, 0.50, 0.75, 0.95]

rssi_very_weak  = fuzz.trapmf(rssi_universe, [-100, -100, -90, -75])
rssi_weak       = fuzz.trimf(rssi_universe,  [-90, -75, -60])
rssi_medium     = fuzz.trimf(rssi_universe,  [-75, -60, -40])
rssi_strong     = fuzz.trimf(rssi_universe,  [-60, -40, -20])
rssi_very_strong= fuzz.trapmf(rssi_universe, [-40, -25, -20, -20])

dist_very_close = fuzz.trapmf(dist_universe, [0, 0, 0.5, 2])
dist_close      = fuzz.trimf(dist_universe,  [0.5, 2, 4])
dist_medium     = fuzz.trimf(dist_universe,  [2, 4, 6])
dist_far        = fuzz.trimf(dist_universe,  [4, 6, 8])
dist_very_far   = fuzz.trapmf(dist_universe, [6, 8, 12, 12])

def euclidean(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def rssi_to_dist(rssi, rssi_1m=-59, path_loss=3.0):
    return 10 ** ((rssi_1m - rssi) / (10 * path_loss))

def plain_wcl(nodes, weights):
    total = sum(weights.values())
    x = sum(weights[n] * nodes[n][0] for n in nodes) / total
    y = sum(weights[n] * nodes[n][1] for n in nodes) / total
    return round(x, 3), round(y, 3)

def run_simulation():
    print("\n--- NODE POSITIONS ---")
    nodes = {}
    for name in ['NOD:1', 'NOD:2', 'NOD:3']:
        x = float(input(f"  {name} X: "))
        y = float(input(f"  {name} Y: "))
        nodes[name] = (x, y)

    print("\n--- GROUND TRUTH POSITION ---")
    gt_x = float(input("  Real X: "))
    gt_y = float(input("  Real Y: "))
    ground_truth = (gt_x, gt_y)

    print("\n--- RSSI PER NODE ---")
    rssi_values = {}
    for name in ['NOD:1', 'NOD:2', 'NOD:3']:
        rssi_values[name] = float(input(f"  {name} RSSI (dBm): "))

    # compute per node
    print(f"\n{'NODE':<8}{'TRUE_DIST':>10}{'EST_DIST':>10}"
          f"{'RSSI':>8}{'FUZZY_W':>10}{'PLAIN_W':>10}")
    print("-" * 56)

    fuzzy_weights = {}
    plain_weights = {}
    est_dists     = {}

    for name in ['NOD:1', 'NOD:2', 'NOD:3']:
        true_dist = euclidean(nodes[name], ground_truth)
        est_dist  = rssi_to_dist(rssi_values[name])
        est_dist  = max(0.1, min(est_dist, 12.0))
        fw = compute_weight(rssi_values[name], est_dist)
        pw = 1.0 / (est_dist ** 2)

        fuzzy_weights[name] = fw
        plain_weights[name] = pw
        est_dists[name]     = est_dist

        print(f"{name:<8}{true_dist:>10.3f}{est_dist:>10.3f}"
              f"{rssi_values[name]:>8.1f}{fw:>10.4f}{pw:>10.4f}")

    
    wcl_plain = plain_wcl(nodes, plain_weights)
    wcl_fuzzy = plain_wcl(nodes, fuzzy_weights)

    err_plain = euclidean(wcl_plain, ground_truth)
    err_fuzzy = euclidean(wcl_fuzzy, ground_truth)

    print(f"\n{'Method':<15}{'X':>8}{'Y':>8}{'ERROR':>10}")
    print("-" * 41)
    print(f"{'Ground Truth':<15}{gt_x:>8.3f}{gt_y:>8.3f}")
    print(f"{'Plain WCL':<15}{wcl_plain[0]:>8.3f}{wcl_plain[1]:>8.3f}{err_plain:>10.3f}m")
    print(f"{'Fuzzy WCL':<15}{wcl_fuzzy[0]:>8.3f}{wcl_fuzzy[1]:>8.3f}{err_fuzzy:>10.3f}m")

    improvement = ((err_plain - err_fuzzy) / err_plain) * 100
    print(f"\n  Improvement: {improvement:+.1f}%")

    again = input("\nRun another simulation? (y/n): ")
    if again.lower() == 'y':
        run_simulation()

def compute_weight(rssi, distance):
    
    r_vw = fuzz.interp_membership(rssi_universe, rssi_very_weak,    rssi)
    r_w  = fuzz.interp_membership(rssi_universe, rssi_weak,         rssi)
    r_m  = fuzz.interp_membership(rssi_universe, rssi_medium,       rssi)
    r_s  = fuzz.interp_membership(rssi_universe, rssi_strong,       rssi)
    r_vs = fuzz.interp_membership(rssi_universe, rssi_very_strong,  rssi)

    d_vc = fuzz.interp_membership(dist_universe, dist_very_close, distance)
    d_c  = fuzz.interp_membership(dist_universe, dist_close,      distance)
    d_m  = fuzz.interp_membership(dist_universe, dist_medium,     distance)
    d_f  = fuzz.interp_membership(dist_universe, dist_far,        distance)
    d_vf = fuzz.interp_membership(dist_universe, dist_very_far,   distance)

    rssi_mfs = [r_vw, r_w, r_m, r_s, r_vs]
    dist_mfs = [d_vc, d_c, d_m, d_f, d_vf]

    
    firing_strengths = []
    fired_constants  = []

    for i in range(5):
        for j in range(5):
            strength = min(rssi_mfs[i], dist_mfs[j])
            if strength > 0:
                fired_constants.append(output_constants[rule_table[i][j]])
                firing_strengths.append(strength)

    
    if not firing_strengths:
        return 0.05  

    numerator   = sum(s * c for s, c in zip(firing_strengths, fired_constants))
    denominator = sum(firing_strengths)
    return round(numerator / denominator, 4)

rule_table = [
    [0, 0, 0, 0, 0],
    [1, 1, 0, 0, 0],  
    [2, 2, 1, 0, 0],  
    [3, 3, 2, 1, 0],  
    [4, 4, 3, 2, 0],  
]


if __name__ == "__main__":
    
    test_cases = [
        (-45, 1.0),   
        (-65, 3.0),  
        (-80, 6.0),   
        (-95, 10.0),  
    ]

    for rssi, dist in test_cases:
        weight = compute_weight(rssi, dist)
        print(f"RSSI: {rssi} dBm, Distance: {dist} m → Weight: {weight}")
    run_simulation()
