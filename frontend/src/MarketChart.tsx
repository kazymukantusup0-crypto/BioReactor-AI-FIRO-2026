import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Price } from './types'
import { date, Empty, number } from './ui'
import { tr } from './i18n'
import { chartColors } from './theme'

export const seriesKey = (price: Price) => [price.source_id, price.commodity, price.region, price.currency, price.normalized_unit, price.consumer_class, price.tax_basis, price.price_type, price.gas_volume_basis].join('|')
export function MarketChart({ prices, compact = false }: { prices: Price[]; compact?: boolean }) {
  if (prices.length < 2) return <Empty title={tr('marketChart.1')}>{tr('marketChart.2')}</Empty>
  const data = [...prices].sort((a, b) => a.effective_from.localeCompare(b.effective_from) || a.id - b.id).map(p => ({ date: p.effective_from, value: Number(p.normalized_value) }))
  const c = chartColors()
  return <div className={`chart ${compact ? 'chart-compact' : ''}`} data-testid="market-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 20, right: 20, bottom: 0, left: -15 }}><CartesianGrid stroke={c.grid} strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" tickFormatter={v => date(String(v)).slice(0, 5)} axisLine={false} tickLine={false} tick={{ fill: c.tick, fontSize: 13, fontFamily: c.fontFamily }} dy={10} /><YAxis domain={['auto', 'auto']} tick={{ fill: c.tick, fontSize: 13, fontFamily: c.fontFamily }} axisLine={false} tickLine={false} tickFormatter={v => number(v)} /><Tooltip contentStyle={{ background: c.tooltipBg, border: `1px solid ${c.tooltipBorder}`, borderRadius: 10, color: c.tooltipText }} labelFormatter={v => date(String(v))} formatter={value => [number(String(value)) + ' ' + prices[0].currency + '/' + prices[0].normalized_unit, tr('marketChart.3')]} /><Line type="linear" dataKey="value" stroke={c.line} strokeWidth={2.5} dot={{ r: 4, fill: c.surface, strokeWidth: 2 }} activeDot={{ r: 6 }} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
}
