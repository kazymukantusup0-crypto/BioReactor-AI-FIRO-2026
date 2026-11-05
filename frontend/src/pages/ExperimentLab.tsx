import { useRef, useState } from 'react'
import { Archive, Beaker, Download, FilePlus2, FlaskConical, LoaderCircle, Save } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useQuery } from '../hooks'
import { compactValues, processApi } from '../processApi'
import type { Experiment } from '../processApi'
import { ScientificFields, ResultValue } from '../ProcessComponents'
import type { InputField } from '../ProcessComponents'
import { Badge, Empty, JsonDetails, LoadState, Notice, number, PageTitle, Panel } from '../ui'

const fields: InputField[] = [
  { name: 'name', label: 'Название эксперимента', type: 'text' }, { name: 'experiment_date', label: 'Дата эксперимента', type: 'date' },
  { name: 'material', label: 'Сырьё', type: 'text' }, { name: 'origin', label: 'Происхождение измерений', options: [['user', 'Пользовательские'], ['laboratory', 'Лабораторные']] },
  { name: 'mass_kg', label: 'Масса сырья', unit: 'кг' }, { name: 'volume_l', label: 'Объём сырья', unit: 'л' },
  { name: 'temperature_c', label: 'Температура', unit: '°C' }, { name: 'ph', label: 'pH', unit: '0–14' },
  { name: 'ts_percent', label: 'TS', unit: '% влажной массы' }, { name: 'vs_percent', label: 'VS', unit: '%' },
  { name: 'vs_basis', label: 'Основание VS', options: [['TS', 'Доля от TS'], ['fresh_mass', 'Доля от влажной массы']] }, { name: 'vs_mass_kg', label: 'Измеренная масса VS', unit: 'кг VS' },
  { name: 'duration_days', label: 'Продолжительность', unit: 'сутки' }, { name: 'gas_volume_m3', label: 'Измеренный объём биогаза', unit: 'м³ · не метан' },
  { name: 'methane_fraction', label: 'Измеренная доля CH₄', unit: 'доля 0–1' },
  { name: 'measurement_method', label: 'Метод измерения газа', type: 'text' }, { name: 'gas_volume_basis', label: 'Условия приведения газа', type: 'text', hint: 'Укажите температуру, давление и сухой/влажный газ' },
  { name:'gas_volume_kind',label:'Что означает объём газа',options:[['cumulative','Накопленный с начала опыта'],['interval','За отдельный интервал']] },
  { name:'methane_fraction_basis',label:'Как определена доля CH₄',options:[['volume_weighted','Средняя, взвешенная по объёму'],['instantaneous','Мгновенная'],['unknown','Неизвестно']] },
]
const measurementFields: InputField[] = [
  { name: 'observed_at', label: 'Время измерения', type: 'datetime-local' },
  { name: 'elapsed_days', label: 'Время от начала опыта', unit: 'сутки' },
  { name: 'temperature_c', label: 'Измеренная температура', unit: '°C' }, { name: 'ph', label: 'Измеренный pH' },
  { name: 'gas_volume_m3', label: 'Измеренный объём биогаза', unit: 'м³' }, { name: 'methane_fraction', label: 'Измеренная доля метана', unit: '0–1' },
  { name: 'measurement_method', label: 'Метод измерения', type: 'text' }, { name: 'gas_volume_basis', label: 'Условия приведения', type: 'text' },
  { name: 'gas_volume_kind', label: 'Объём газа', options: [['cumulative', 'Накопленный с начала опыта'], ['interval', 'За отдельный интервал']] },
  { name: 'methane_fraction_basis', label: 'Основание доли метана', options: [['volume_weighted', 'Средняя, взвешенная по объёму'], ['instantaneous', 'Мгновенная'], ['unknown', 'Неизвестно']] },
]
const textFields = ['name', 'experiment_date', 'material', 'origin', 'vs_basis', 'measurement_method', 'gas_volume_basis','gas_volume_kind','methane_fraction_basis']

export function measurementChartRows(rows: Record<string, unknown>[]) {
  return rows.map((row, i) => ({ name: String(row.observed_at ?? i + 1), temperature: typeof row.temperature_c === 'number' ? row.temperature_c : null, gas: typeof row.gas_volume_m3 === 'number' ? row.gas_volume_m3 : null }))
}

