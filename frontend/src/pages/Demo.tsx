import { useState } from 'react'
import { ArrowRight, BookOpen, FlaskConical, MessageSquare, Play, Presentation, Scale, ShieldCheck, Store } from 'lucide-react'
import { api } from '../api'
import { useQuery } from '../hooks'
import { Badge, LoadState, Notice, PageTitle, Panel, Reply } from '../ui'
import FiroDemoMvp from './FiroDemoMvp'
import { tr } from '../i18n'

export default function Demo({ navigate }: { navigate: (page: string) => void }) {
  const demo = useQuery('firo-demo', api.demo); const [recorded, setRecorded] = useState(false)
  const laboratory = () => { if (demo.data) { sessionStorage.setItem('bioreactor_laboratory_example', JSON.stringify({ input: demo.data.laboratory_example, notice: demo.data.example_notice })); navigate('prediction') } }
  const chat = () => { if (demo.data) { sessionStorage.setItem('bioreactor_demo_question', demo.data.question); navigate('chat') } }
  return <><PageTitle eyebrow={tr('demo.eyebrow')} title={tr('demo.1')} description={tr('demo.2')} action={<Badge tone="green">FIRO 2026</Badge>} /><FiroDemoMvp/><div className="demo-intro panel"><div className="demo-logo"><Presentation size={30} /></div><div><span className="eyebrow">{tr('demo.live')}</span><h2>{tr('demo.3')}</h2><p>{tr('demo.4')}</p></div></div><LoadState loading={demo.loading} error={demo.error} retry={demo.refresh} />{demo.data && <><div className="demo-steps">{[
    { icon: <FlaskConical />, title: tr('demo.5'), detail: tr('demo.6'), action: laboratory, button: tr('demo.7') },
    { icon: <MessageSquare />, title: tr('demo.8'), detail: tr('demo.9'), action: chat, button: tr('demo.10') },
    { icon: <Store />, title: tr('demo.11'), detail: tr('demo.12'), action: () => navigate('market'), button: tr('demo.13') },
    { icon: <Scale />, title: tr('demo.14'), detail: tr('demo.15'), action: () => navigate('economics'), button: tr('demo.16') },
    { icon: <BookOpen />, title: tr('demo.17'), detail: tr('demo.18'), action: () => navigate('science'), button: tr('demo.19') },
    { icon: <ShieldCheck />, title: tr('demo.20'), detail: tr('demo.21'), action: () => navigate('system'), button: tr('demo.22') },
  ].map((step, index) => <Panel className="demo-step" key={step.title}><div className="demo-step-number">0{index + 1}</div><span className="demo-step-icon">{step.icon}</span><h2>{step.title}</h2><p>{step.detail}</p><button className="text-button" onClick={step.action}>{step.button}<ArrowRight size={15} /></button></Panel>)}</div><Panel title={tr('demo.23')} subtitle={tr('demo.24', { v0: demo.data.recorded_at })} action={<Badge tone="amber">{tr('demo.recorded')}</Badge>}><Notice tone="muted">{tr('demo.25')}</Notice><button className="btn btn-secondary" onClick={() => setRecorded(v => !v)}><Play size={15} />{recorded ? tr('demo.26') : tr('demo.27')}</button>{recorded && <div className="recorded-transcript"><Badge tone="amber">{tr('demo.28')}</Badge><h3>{demo.data.transcript.question}</h3><Reply reply={demo.data.transcript.reply} /></div>}</Panel></>}</>
}
