import main,requests,fitz,json,hashlib
from src.data.prepare import ROOT
out=ROOT/'reports/stage8_1/sources';out.mkdir(exist_ok=True)
items={'wedwitschka2020':('https://pdfs.semanticscholar.org/f447/e85c63c088ca698e9513407cbbe5f23d9c7d.pdf',[5,6,11]),'eftaxias2024':('https://pdfs.semanticscholar.org/d80d/aff8cb9be2d3f88f64471a7656ff12ceec8a.pdf',[2,4])}
audit=[]
for key,(url,pages) in items.items():
 try:
  r=requests.get(url,timeout=20);row={'id':key,'url':url,'status':r.status_code,'final_url':r.url}
  if r.status_code==200 and r.content.startswith(b'%PDF'):
   p=out/(key+'.pdf');p.write_bytes(r.content);doc=fitz.open(p);row['sha256']=hashlib.sha256(r.content).hexdigest();row['pages']=len(doc)
   (out/(key+'.txt')).write_text('\n'.join(page.get_text() for page in doc),encoding='utf-8')
   for n in pages:doc[n].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(out/(key+'_'+str(n)+'.png'))
  audit.append(row)
 except Exception as exc:audit.append({'id':key,'url':url,'error':type(exc).__name__+': '+str(exc)})
 print(audit[-1],flush=True)
(out/'researcher_access.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
