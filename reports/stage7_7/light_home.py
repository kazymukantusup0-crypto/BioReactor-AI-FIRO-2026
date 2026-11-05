from pathlib import Path
p=Path('frontend/src/api.ts');s=p.read_text(encoding='utf-8').replace('export const api = {',"export const api = {\n  health: (signal?: AbortSignal) => request<{status:string}>('/health', {signal}),");p.write_text(s,encoding='utf-8')
p=Path('frontend/src/App.tsx');s=p.read_text(encoding='utf-8').replace("const overview = useQuery('app-overview', api.overview)","const health = useQuery('app-health', api.health)").replace('overview.refresh','health.refresh').replace('overview.data?.system','health.data').replace('overview.error','health.error').replace('<Overview {...overview} navigate={navigate} />','<Overview navigate={navigate} />').replace('FastAPI подключён','Подключено').replace('Scientific Machine Learning System','Локальный ассистент по биогазу');p.write_text(s,encoding='utf-8')
p=Path('frontend/src/pages/Overview.tsx');s=p.read_text(encoding='utf-8').replace("import type { Overview as OverviewData } from '../types'","import { useEffect } from 'react'\nimport { api } from '../api'\nimport { useQuery } from '../hooks'")
start=s.index('export default function Overview(');end=s.index('return <div',start)
s=s[:start]+"""export default function Overview({navigate}:{navigate:(page:string)=>void}){
const prices=useQuery('home-prices',signal=>api.prices('KZ-Karaganda',signal))
useEffect(()=>{const timer=setInterval(prices.refresh,60000);return()=>clearInterval(timer)},[prices.refresh])
"""+s[end:]
s=s.replace('<LoadState loading={loading&&!data} error={error} retry={refresh}/>','').replace('{data&&<section','{<section').replace('{data.market_prices.slice(0,3).map(p=>','{prices.data?.prices.slice(0,3).map(p=>').replace('<h2>Цены для вашего сравнения</h2>','<h2>Цены для вашего сравнения</h2><LoadState loading={prices.loading} error={prices.error} retry={prices.refresh}/>')
s=s.replace("{p.currency}/{p.normalized_unit}","{p.normalized_unit.includes(p.currency)?p.normalized_unit:p.currency+'/'+p.normalized_unit}")
p.write_text(s,encoding='utf-8')
