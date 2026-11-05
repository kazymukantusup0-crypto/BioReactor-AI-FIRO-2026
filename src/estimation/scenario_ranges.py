def point(value):return {'low':value,'high':value}
def multiply(a,b):return {'low':a['low']*b['low'],'high':a['high']*b['high']}
def scale(a,factor):return {'low':a['low']*factor,'high':a['high']*factor}
def sensitivity(vs,bmp):
    midvs=(vs['low']+vs['high'])/2;midbmp=(bmp['low']+bmp['high'])/2
    return {'vary_VS_only_m3':scale(vs,midbmp/1000),'vary_BMP_only_m3':scale(bmp,midvs/1000),
            'method':'One factor at a time around arithmetic midpoint; no probabilities assigned'}
