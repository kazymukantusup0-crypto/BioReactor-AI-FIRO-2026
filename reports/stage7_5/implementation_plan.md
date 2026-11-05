# v7.5: аудит и план

До изменений сохранены хеши артефактов, все старые строки SQLite и резервная копия базы.

Рабочие компоненты: research_and_estimate (src/research/orchestrator.py), проверенный профиль RM1, память ConversationAgent, Crossref с кешем/backoff, 28 наблюдений рынка, сценарии A–D, FastAPI и React Chat. Ollama qwen3:8b установлен, контекст 2048, 100% GPU; резерв qwen2.5:1.5b сохранён. На ноутбуке фактически i7-12700H (а не i5). Формулы первоначального нагрева, UA-потерь и оборудования уже есть в src/optimizer/energy_model.py; ограничения загрузки — в constraints.py. Рыночные цены строго отбирает src/market/scenarios.select_price. Калькулятор v7 покрывает только явные пользовательские цены и не строит полный энергобаланс.

Изменения:
1. src/economics/decision_schemas.py — диапазоны, газовый базис, КПД, расходы, цены и границы применимости.
2. gas_composition.py, energy_conversion.py — состав/биогаз и раздельные выходы тепла, электричества, CHP.
3. reactor_balance.py, feasibility.py — переиспользование модели v6 и её ограничений; раздельные нагрузки.
4. valuation.py, break_even.py, decision_engine.py, complete_analysis.py — A–E/CHP, проверка цен, бюджет затрат и детерминированный статус.
5. data/research/decision_references.json — отдельные источники состава и инженерных сценариев; исходный RM1 не меняется.
6. src/research/orchestrator.py, estimation/schemas.py, research/api.py — добавочный decision_analysis; старые поля/API v7 остаются.
7. src/agent/decision_bridge.py, decision_response.py, dialogue_types.py — структурированная память сценариев и короткое продолжение вместо повторного отчёта.
8. frontend/src/DecisionCards.tsx и существующий Chat — карточки расчёта, раскрываемые допущения/источники.
9. tests/test_complete_economics.py, verify_stage7_5.py, frontend/tests — независимые формулы, интеграция, полный сценарий 142 л, реальные HTTP/Ollama/Chrome и проверка сохранности.

Не вводятся универсальные свойства партии или установки. Неизвестные КПД/извлечение/UA показываются отдельными явно сценарными примерами. Статистическая цена электроэнергии Караганды 20,39 ₸/кВт·ч — рыночный ориентир для условного замещения, не подтверждённый индивидуальный тариф.
