export function conversationQuestion(text: string): string {
 if (!text.trimStart().startsWith('{')) return text
 try {
  const input = JSON.parse(text).decision_inputs
  if (!input || typeof input !== 'object') return text
  const labels: Record<string, string> = { reactor_working_volume_l: 'Рабочий объём, л', temperature_c: 'Температура процесса, °C', initial_temperature_c: 'Начальная температура, °C', ambient_temperature_c: 'Температура среды, °C', heated_mass_kg: 'Нагреваемая масса, кг', heat_capacity_kj_kg_k: 'Теплоёмкость, кДж/(кг·К)', heat_loss_coefficient_w_k: 'UA, Вт/К', duration_days: 'Период, сутки', heater_efficiency: 'КПД нагревателя', auxiliary_energy_kwh: 'Вспомогательная энергия, кВт·ч' }
  const details = Object.entries(input.reactor ?? {}).filter(([key]) => key in labels).map(([key, value]) => `${labels[key]}: ${value}`)
  if (input.costs) details.push(`Введены статьи затрат: ${Object.keys(input.costs).length}`)
  return `Уточнены параметры расчёта.${details.length ? `\n${details.join('\n')}` : ''}`
 } catch { return text }
}
