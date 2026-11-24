import { useEffect, useRef, useState } from 'react'
import { ExternalLink, Leaf, LoaderCircle, RefreshCw, TrendingUp, Zap } from 'lucide-react'
import { api } from '../api'
import { useQuery } from '../hooks'
import { MarketChart, seriesKey } from '../MarketChart'
import { Badge, categories, commodityNames, date, Empty, JsonDetails, LoadState, Notice, number, PageTitle, Panel, PriceStatus, regionName, timestamp } from '../ui'
import { tr } from '../i18n'
import { useDisplayMode } from '../DisplayMode'

// «household_tier1_electric_stove_statistics · VAT_included · tariff» -> «население · с НДС · тариф».
// The raw codes stay visible in the «Научный» view.
function priceLabel(price: { consumer_class?: string | null; tax_basis?: string | null; price_type?: string | null }) {
  const who = !price.consumer_class ? '' : price.consumer_class.startsWith('household') ? tr('market2.household') : price.consumer_class.startsWith('non_household') ? tr('market2.business') : ''
  const tax = price.tax_basis === 'VAT_included' ? tr('market2.vatIncluded') : price.tax_basis === 'VAT_excluded' ? tr('market2.vatExcluded') : price.tax_basis === 'statistics_as_published' ? tr('market2.statistics') : ''
  const type = price.price_type === 'tariff' ? tr('market2.tariff') : price.price_type === 'reference' ? tr('market2.reference') : ''
  return [who, tax, type].filter(Boolean).join(' · ')
}

