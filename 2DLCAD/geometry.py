import math

EPS = 1e-9

def line_intersection(p1, p2, p3, p4):
    """
    Find intersection between Line1 (p1->p2) and Line2 (p3->p4).
    Returns (ix, iy, t, u) where:
      - ix, iy is the intersection point
      - t is parameter on Line1 (0..1 if within segment)
      - u is parameter on Line2 (0..1 if within segment)
    Returns None if parallel.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    
    denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
    if abs(denom) < EPS:
        return None  # Parallel
        
    ua = ((x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)) / denom
    ub = ((x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)) / denom
    
    ix = x1 + ua * (x2 - x1)
    iy = y1 + ua * (y2 - y1)
    
    return ix, iy, ua, ub

def get_intersections_on_line(target_line, other_lines):
    """
    Returns a list of (t, x, y) for all intersections on 'target_line'
    caused by 'other_lines'.
    Only considers intersections where the crossing lines actually touch/cross within their segments.
    (i.e. 0 <= u <= 1 for the other line).
    Depending on needs, we might want 0 <= t <= 1 or allow infinite line for extend.
    For Trim, we need points ON the target line.
    """
    intersections = []
    
    p1 = (target_line.x1, target_line.y1)
    p2 = (target_line.x2, target_line.y2)
    
    for other in other_lines:
        if other is target_line:
            continue
            
        p3 = (other.x1, other.y1)
        p4 = (other.x2, other.y2)
        
        res = line_intersection(p1, p2, p3, p4)
        if res:
            ix, iy, t, u = res
            # For trim: The 'cutter' (other line) must physically exist at the crossing point.
            if -EPS <= u <= 1.0 + EPS:
                # We store t parameter to sort them along the target line
                intersections.append((t, ix, iy))
                
    # Sort by 't'
    intersections.sort(key=lambda x: x[0])
    return intersections
