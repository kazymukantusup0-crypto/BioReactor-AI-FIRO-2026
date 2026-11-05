import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Price } from './types'
import { date, Empty, number } from './ui'

export const seriesKey = (price: Price) => [price.source_id, price.commodity, price.region, price.currency, price.normalized_unit, price.consumer_class, price.tax_basis, price.price_type, price.gas_volume_basis].join('|')
export function MarketChart({ prices, compact = false }: { prices: Price[]; compact?: boolean }) {
  if (prices.length < 2) return <Empty title="Недостаточно истории">График появится после получения двух сопоставимых датированных наблюдений.</Empty>
  const data = [...prices].sort((a, b) => a.effective_from.localeCompare(b.effective_from) || a.id - b.id).map(p => ({ date: p.effective_from, value: Number(p.normalized_value) }))
  return <div className={`chart ${compact ? 'chart-compact' : ''}`} data-testid="market-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 20, right: 20, bottom: 0, left: -15 }}><CartesianGrid stroke="#24333b" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="date" tickFormatter={v => date(String(v)).slice(0, 5)} axisLine={false} tickLine={false} tick={{ fill: '#91a6ae', fontSize: 11 }} dy={10} /><YAxis domain={['auto', 'auto']} tick={{ fill: '#91a6ae', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => number(v)} /><Tooltip contentStyle={{ background: '#132129', border: '1px solid #2b414b', borderRadius: 10, color: '#edf6f5' }} labelFormatter={v => date(String(v))} formatter={value => [number(String(value)) + ' ' + prices[0].currency + '/' + prices[0].normalized_unit, 'Наблюдение']} /><Line type="linear" dataKey="value" stroke="#55d6af" strokeWidth={2.5} dot={{ r: 4, fill: '#0c171d', strokeWidth: 2 }} activeDot={{ r: 6 }} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
}
