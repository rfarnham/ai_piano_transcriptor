def label_ottava(events, mode, trigger_threshold, release_threshold, min_duration=1.5, min_notes=3):
    """Identify which events should be rendered under an ottava bracket.
    
    Uses hysteresis thresholds to prevent rapid on/off flickering of brackets.
    
    Args:
        events (list): List of events (offset, pitches, duration, grid).
        mode (str): '8va' (shifting up) or '8vb' (shifting down).
        trigger_threshold (int): MIDI pitch that triggers the bracket.
        release_threshold (int): MIDI pitch that releases the bracket.
        min_duration (float): Minimum duration in beats for a bracket to form.
        min_notes (int): Minimum number of notes in a cluster for a bracket to form.
        
    Returns:
        list of bool: Boolean flags indicating if the corresponding event is inside the bracket.
    """
    MAX_GAP = 3.0
    
    if mode == '8va':
        high_indices = [i for i, (_, pitches, _, _) in enumerate(events)
                        if pitches and any(p >= trigger_threshold for p in pitches) and min(pitches) >= release_threshold]
    elif mode == '8vb':
        high_indices = [i for i, (_, pitches, _, _) in enumerate(events)
                        if pitches and any(p <= trigger_threshold for p in pitches) and max(pitches) <= release_threshold]
    else:
        return [False] * len(events)
        
    if not high_indices:
        return [False] * len(events)
        
    # Group indices into continuous clusters separated by at most MAX_GAP beats
    clusters = []
    current_cluster = [high_indices[0]]
    for idx in high_indices[1:]:
        prev_idx = current_cluster[-1]
        prev_offset = events[prev_idx][0]
        curr_offset = events[idx][0]
        
        if mode == '8va':
            safe = all(not events[k][1] or min(events[k][1]) >= release_threshold for k in range(prev_idx + 1, idx))
        else:
            safe = all(not events[k][1] or max(events[k][1]) <= release_threshold for k in range(prev_idx + 1, idx))
            
        if curr_offset - prev_offset <= MAX_GAP and safe:
            current_cluster.append(idx)
        else:
            clusters.append(current_cluster)
            current_cluster = [idx]
    if current_cluster:
        clusters.append(current_cluster)
        
    # Filter clusters by duration or size
    valid_clusters = []
    for cluster in clusters:
        first_idx = cluster[0]
        last_idx = cluster[-1]
        first_offset = events[first_idx][0]
        last_offset = events[last_idx][0]
        
        cluster_duration = last_offset - first_offset
        num_high_notes = len(cluster)
        
        if cluster_duration >= min_duration or num_high_notes >= min_notes:
            valid_clusters.append(cluster)
            
    # Mark and expand valid clusters
    use_ottava = [False] * len(events)
    for cluster in valid_clusters:
        first_idx = cluster[0]
        last_idx = cluster[-1]
        
        # Expand left to nearby notes that are above release threshold
        left_idx = first_idx
        while left_idx > 0:
            candidate_idx = left_idx - 1
            cand_offset, cand_pitches, _, _ = events[candidate_idx]
            curr_offset = events[left_idx][0]
            
            if curr_offset - cand_offset <= 1.0:
                if mode == '8va':
                    ok = not cand_pitches or min(cand_pitches) >= release_threshold
                else:
                    ok = not cand_pitches or max(cand_pitches) <= release_threshold
                if ok:
                    left_idx = candidate_idx
                else:
                    break
            else:
                break
                
        # Expand right to nearby notes that are above release threshold
        right_idx = last_idx
        while right_idx < len(events) - 1:
            candidate_idx = right_idx + 1
            cand_offset, cand_pitches, _, _ = events[candidate_idx]
            curr_offset = events[right_idx][0]
            
            if cand_offset - curr_offset <= 1.0:
                if mode == '8va':
                    ok = not cand_pitches or min(cand_pitches) >= release_threshold
                else:
                    ok = not cand_pitches or max(cand_pitches) <= release_threshold
                if ok:
                    right_idx = candidate_idx
                else:
                    break
            else:
                break
                
        for idx in range(left_idx, right_idx + 1):
            use_ottava[idx] = True
            
    return use_ottava
