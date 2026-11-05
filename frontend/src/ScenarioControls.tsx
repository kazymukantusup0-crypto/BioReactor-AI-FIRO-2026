import type { AdvisorDecision } from './advisorApi'

export default function ScenarioControls({ value, onChange, region }: { value: AdvisorDecision; onChange: (value: AdvisorDecision) => void; region: string }) {
  const reactor = value.reactor ?? {}
  const edit = (key: string, v: unknown) => onChange({ ...value, [key]: v })
  const editReactor = (key: string, v: unknown) => edit('reactor', { ...reactor, [key]: v })
  const costs = (value.costs ?? {}) as Record<string, { low: number; high: number }>
  const point = (v: number) => ({ low: v, high: v, provenance: 'USER_REPORTED', evidence: 'Explicit Dashboard scenario input; not independently measured' })
  const quotes = (value.quotes ?? {}) as Record<string, Record<string, unknown>>
  const quote = quotes.electricity ?? {}
  const quoteEdit = (key: string, v: unknown) => edit('quotes', { ...quotes, electricity: { commodity: 'electricity', unit: 'KZT/kWh', currency: 'KZT', source: 'Пользовательский сценарий', ...quote, region, [key]: v } })
  return <details className="advisor-reactor"><summary>Загрузка, энергия и затраты партии</summary>
    <p>Пустое поле означает неизвестное значение. Ноль вводите только для действительно отсутствующей статьи. КПД и извлечение — сценарные параметры, не измерения установки.</p>
    <div className="advisor-input-grid">
      {Object.entries({ dilution_water_l: 'Добавленная вода, л', headspace_l: 'Требуемое газовое пространство, л', resident_liquid_volume_l: 'Остаток в реакторе, л', temperature_c: 'Температура процесса, °C', initial_temperature_c: 'Начальная температура, °C', ambient_temperature_c: 'Температура окружающей среды, °C', heated_mass_kg: 'Полная нагреваемая масса, кг', heat_capacity_kj_kg_k: 'Теплоёмкость, кДж/(кг·К)', heat_loss_coefficient_w_k: 'Теплопотери UA, Вт/К', duration_days: 'Продолжительность сценария, суток', heater_efficiency: 'КПД нагревателя, 0–1', auxiliary_energy_kwh: 'Смешивание и прочее потребление, кВт·ч' }).map(([key, label]) =>
        <label key={key}>{label}<input type="number" step="any" value={reactor[key] == null ? '' : String(reactor[key])} onChange={e => editReactor(key, e.target.value === '' ? undefined : Number(e.target.value))} /></label>)}
      <label>Источник нагрева<select value={String(reactor.heating_carrier ?? '')} onChange={e => editReactor('heating_carrier', e.target.value || undefined)}><option value="">Не задан</option><option value="electricity">Электричество</option><option value="process_heat">Тепло произведённого газа</option><option value="external_heat">Внешнее тепло</option></select></label>
      <label>Использование газа<select value={String(value.gas_use ?? 'unknown')} onChange={e => edit('gas_use', e.target.value)}><option value="unknown">Сравнить доступные варианты</option><option value="heat">Тепло</option><option value="electricity">Электричество</option><option value="chp">Когенерация</option><option value="sell_gas">Продажа газа</option></select></label>
      {Object.entries({ recovery_fraction: 'Извлечение потенциала, 0–1', thermal_efficiency: 'КПД получения тепла, 0–1', electrical_efficiency: 'КПД электричества, 0–1', methane_fraction: 'Доля метана в биогазе, 0–1' }).map(([key, label]) => <label key={key}>{label}<input type="number" min="0" max="1" step="any" value={(value[key] as { low?: number } | undefined)?.low ?? ''} onChange={e => edit(key, e.target.value === '' ? undefined : point(Number(e.target.value)))} /></label>)}
      {Object.entries({ preparation: 'Подготовка', maintenance: 'Обслуживание', storage: 'Хранение', transport: 'Транспорт', gas_cleaning: 'Очистка газа', digestate_handling: 'Обращение с дигестатом', packaging: 'Упаковка' }).map(([key, label]) => <label key={key}>{label}, KZT/партию<input type="number" min="0" step="any" value={costs[key]?.low ?? ''} onChange={e => edit('costs', { ...costs, [key]: e.target.value === '' ? undefined : point(Number(e.target.value)) })} /></label>)}
    </div>
    <label className="advisor-checkbox"><input type="checkbox" checked={reactor.energy_scope === 'entire_batch'} onChange={e => editReactor('energy_scope', e.target.checked ? 'entire_batch' : undefined)} />Нагрев, продолжительность и энергозатраты относятся ко всей партии</label>
    <label className="advisor-checkbox"><input type="checkbox" checked={value.all_operating_costs_included === true} onChange={e => edit('all_operating_costs_included', e.target.checked)} />Все эксплуатационные статьи учтены; отсутствующие статьи явно указаны нулём</label>
    <label className="advisor-checkbox"><input type="checkbox" checked={value.assume_full_self_consumption === true} onChange={e => edit('assume_full_self_consumption', e.target.checked)} />Условно использовать всю полезную энергию для собственных нужд</label>
    <label className="advisor-checkbox"><input type="checkbox" checked={value.replacement_heat_source === 'electric_resistance'} onChange={e => edit('replacement_heat_source', e.target.checked ? 'electric_resistance' : 'unknown')} />Сравнить тепло с электрическим сопротивительным нагревом</label>
    <details><summary>Свой тариф электричества · необязательно</summary><p>Чтобы использовать свою цену, заполните значение, дату и класс потребителя. Без этих сведений цена не применяется. Регион цены: {region}.</p><div className="advisor-input-grid">
      <label>Цена, KZT/кВт·ч<input type="number" min="0" step="any" value={quote.value == null ? '' : String(quote.value)} onChange={e => { if (e.target.value === '') { const rest = { ...quotes }; delete rest.electricity; edit('quotes', rest) } else quoteEdit('value', Number(e.target.value)) }} /></label>
      <label>Дата цены<input type="date" disabled={quote.value == null} value={String(quote.published_at ?? '')} onChange={e => quoteEdit('published_at', e.target.value || undefined)} /></label>
      <label>Источник цены<input disabled={quote.value == null} value={String(quote.source ?? '')} onChange={e => quoteEdit('source', e.target.value)} /></label>
      <label>Класс потребителя<input disabled={quote.value == null} placeholder="Класс из вашего тарифа" value={String(value.consumer_class ?? '')} onChange={e => onChange({ ...value, consumer_class: e.target.value || undefined, quotes: { ...quotes, electricity: { ...quote, consumer_class: e.target.value || undefined } } })} /></label>
    </div><label className="advisor-checkbox"><input type="checkbox" disabled={quote.value == null} checked={quote.confirmed === true} onChange={e => quoteEdit('confirmed', e.target.checked)} />Цена и применимость тарифа подтверждены мной</label></details>
    <p>Если своя цена не задана, используются сохранённые наблюдения с датой и регионом. Стоимость сырого биогаза не приравнивается к природному газу.</p>
  </details>
}