export default function Market({ onChange }: { onChange: () => void }) {
  const scientific = useDisplayMode().mode === 'scientific'
  const [region, setRegion] = useState('KZ-Karaganda'); const [category, setCategory] = useState('electricity'); const [commodity, setCommodity] = useState('electricity')
  const catalog = useQuery('catalog', api.catalog)
  const prices = useQuery('prices-' + region, signal => api.prices(region, signal))
  const sources = useQuery('source-states', api.sources)
  const history = useQuery('history-' + commodity + region, signal => api.history(commodity, region, signal))
  const changes = useQuery('changes-' + commodity + region, signal => api.changes(commodity, region, signal))
  const [selectedKey, setSelectedKey] = useState(''); const [busy, setBusy] = useState(false); const [updateMessage, setUpdateMessage] = useState(''); const [error, setError] = useState(''); const lock = useRef(false)
  const series = [...new Map((history.data?.prices ?? []).map(p => [seriesKey(p), p])).values()]
  const chosen = series.find(p => seriesKey(p) === selectedKey) ?? series.find(p => p.price_type === 'reference') ?? series[0]
  const chartRows = history.data?.prices.filter(p => chosen && seriesKey(p) === seriesKey(chosen)) ?? []
  const change = changes.data?.series.find(p => chosen && p.source_id === chosen.source_id && p.consumer_class === chosen.consumer_class && p.tax_basis === chosen.tax_basis && p.price_type === chosen.price_type)
  useEffect(() => { setSelectedKey('') }, [region, commodity])
  const chooseCategory = (value: string) => {
    setCategory(value)
    setCommodity(catalog.data?.commodities.find(c => c.category === value)?.id ?? ({ natural_gas: 'natural_gas', organic_fertilizer: 'digestate', mineral_fertilizer: 'urea', organic_feedstock: 'food_waste', electricity: 'electricity' }[value] ?? 'electricity'))
  }
  const update = async () => {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setUpdateMessage('')
    try {
      const result = await api.update(category)
      setUpdateMessage(tr('market.1', { v0: result.inserted }) + result.sources.map(s => `${s.source}: ${s.status}${s.error ? ' — ' + s.error : ''}`).join('; '))
      prices.refresh(); sources.refresh(); history.refresh(); changes.refresh(); onChange()
    } catch (e) { setError((e as Error).message) }
    finally { lock.current = false; setBusy(false) }
  }
  const rows = prices.data?.prices.filter(p => p.category === category) ?? []
  const regionOptions = [...new Set(['KZ-Karaganda', ...(catalog.data?.regions.map(r => r.id) ?? [])])]
  return <><PageTitle eyebrow={tr('market.eyebrow')} title={tr('market.2')} description={tr('market.3')} action={<button className="btn btn-primary" disabled={busy} onClick={update}>{busy ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}{busy ? tr('market.4') : tr('market.5')}</button>} /><div className="category-tabs">{Object.entries(categories).map(([key, label]) => <button className={category === key ? 'active' : ''} onClick={() => chooseCategory(key)} key={key}>{key === 'electricity' ? <Zap size={16} /> : key.includes('fertilizer') ? <Leaf size={16} /> : <TrendingUp size={16} />}{label}<span>{prices.data?.prices.filter(p => p.category === key).length ?? '—'}</span></button>)}</div><Panel className="filter-panel"><label>{tr('market.6')}<select aria-label={tr('market.7')} value={region} onChange={e => setRegion(e.target.value)}>{regionOptions.map(r => <option key={r} value={r}>{regionName(r)}</option>)}</select></label><label>{tr('market.8')}<select aria-label={tr('market.8')} value={commodity} onChange={e => setCommodity(e.target.value)}>{catalog.data?.commodities.filter(c => c.category === category).map(c => <option key={c.id} value={c.id}>{commodityNames[c.id] ?? c.name}</option>)}</select></label><div className="filter-note"><Badge tone="cyan">{tr('market.9')}</Badge><small>{tr('market.10')}</small></div></Panel>{region === 'KZ-national' && <Notice>{tr('market.11')}</Notice>}<LoadState loading={prices.loading || catalog.loading} error={error || prices.error || catalog.error} retry={prices.refresh} />{updateMessage && <Notice tone="cyan">{updateMessage} {tr('market.12')}</Notice>}<Panel title={categories[category]} subtitle={tr('market.13', { v0: regionName(region) })} action={<Badge>{rows.length} {tr('market.14')}</Badge>}>{rows.length ? <div className="table-scroll"><table className="market-table"><thead><tr><th>{tr('market.15')}</th><th>{tr('market.16')}</th><th>{tr('market.17')}</th><th>{tr('market.18')}</th><th>{tr('market.19')}</th></tr></thead><tbody>{rows.map(price => <tr key={price.id}><td><strong>{commodityNames[price.commodity] ?? price.commodity}</strong><small>{priceLabel(price)}</small>{scientific && <small className="market-codes">{price.consumer_class} · {price.tax_basis} · {price.price_type}</small>}</td><td className="price-cell">{number(price.normalized_value)}<small>{price.currency}/{price.normalized_unit}</small></td><td><PriceStatus price={price} />{price.price_type === 'reference' && <small>{tr('market.20')}</small>}</td><td><strong>{date(price.effective_from)}</strong><small>{tr('market.21')} {date(price.published_at)}</small><small>{tr('market.22')} {price.age_days} {tr('market.23')}</small></td><td><a className="source-link" href={price.source_url} target="_blank" rel="noreferrer">{price.source_name}<ExternalLink size={13} /></a><small>{regionName(price.region)}</small><details className="table-details"><summary>{tr('market.24')}</summary><p>{price.evidence}</p><p>{tr('market.25')} {timestamp(price.received_at)}</p></details></td></tr>)}</tbody></table></div> : !prices.loading && <Empty icon={<Leaf size={30} />} title={tr('market.26')}>{tr('market.27')}</Empty>}</Panel><div className="market-bottom"><Panel title={tr('market.28')} subtitle={tr('market.29')}><LoadState loading={history.loading} error={history.error} retry={history.refresh} />{series.length > 0 && <select className="series-select" aria-label={tr('market.30')} value={chosen ? seriesKey(chosen) : ''} onChange={e => setSelectedKey(e.target.value)}>{series.map(p => <option key={seriesKey(p)} value={seriesKey(p)}>{p.source_name} · {priceLabel(p)}</option>)}</select>}{!history.loading && <MarketChart prices={chartRows} />}{chosen && <div className="chart-footnote">{chosen.price_type === 'reference' ? tr('market.31') : tr('market.32')} · {chosen.currency}/{chosen.normalized_unit} · {priceLabel(chosen)}</div>}{history.data?.truncated && <Notice>{tr('market.33')}</Notice>}</Panel><Panel title={tr('market.34')} subtitle={tr('market.35')}><div className="period-changes">{['7', '30', '90'].map(days => <div key={days}><span>{days} {tr('market.36')}</span><strong>{change?.windows_days[days]?.percent_change !== null && change?.windows_days[days]?.percent_change !== undefined ? number(change.windows_days[days].percent_change) + '%' : '—'}</strong><small>{change?.windows_days[days]?.status === 'ok' ? tr('market.37') : tr('market.38')}</small></div>)}</div><Notice tone="muted">{tr('market.39')}</Notice><div className="source-update-list"><h3>{tr('market.40')}</h3>{sources.data?.states.filter(s => rows.some(p => p.source_id === s.source_id)).map(source => <div key={source.source_id}><span>{source.source_id}</span><strong>{timestamp(source.last_success_at)}</strong><small>{source.last_status}{source.last_error ? ' · ' + source.last_error : ''}</small></div>)}</div><LoadState loading={sources.loading} error={sources.error || changes.error} />{change && <JsonDetails value={change} title={tr('market.41')} />}</Panel></div></>
}
