# Реальный агент и сохранённые реальные цены

У меня 20 кг пищевых отходов в Караганде. Что выгоднее: продать или переработать в биогаз?

Сырьё: пищевые отходы. Состав отходов меняется; BMP-модель Hafner для этой категории не обучена. Численный прогноз Hafner для этого материала отклоняется.

Для потенциального метана нужны BMP с единицами, измеренная масса VS и условия приведения газа.

Последние сохранённые цены: electricity: 20.39 KZT/kWh, KZ-Karaganda, VERIFIED_CURRENT, возраст 28 дн., публикация 2026-10-09, профиль household_tier1_electric_stove_statistics, statistics_as_published, источник БНС РК: месячная статистика электроэнергии, население, первый уровень, электроплиты, статистическая/справочная величина, не предложение сделки; natural_gas: 54.81 KZT/m3, KZ-Karaganda, VERIFIED_CURRENT, возраст 28 дн., публикация 2026-10-09, профиль household_statistics, statistics_as_published, источник БНС РК: месячная статистика розничных цен природного газа, статистическая/справочная величина, не предложение сделки; electricity: 38.87 KZT/kWh, KZ-Karaganda, STALE, возраст 422 дн., публикация не установлена, профиль non_household, VAT_included, источник Қарағанды Жарық: тариф небытовых потребителей г. Караганда, тариф/котировка с указанным профилем; electricity: 33.51 KZT/kWh, KZ-Karaganda, STALE, возраст 422 дн., публикация не установлена, профиль non_household, VAT_excluded, источник Қарағанды Жарық: тариф небытовых потребителей г. Караганда, тариф/котировка с указанным профилем

Рыночные сценарии. A: Не заданы: sale_storage_cost, sale_transport_cost; B: Не заданы: preparation_cost, heating_cost, operating_cost, storage_cost, transport_cost, digestate_handling_cost, energy_use_kwh, recovery_fraction, gas_volume_basis; C: Не заданы: gas_sale_technical_confirmed, gas_sale_legal_confirmed, gas_sale_evidence; D: Не заданы: digestate_quality_confirmed, digestate_market_allowed, digestate_quality_evidence. Итоговая рекомендация не выдана: сравнение неполное. Доходы газа, электричества и дигестата не суммировались; B, C и D — альтернативы.

Нужны данные: bmp_ml_ch4_g_vs, vs_mass_kg, bmp_unit, gas_volume_basis. Ответьте JSON-объектом или полями имя=значение; строки с пробелами — в кавычках.

Источники:
- EBMUD / US EPA (March 2008) — Anaerobic Digestion of Food Waste, final experimental report: https://www.epa.gov/system/files/documents/2024-08/ebmud-final-report-anaerobic-digestion-of-food-waste-2008-03.pdf
- БНС РК: месячная статистика розничных цен природного газа: https://stat.gov.kz/api/iblock/element/353619/file/ru/
- Қарағанды Жарық: тариф небытовых потребителей г. Караганда: https://www.k-zharyk.kz/ru/node/329