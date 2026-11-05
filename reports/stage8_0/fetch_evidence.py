import main,json,hashlib
import requests,fitz
from src.data.prepare import ROOT
out=ROOT/'reports/stage8_0/sources';out.mkdir(exist_ok=True)
items={'alberta2005':('https://www1.agric.gov.ab.ca/$department/deptdocs.nsf/all/agdex8875/$file/400_27-1.pdf?OpenElement=',[9]),'alberta_nmp':('https://www1.agriculture.alberta.ca/$department/deptdocs.nsf/all/epw11920/$FILE/6-1.pdf',[11]),'monch2013':('https://cigrjournal.org/index.php/Ejounral/article/download/2445/1736/8047',[4,6,7]),'pham2013':('https://pdfs.semanticscholar.org/11ec/6cf5527fb8cd3d44f99641d82ec645b15b8f.pdf',[2,4])}
audit=[]
for key,(url,pages) in items.items():
 try:
  response=requests.get(url,timeout=20);row={'id':key,'url':url,'status':response.status_code,'final_url':response.url}
  if response.status_code==200 and response.content.startswith(b'%PDF'):
   path=out/(key+'.pdf');path.write_bytes(response.content);doc=fitz.open(path);row['sha256']=hashlib.sha256(response.content).hexdigest();row['pages']=len(doc)
   (out/(key+'.txt')).write_text('\n'.join(p.get_text() for p in doc),encoding='utf-8')
   for p in pages:doc[p].get_pixmap(matrix=fitz.Matrix(1.4,1.4)).save(out/(key+'_'+str(p)+'.png'))
  audit.append(row)
 except Exception as e:audit.append({'id':key,'url':url,'error':type(e).__name__+': '+str(e)})
 print(audit[-1],flush=True)
(out/'access.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
