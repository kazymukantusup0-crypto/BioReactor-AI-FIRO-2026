def select(profiles,request):
    compatible=[p for p in profiles if p['material']==request.material and request.material_state in {'unknown',p['material_state']}]
    # A coherent single source is used, never a cross-material pooled average.
    return compatible[0] if compatible else None
