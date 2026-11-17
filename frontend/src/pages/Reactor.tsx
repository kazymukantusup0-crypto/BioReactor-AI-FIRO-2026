import { ArrowRight, Bot, Cable, Cpu, Gauge, Laptop, LayoutDashboard, LockKeyhole, PlugZap, Thermometer, Wrench } from 'lucide-react'
import { motion } from 'motion/react'
import { api } from '../api'
import { useQuery } from '../hooks'
import { Badge, JsonDetails, LoadState, Notice } from '../ui'
import { serverText, tr } from '../i18n'

export function ReactorDiagram({ compact = false, step = -1 }: { compact?: boolean; step?: number }) {
  return <div className={`reactor-diagram ${compact ? 'compact' : ''}`} aria-label={tr('reactor.1')}><svg viewBox="0 0 380 280" role="img"><defs><linearGradient id={compact ? 'tankSmall' : 'tankLarge'} x1="0" y1="0" x2="1" y2="1"><stop stopColor="#24433d" stopOpacity=".7" /><stop offset="1" stopColor="#10231f" stopOpacity=".2" /></linearGradient><pattern id={compact ? 'gridSmall' : 'gridLarge'} width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#28483d" strokeWidth=".4" /></pattern></defs><rect width="380" height="280" fill={`url(#${compact ? 'gridSmall' : 'gridLarge'})`} opacity=".35" /><g fill="none" stroke="#4e746b" strokeWidth="1.5"><path d="M140 65V43h40v-9M210 43h45v48h50" strokeDasharray="4 5" /><path d="M94 166H55v35h-25M250 184h45v44h55" strokeDasharray="4 5" /><path d="M152 222v28m72-28v28M143 250h18m54 0h18" /><rect x="113" y="78" width="143" height="145" rx="24" fill={`url(#${compact ? 'tankSmall' : 'tankLarge'})`} /><ellipse cx="184" cy="80" rx="71" ry="18" fill="#142a25" /><ellipse cx="184" cy="222" rx="64" ry="12" /><path d="M113 162c30-8 41 10 71 0s41 8 72 0" stroke="#5bd5aa" opacity=".6" /><path d="M184 62v107m-23-14 23 14 23-14m-46 26 23-12 23 12" /><rect x="163" y="39" width="42" height="25" rx="6" fill="#1b3730" /><path d="M123 204h122" opacity=".4" /></g><g fill="#85cbb4"><circle cx="142" cy="126" r="3" opacity=".45" /><circle cx="225" cy="141" r="2" opacity=".35" /><circle cx="214" cy="111" r="3" opacity=".25" /></g><g fontFamily="ui-monospace, monospace" fontSize="13" fill="#9db8b0"><text x="10" y="126">{tr('reactor.tempPh')}</text><path d="M82 124h30" stroke="#4d7567" strokeDasharray="3 3" /><text x="270" y="82">{tr('reactor.gasOut')}</text><text x="250" y="253">{tr('reactor.digestate')}</text><text x="130" y="272">{tr('reactor.offline')}</text></g>{step >= 0 && <circle cx={[80, 165, 275, 310, 184][step]} cy={[124, 50, 91, 228, 169][step]} r="8" fill="#61dfb7" opacity=".7" />}</svg></div>
}

// Today: no sensors. Tomorrow temperature and gas sensors arrive — this page becomes the main live view.
const CHAIN = () => [
  { icon: Gauge, title: tr('reactor2.chain.reactor'), text: tr('reactor2.chain.reactorText') },
  { icon: Thermometer, title: tr('reactor2.chain.sensors'), text: tr('reactor2.chain.sensorsText') },
  { icon: Cpu, title: tr('reactor2.chain.board'), text: tr('reactor2.chain.boardText') },
  { icon: Laptop, title: tr('reactor2.chain.laptop'), text: tr('reactor2.chain.laptopText') },
  { icon: LayoutDashboard, title: tr('reactor2.chain.dashboard'), text: tr('reactor2.chain.dashboardText') },
  { icon: Bot, title: tr('reactor2.chain.agent'), text: tr('reactor2.chain.agentText') },
]

export default function Reactor() {
  const contract = useQuery('reactor-contract', api.contract)
  return <div className="reactor-page">
    <div className="page-heading"><div><h1>{tr('reactor2.title')}</h1><p>{tr('reactor2.lead')}</p></div></div>

    <motion.section className="reactor-state ds-card" data-testid="reactor-state" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
      <div className="reactor-state-icon"><PlugZap size={30} /></div>
      <div><h2>{tr('reactor2.notConnected')}</h2><p>{tr('reactor2.notConnectedText')}</p></div>
    </motion.section>

    <div className="reactor-readings">
      {[{ icon: Thermometer, title: tr('reactor2.temp'), unit: '°C' }, { icon: Gauge, title: tr('reactor2.gas'), unit: tr('farm.unit.L') }].map((item, index) =>
        <motion.article key={item.title} className="reactor-reading ds-card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25, delay: .08 + index * .05 }}>
          <span className="farm-card-title"><item.icon size={18} />{item.title}</span>
          <strong className="farm-card-value">— <small>{item.unit}</small></strong>
          <span className="farm-card-note">{tr('reactor2.waiting')}</span>
        </motion.article>)}
    </div>

    <section className="reactor-chain ds-card" aria-label={tr('reactor2.chainTitle')}>
      <h2>{tr('reactor2.chainTitle')}</h2>
      <p className="ds-muted">{tr('reactor2.chainLead')}</p>
      <ol className="reactor-chain-list">
        {CHAIN().map((step, index, all) => <motion.li key={step.title} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .22, delay: .15 + index * .06 }}>
          <div className="reactor-chain-step"><step.icon size={24} /><strong>{step.title}</strong><span>{step.text}</span></div>
          {index < all.length - 1 && <ArrowRight className="reactor-chain-arrow" size={20} aria-hidden="true" />}
        </motion.li>)}
      </ol>
    </section>

    <details className="ds-collapse" data-testid="reactor-dev">
      <summary><Wrench size={15} /> {tr('reactor2.dev')}</summary>
      <p className="ds-muted">{tr('reactor.3')}</p>
      <div className="reactor-dev-grid">
        <ReactorDiagram />
        <div className="actuator-list">{[tr('reactor.24'), tr('reactor.25'), tr('reactor.26')].map(label => <div key={label}><div className="actuator-icon"><LockKeyhole size={19} /></div><div><strong>{label}</strong><p>{tr('reactor.27')}</p></div><Badge>{tr('reactor.28')}</Badge></div>)}
          <Notice tone="muted">{tr('reactor.29')}</Notice></div>
      </div>
      <h3><Cable size={15} /> {tr('reactor.32')}</h3>
      <p className="ds-muted">{tr('reactor.33')}</p>
      <LoadState loading={contract.loading} error={contract.error} retry={contract.refresh} />
      {contract.data && <><div className="contract-units">{Object.entries(contract.data.units).map(([field, unit]) => <div key={field}><code>{field}</code><span>{unit}</span></div>)}</div>
        <Notice>{serverText(contract.data.notice, 'server.contract')}</Notice><JsonDetails value={contract.data.schema} title={tr('reactor.34')} /></>}
    </details>
  </div>
}