export default function ExperimentLab() {
  const journal = useQuery('experiment-journal', processApi.experiments)
  const [selected, setSelected] = useState<Experiment>()
  const [values, setValues] = useState<Record<string, string>>({})
  const [measurement, setMeasurement] = useState<Record<string, string>>({})
  const [quantitative, setQuantitative] = useState(false); const [measurementQuantitative, setMeasurementQuantitative] = useState(false)
  const [predictionContext, setPredictionContext] = useState(''); const [gasBasisConfirmed, setGasBasisConfirmed] = useState(false)
  const [gasBasisEvidence, setGasBasisEvidence] = useState(''); const [predictionBasis, setPredictionBasis] = useState('')
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [notice, setNotice] = useState('')
  const lock = useRef(false)
  const measurements = useQuery('experiment-measurements-' + selected?.id, signal => selected ? processApi.measurements(selected.id, signal) : Promise.resolve({ measurements: [] }))
  const comparison = useQuery<Record<string, unknown>>('experiment-comparison-' + selected?.id, signal => selected ? processApi.experimentComparison(selected.id, signal) : Promise.resolve({}))
  const [showEditor, setShowEditor] = useState(true)
  const select = (experiment: Experiment) => { setSelected(experiment); setValues(Object.fromEntries(fields.map(field => [field.name, experiment[field.name] == null ? '' : String(experiment[field.name])]))); setQuantitative(experiment.quantitative_method_confirmed === true); setPredictionContext(experiment.prediction_context && Object.keys(experiment.prediction_context as object).length ? JSON.stringify(experiment.prediction_context, null, 2) : ''); setGasBasisConfirmed(experiment.gas_basis_comparison_confirmed === true); setGasBasisEvidence(String(experiment.gas_basis_evidence ?? '')); setPredictionBasis(String(experiment.prediction_gas_volume_basis ?? '')); setShowEditor(false); setError(''); setNotice('') }
  const fresh = () => { setSelected(undefined); setValues({}); setQuantitative(false); setPredictionContext(''); setGasBasisConfirmed(false); setGasBasisEvidence(''); setPredictionBasis(''); setShowEditor(true); setNotice(''); setError('') }
  const run = async (task: () => Promise<void>) => {
    if (lock.current) return; lock.current = true; setBusy(true); setError(''); setNotice('')
    try { await task() } catch (e) { setError((e as Error).message) } finally { lock.current = false; setBusy(false) }
  }
  const save = (event: React.FormEvent) => {
    event.preventDefault(); void run(async () => {
      const emptyFields = selected ? Object.fromEntries(fields.filter(field => !values[field.name] && !['name', 'origin'].includes(field.name)).map(field => [field.name, null])) : {}
      const body:Record<string,unknown> = { ...emptyFields, ...compactValues(values, textFields), quantitative_method_confirmed: quantitative,
        prediction_context: predictionContext.trim() ? JSON.parse(predictionContext) : {}, gas_basis_comparison_confirmed: gasBasisConfirmed,
        gas_basis_evidence: gasBasisEvidence.trim() || null, prediction_gas_volume_basis: predictionBasis.trim() || null }
      if(selected)delete body.origin
      const result = selected ? await processApi.updateExperiment(selected.id, body) : await processApi.createExperiment(body)
      select(result); journal.refresh(); comparison.refresh(); setNotice('Сохранено в локальной SQLite. Измерения не используются для переобучения.');
    })
  }
  const addMeasurement = (event: React.FormEvent) => {
    event.preventDefault(); if (!selected) return
    void run(async () => {
      const body = compactValues(measurement, ['observed_at', 'measurement_method', 'gas_volume_basis', 'gas_volume_kind', 'methane_fraction_basis'])
      if (body.observed_at) body.observed_at = new Date(String(body.observed_at)).toISOString()
      await processApi.addMeasurement(selected.id, { ...body, quantitative_method_confirmed: measurementQuantitative })
      setMeasurement({}); setMeasurementQuantitative(false); measurements.refresh(); comparison.refresh(); setNotice('Измерение добавлено; прежние записи сохранены.')
    })
  }
  const rows = measurementChartRows(measurements.data?.measurements ?? [])
  const comparable = comparison.data ?? {}
  const predictionFields = <details className="context-fields"><summary>Прогноз модели и сопоставимость условий</summary><p className="process-help">Необязательно. Для поддерживаемого материала можно сохранить измеренные признаки модели. Навоз и пищевые отходы не входят в область Hafner-модели.</p><label className="process-json-label">Лабораторные признаки модели (JSON)<textarea aria-label="Признаки модели JSON" value={predictionContext} onChange={e => setPredictionContext(e.target.value)} placeholder='{"c_vs_sub_m":0.2,"c_vs_sub_f":0.95,"c_vs_inoc":0.03,"ISR":2}' /></label><label className="process-json-label">Условия приведения исходного BMP<input value={predictionBasis} onChange={e => setPredictionBasis(e.target.value)} /></label><label className="process-check"><input type="checkbox" checked={gasBasisConfirmed} onChange={e => setGasBasisConfirmed(e.target.checked)} />Подтверждаю одинаковые условия приведения измеренного газа и исходного BMP</label><label className="process-json-label">Основание сопоставимости<input value={gasBasisEvidence} onChange={e => setGasBasisEvidence(e.target.value)} placeholder="Протокол, температура и давление" /></label></details>
  return <><PageTitle eyebrow="SCIENTIFIC EXPERIMENT LAB" title="Experiment Lab" description="Журнал реальных испытаний. Неизвестные величины оставляйте пустыми." action={<button className="btn btn-secondary" onClick={fresh}><FilePlus2 size={15} />Новый эксперимент</button>} />
    <Notice tone="muted">Пользовательские и лабораторные измерения хранятся с указанием происхождения. MQ-датчик не измеряет точный метан; общий объём биогаза нельзя напрямую сравнить с BMP CH₄.</Notice>
    <LoadState loading={false} error={error} />{notice && <div className="process-success" role="status">{notice}</div>}
    <div className="lab-layout"><Panel title="Журнал экспериментов" subtitle="Сохранённая история, без автоматического обучения"><LoadState {...journal} retry={journal.refresh} />{!journal.loading && !journal.data?.experiments.length && <Empty icon={<Beaker size={32} />} title="Испытаний пока нет">Создайте запись после реального измерения или явно обозначьте происхождение тестовой записи.</Empty>}<div className="experiment-list">{journal.data?.experiments.map(experiment => <button className={`experiment-entry ${selected?.id === experiment.id ? 'selected' : ''}`} key={experiment.id} onClick={() => select(experiment)}><span><FlaskConical size={16} /><strong>{experiment.name}</strong></span><small>{experiment.experiment_date ?? 'Дата не указана'} · {experiment.origin === 'laboratory' ? 'Лабораторные' : 'Пользовательские'}</small>{experiment.archived && <Badge>Архив</Badge>}</button>)}</div></Panel>
    <div className="lab-detail">{showEditor ? <Panel title={selected ? 'Уточнить запись' : 'Новый эксперимент'} subtitle="Введите только известные параметры. Пустое поле не означает ноль."><form onSubmit={save}><ScientificFields fields={selected ? fields.filter(f => f.name !== 'origin') : fields} values={values} setValue={(name, value) => setValues(v => ({ ...v, [name]: value }))} prefix="lab-" />{predictionFields}<label className="process-check"><input type="checkbox" checked={quantitative} onChange={e => setQuantitative(e.target.checked)} />Подтверждаю количественный метод и калибровку измерения CH₄, если доля указана</label><button className="btn btn-primary full-width" disabled={busy || !values.name?.trim() || !values.origin} type="submit">{busy ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}Сохранить эксперимент</button><div className="form-caption">Для создания нужны название и происхождение; остальные параметры необязательны.</div></form></Panel> : selected && <Panel title={selected.name} subtitle={`${selected.origin === 'laboratory' ? 'Лабораторные' : 'Пользовательские'} измерения · ${selected.experiment_date ?? 'без даты'}`} action={<button className="text-button" onClick={() => setShowEditor(true)}>Уточнить запись</button>}><div className="lab-facts"><div><span>Сырьё</span><strong>{selected.material ?? 'Не указано'}</strong></div><div><span>Масса / объём</span><strong>{number(selected.mass_kg)} кг / {number(selected.volume_l)} л</strong></div><div><span>Газ / доля CH₄</span><strong>{number(selected.gas_volume_m3, 5)} м³ / {number(selected.methane_fraction, 4)}</strong></div><div><span>Версия ML при записи</span><strong>{String((selected.model_snapshot as Record<string, unknown> | undefined)?.version ?? '') || 'Прогноз не фиксировался'}</strong></div></div><div className="process-actions"><a className="btn btn-secondary" href={processApi.exportUrl(selected.id)} download><Download size={15} />Экспорт CSV</a><button className="btn btn-secondary" disabled={busy || selected.archived} onClick={() => void run(async () => { const row = await processApi.archiveExperiment(selected.id); select(row); journal.refresh(); setNotice('Эксперимент помещён в архив; история сохранена.') })}><Archive size={15} />В архив</button></div><JsonDetails value={selected} title="Параметры и происхождение записи" /></Panel>}
    {selected && <><Panel title="Сравнение с прогнозом" subtitle="Сопоставляются CH₄, масса VS и одинаковые условия приведения"><LoadState {...comparison} retry={comparison.refresh} />{Object.keys(comparable).length > 0 && <><div className="process-result-message">{typeof comparable.message === 'string' ? comparable.message : typeof comparable.reason === 'string' ? comparable.reason : Array.isArray(comparable.reasons) ? comparable.reasons.join('. ') : 'Проверка сопоставимости выполнена. Подробности и ограничения приведены ниже.'}</div><div className="lab-facts"><div><span>Измеренный CH₄</span><strong><ResultValue value={comparable.measured_methane_m3} unit="м³" digits={5} /></strong></div><div><span>Потенциал по модели</span><strong><ResultValue value={comparable.predicted_bmp_ml_ch4_g_vs} unit="мл CH₄/г VS" digits={5} /></strong></div></div><JsonDetails value={comparable} title="Сопоставимость, версия модели и ограничения" /></>}</Panel>
      <Panel title="Измерения во времени" subtitle="Только введённые значения; пропуски не интерполируются"><LoadState {...measurements} retry={measurements.refresh} />{rows.some(row => row.temperature !== null || row.gas !== null) ? <div className="chart chart-compact" data-testid="experiment-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows}><CartesianGrid stroke="#24333b" vertical={false} /><XAxis dataKey="name" stroke="#91a6ae" tickFormatter={v => String(v).replace('T', ' ').slice(0, 16)} /><YAxis yAxisId="temperature" stroke="#91a6ae" /><YAxis yAxisId="gas" orientation="right" stroke="#91a6ae" /><Tooltip contentStyle={{ background: '#15242b', border: '1px solid #29414a' }} /><Line yAxisId="temperature" name="Температура, °C" dataKey="temperature" stroke="#55d6af" connectNulls={false} isAnimationActive={false} /><Line yAxisId="gas" name="Измеренный биогаз, м³" dataKey="gas" stroke="#e4b873" connectNulls={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div> : <Empty title="Измерений для графика пока нет">График появится после ввода температуры или объёма газа.</Empty>}{measurements.data?.measurements.length ? <div className="table-scroll"><table><thead><tr><th>Время</th><th>Температура, °C</th><th>pH</th><th>Биогаз, м³</th><th>CH₄, доля</th></tr></thead><tbody>{measurements.data.measurements.map(row => <tr key={row.id}><td>{row.observed_at ?? 'Не указано'}</td><td>{number(row.temperature_c)}</td><td>{number(row.ph)}</td><td>{number(row.gas_volume_m3, 5)}</td><td>{number(row.methane_fraction, 4)}</td></tr>)}</tbody></table></div> : null}</Panel>
      <Panel title="Добавить измерение" subtitle="Новая запись не заменяет предыдущую"><form onSubmit={addMeasurement}><ScientificFields fields={measurementFields} values={measurement} setValue={(name, value) => setMeasurement(v => ({ ...v, [name]: value }))} prefix="measurement-" /><label className="process-check"><input type="checkbox" checked={measurementQuantitative} onChange={e => setMeasurementQuantitative(e.target.checked)} />Количественный калиброванный метод CH₄ подтверждён</label><button className="btn btn-primary" type="submit" disabled={busy || !Object.values(measurement).some(value => value !== '')}><Save size={15} />Добавить измерение</button></form></Panel></>}
    </div></div>
  </>
}
