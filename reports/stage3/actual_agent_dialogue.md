# Реальный вызов рыночных инструментов

У меня 20 кг пищевых отходов в Алматы. Что выгоднее: продать или переработать в биогаз?

analyze_substrate [ok] → predict_bmp [unsupported] → calculate_methane [needs_input] → get_market_prices [ok] → compare_market_scenarios [needs_input] → explain_market_recommendation [needs_input]

Сырьё: пищевые отходы. Состав отходов меняется; BMP-модель Hafner для этой категории не обучена. Численный прогноз Hafner для этого материала отклоняется.

Последние сохранённые цены: electricity: 50.03 KZT/kWh, возраст 46 дн., не подтверждена как актуальная

Для потенциального метана нужны BMP с единицами, измеренная масса VS и условия приведения газа.

Рыночные сценарии. A: Не заданы: sale_storage_cost, sale_transport_cost; B: Не заданы: preparation_cost, heating_cost, operating_cost, storage_cost, transport_cost, digestate_handling_cost, energy_use_kwh, recovery_fraction, gas_volume_basis; C: Не заданы: gas_sale_technical_confirmed, gas_sale_legal_confirmed, gas_sale_evidence; D: Не заданы: digestate_quality_confirmed, digestate_market_allowed, digestate_quality_evidence. Итоговая рекомендация не выдана: сравнение неполное. Доходы газа, электричества и дигестата не суммировались; B, C и D — альтернативы.

Нужны данные: bmp_ml_ch4_g_vs, vs_mass_kg, bmp_unit, gas_volume_basis. Ответьте JSON-объектом или полями имя=значение; строки с пробелами — в кавычках.

Источники:
- EBMUD / US EPA (March 2008) — Anaerobic Digestion of Food Waste, final experimental report: https://www.epa.gov/system/files/documents/2024-08/ebmud-final-report-anaerobic-digestion-of-food-waste-2008-03.pdf
- АО Алатау Жарық Компаниясы — Энергосбыт, небытовая группа 2: https://www.esalmaty.kz/ru/business-tariffs