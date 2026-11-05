def citations(profile,energy=None):
    source=profile['source']
    rows=[{**source,'locators':{k:v['locator'] for k,v in profile['values'].items()}}]
    if energy:rows.append(energy)
    return rows
