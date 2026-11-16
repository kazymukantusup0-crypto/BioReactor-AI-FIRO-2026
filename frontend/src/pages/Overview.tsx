import { ArrowRight, MessageSquare, Layers, Radio } from 'lucide-react'
import { useEffect } from 'react'
import { api } from '../api'
import { useQuery } from '../hooks'
import { LoadState, PriceStatus, number } from '../ui'
import { tr } from '../i18n'
export default function Overview({navigate}:{navigate:(page:string)=>void}){
const prices=useQuery('home-prices',signal=>api.prices('KZ-Karaganda',signal))
useEffect(()=>{const timer=setInterval(prices.refresh,60000);return()=>clearInterval(timer)},[prices.refresh])
return <div className="clean-home"><div className="clean-intro"><h1>{tr('overview.1')}</h1><p>{tr('overview.2')}</p></div><div className="home-actions"><button className="home-action" onClick={()=>navigate('substrates')}><Layers size={25}/><h2>{tr('overview.3')}</h2><p>{tr('overview.4')}</p><ArrowRight size={17}/></button><button className="home-action" onClick={()=>navigate('chat')}><MessageSquare size={25}/><h2>{tr('overview.5')}</h2><p>{tr('overview.6')}</p><ArrowRight size={17}/></button></div><div className="home-status"><Radio size={19}/><span>{tr('overview.7')}</span><button className="text-button" onClick={()=>navigate('reactor')}>{tr('overview.8')}</button></div>{<section className="home-market"><h2>{tr('overview.9')}</h2><LoadState loading={prices.loading} error={prices.error} retry={prices.refresh}/>{prices.data?.prices.slice(0,3).map(p=><div className="home-market-row" key={p.id}><span>{p.commodity==='electricity'?tr('overview.10'):tr('overview.11')}<small>{p.price_type==='reference'?tr('overview.12'):tr('overview.13')} · {p.region}</small></span><span>{number(p.normalized_value)} {p.normalized_unit.includes(p.currency)?p.normalized_unit:p.currency+'/'+p.normalized_unit}<PriceStatus price={p}/></span></div>)}<button className="text-button" onClick={()=>navigate('market')}>{tr('overview.14')} <ArrowRight size={14}/></button></section>}</div>
}
