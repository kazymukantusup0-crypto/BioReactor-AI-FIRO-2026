# Historical real-Qwen failure analysis

Date: 2026-11-09. This is a forensic review of previously saved traces, not a new live baseline. No Stage 9 held-out cases were used for tuning or executed. Raw prompts, drafts, verifier records, tool calls and displayed answers are extracted from the JSON artifacts. When an intermediate Qwen draft was not stored, that absence is stated; it is not reconstructed.

## Evidence limits and count reconciliation

- Stage 9 rc3 trace has 23 development cases; summary reports 10/23 automated contract passes. The 13 automated non-pass cases are listed below. This is not blinded scientific adjudication.
- Manual review also marks D04 scientifically false (unsupported 30 C optimum claim), D01 partial, D03 partial, and D02 pending. D04 is analyzed separately despite its automated contract pass.
- Previous acceptance summary reports 19/20 completed with 17 FAIL, 1 PARTIAL, 2 PASS. Its detailed case table enumerates 16 FAIL, 1 PARTIAL, 2 PASS and one IN PROGRESS. Denominator remains inconsistent; no rate is inferred.
- Provider records show `offline`/`qwen3:8b` actual generation through loopback Ollama in historical runs. A model-generation record does not mean every final response came from Qwen; some were engine fallbacks after rejection/timeout.
- Separate raw Qwen prose is absent for some cases. The saved `reply.answer` is the displayed final; the diagnostics may retain rejected structured drafts.

## Stage 9 automated non-pass cases

### D03 (automated non-pass)
Expected: Compare both 10 kg feedstocks; distinguish methane potential from net profitability and show available economics.
Root-cause assessment: Qwen draft ranked food waste as more profitable based on gas volume; verifier rejected unconfirmed_profitability_ranking. Next synthesis timed out; fallback displayed cattle manure only. Categories: C/F/H/K; rejected claim, timeout, and incomplete fallback are directly evidenced. Why a second synthesis was needed is not established..
#### Turn 1
User request: Что выгоднее: 10 кг коровьего навоза или 10 кг пищевых отходов?
Tools: assess_substrate_potential=ok, evaluate_partial_economics=ok
Saved Qwen rejected draft(s): [{"conclusion": "Пищевые отходы выгоднее, так как их потенциал биогаза выше (0.636 м³) по сравнению с коровьим навозом (0.339–0.520 м³).", "explanation": "Пищевые отходы (s4) дают больше биогаза и имеют более высокую ценность по сравнению с навозом КРС (s1).", "limitations": ["Неизвестные затраты и цены затрудняют окончательную оценку прибыльности."], "next_question": "Какие дополнительные затраты могут повлиять на выбор между навозом и пищевыми отходами?", "evidence_ids": ["s4.methane", "s1.biogas"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=unconfirmed_profitability_ranking, synthesis: Provider unreachable or invalid JSON: TimeoutError, v9_synthesis: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Навоз КРС (отдельный сценарий s1): потенциал метана: 0.2032–0.286 м³ CH₄ (условный сценарий). |  | Навоз КРС (отдельный сценарий s1): масса VS: 1.016–1.144 кг VS (условный сценарий). |  | Навоз КРС (отдельный сценарий s1): потенциал общего биогаза: 0.33867–0.52 м³ биогаза (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "mixture"}

### D05 (automated non-pass)
Expected: Preserve the 5 kg food-waste batch, add 2 kg poultry manure as another component, and recompute.
Root-cause assessment: Turn 1 draft first gave 1.59 m3 then 0.318 m3; verifier rejected quantity/evidence binding. Turn 2 draft included 2 kg and 7 kg but verifier rejected those grounded masses because only methane/VS typed values were allowed. Engine fallback displayed 0.31814 then 0.67308 m3 CH4. Categories: G/H/I; missing user-input quantities in allowed typed evidence is confirmed by rejection trace..
#### Turn 1
User request: У меня 5 кг пищевых отходов. Сколько метана?
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Потенциал метана от 5 кг пищевых отходов: 1.59 м³ CH₄.", "explanation": "Использованы данные из s1.methane. Роль ёмкости: влияет на объем и условия анализа, но не на расчет метана.", "limitations": ["Неизвестны параметры реактора и условия работы."], "next_question": "Каковы затраты на обработку отходов?", "evidence_ids": ["s1.methane"], "decision": "not_established"}, {"conclusion": "Потенциал метана от 5 кг пищевых отходов: 0.318 м³ CH₄.", "explanation": "Использованы данные из s1.methane. Роль ёмкости: влияет на объем и условия анализа, но не на расчет метана.", "limitations": ["Неизвестны параметры реактора и условия работы."], "next_question": "Каковы затраты на обработку отходов?", "evidence_ids": ["s1.methane"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit, evidence_id_outside_reference_list.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Пищевые отходы: потенциал метана: 0.31814 м³ CH₄ (условный сценарий). |  | Пищевые отходы: масса VS: 0.603 кг VS (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "food_waste", "quantity": 5.0, "unit": "kg"}
#### Turn 2
User request: Добавь 2 кг куриного помёта и пересчитай
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Добавлено 2 кг куриного помёта. Общее количество смеси: 7 кг. Метановый потенциал: 0.673 м³ CH₄. Масса VS: 1.712 кг. Дополнительные данные требуют проверки.", "explanation": "Объём ёмкости влияет на выход биогаза, но не указан. Данные о метане и VS рассчитаны на основе литературы.", "limitations": ["Неизвестны плотность и объём смеси", "Не указаны условия реакции"], "next_question": "Уточни плотность и объём смеси для расчёта выхода биогаза.", "evidence_ids": ["s1.methane", "s1.vs"], "decision": "not_established"}, {"conclusion": "Добавлено 2 кг куриного помёта. Общее количество смеси: 7 кг. Метановый потенциал: 0.673 м³ CH₄. Масса VS: 1.712 кг. Дополнительные данные требуют проверки.", "explanation": "Объём ёмкости влияет на выход биогаза, но не указан. Данные о метане и VS рассчитаны на основе литературы.", "limitations": ["Неизвестны плотность и объём смеси", "Не указаны условия реакции"], "next_question": "Уточни плотность и объём смеси для расчёта выхода биогаза.", "evidence_ids": ["s1.methane", "s1.vs"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Пищевые отходы + Птичий помёт: потенциал метана: 0.67308 м³ CH₄ (условный сценарий). |  | Пищевые отходы + Птичий помёт: масса VS: 1.7122 кг VS (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "mixture"}

### D07 (automated non-pass)
Expected: Calculate any available gross economic value for 5 kg and distinguish it from profit; run partial economics.
Root-cause assessment: Market, price-history and substrate tools ran; economics tool did not. History required a missing commodity. Tool-selection timed out; final showed methane only. Categories: C/K; required economics evidence is absent in the trace..
#### Turn 1
User request: Сколько денег я заработаю на 5 кг пищевых отходов?
Tools: get_market_prices=ok, get_price_history=needs_input, assess_substrate_potential=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=selection: Provider unreachable or invalid JSON: TimeoutError, v9_tool_selection: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Пищевые отходы: потенциал метана: 0.31814 м³ CH₄ (условный сценарий). |  | Пищевые отходы: масса VS: 0.603 кг VS (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "food_waste", "quantity": 5.0, "unit": "kg"}

### D08 (automated non-pass)
Expected: For 47 L liquid cattle manure, estimate conditional methane and available energy; preserve the 114 L vessel as nominal capacity only.
Root-cause assessment: Only substrate tool ran. Fallback displayed methane/VS/biogas, no energy or capacity caveat in this historical reply. Categories: C/I; missing process/economics tools confirmed. This trace predates the later capacity fix; no current regression claimed..
#### Turn 1
User request: Есть 47 л жидкого коровьего навоза и реактор 114 л. Оцени метан и ценность энергии.
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Метан: 0.97–1.36 м³ CH₄. Энергетическая ценность: 0.97–1.36 м³ биогаза (LHV). Реактор 114 л подходит для загрузки 47 л навоза. Данные о продаже и прибыли не подтверждены.", "explanation": "Емкость реактора достаточна для обработки 47 л навоза. Метан и биогаз рассчитаны на основе сценариев, но без подтверждения рыночных условий и затрат невозможно определить прибыльность.", "limitations": ["profit_established=false", "gas_sale_technical_confirmed=false"], "next_question": "Какие рыночные условия и затраты на обработку навоза в регионе KZ-Karaganda?", "evidence_ids": ["s1.methane", "s1.biogas", "s1.vessel"], "decision": "not_established"}, {"conclusion": "Метан: 0.97–1.36 м³ CH₄. Энергетическая ценность: 0.97–1.36 м³ биогаза (LHV). Реактор 114 л подходит для загрузки 47 л навоза. Данные о продаже и прибыли не подтверждены.", "explanation": "Емкость реактора достаточна для обработки 47 л навоза. Метан и биогаз рассчитаны на основе сценариев, но без подтверждения рыночных условий и затрат невозможно определить прибыльность.", "limitations": ["profit_established=false", "gas_sale_technical_confirmed=false"], "next_question": "Какие рыночные условия и затраты на обработку навоза в регионе KZ-Karaganda?", "evidence_ids": ["s1.methane", "s1.biogas", "s1.vessel"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Навоз КРС (отдельный сценарий s1): потенциал метана: 0.96746–1.3617 м³ CH₄ (условный сценарий). |  | Навоз КРС (отдельный сценарий s1): масса VS: 4.8373–5.4467 кг VS (условный сценарий). |  | Навоз КРС (отдельный сценарий s1): потенциал общего биогаза: 1.6124–2.4758 м³ биогаза (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "cattle_manure", "quantity": 47.0, "unit": "L", "reactor_total_volume_l": 114.0}

### D09 (automated non-pass)
Expected: Start a new 470 L fresh-grass batch in an 840 L vessel; use scientific lookup and do not treat liters as methane/mass.
Root-cause assessment: Turn 2 had no tools. Qwen said vessel capacity allowed 470 L as methane-potential basis and asked conversion efficiency. State preserved grass/470 L/840 L. Categories: A/C/F/G; planner skipped science lookup and used a false relationship; batch facts were retained..
#### Turn 1
User request: Есть 47 л жидкого коровьего навоза и реактор 114 л. Оцени метан.
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Метан от 0.97 до 1.36 м³ при 47 л навоза. Реактор 114 л позволяет загрузить 100% объема. Метан составляет 55–60% биогаза. Прибыль не определена.", "explanation": "Емкость реактора позволяет использовать весь объем навоза. Метан рассчитан как часть биогаза. Без цен и затрат невозможно определить прибыль.", "limitations": ["Неизвестные затраты и цены", "Не подтверждено использование газа"], "next_question": "Какова цена метана в регионе KZ-Karaganda?", "evidence_ids": ["s1.methane", "s1.biogas", "s1.vessel"], "decision": "not_established"}, {"conclusion": "Метан от 0.97 до 1.36 м³ при 47 л навоза. Реактор 114 л позволяет загрузить 100% объема. Метан составляет 55–60% биогаза. Прибыль не определена.", "explanation": "Емкость реактора позволяет использовать весь объем навоза. Метан рассчитан как часть биогаза. Без цен и затрат невозможно определить прибыль.", "limitations": ["Неизвестные затраты и цены", "Не подтверждено использование газа"], "next_question": "Какова цена метана в регионе KZ-Karaganda?", "evidence_ids": ["s1.methane", "s1.biogas", "s1.vessel"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Навоз КРС (отдельный сценарий s1): потенциал метана: 0.96746–1.3617 м³ CH₄ (условный сценарий). |  | Навоз КРС (отдельный сценарий s1): масса VS: 4.8373–5.4467 кг VS (условный сценарий). |  | Навоз КРС (отдельный сценарий s1): потенциал общего биогаза: 1.6124–2.4758 м³ биогаза (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "cattle_manure", "quantity": 47.0, "unit": "L", "reactor_total_volume_l": 114.0}
#### Turn 2
User request: Новая партия: 470 литров свежей травы, реактор 840 литров. Каков потенциал метана?
Tools: none
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=ok; checked=False; outcome=not recorded; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Потенциал метана зависит от эффективности реактора и состава сырья. Для точного расчета требуется информация о конверсии массы травы в метан. |  | Объем реактора (840 л) больше объема травы (470 л), что позволяет для потенциала метана использовать 470 л как основу. |  | Неизвестна эффективность преобразования травы в метан |  | Неизвестны условия реакции |  | Какова эффективность преобразования травы в метан при указанных условиях?
Persisted state facts: {"reactor_total_volume_l": 840.0, "material": "grass", "quantity": 470.0, "unit": "L"}

### D10 (automated non-pass)
Expected: Correct the prior cattle-manure lot to 47 L and 114 L vessel, retaining material identity and recalculating.
Root-cause assessment: Turn 2 had no tools; final generic answer said vessel must exceed manure volume. State changed material from cattle_manure to generic manure while retaining 47 L and 114 L. Categories: B/C/G; identity loss and omitted recalculation are confirmed by turn-2 state and empty tool trace..
#### Turn 1
User request: Есть 478 литров жидкого коровьего навоза, реактор 700 литров. Сколько метана?
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Метана в 478 л жидкого коровьего навоза в диапазоне 9.84–13.85 м³, при условии 55–60% содержания метана в биогазе. Реактор 700 л не ограничивает метановый потенциал.", "explanation": "Емкость реактора не влияет на метановый потенциал, так как он определяется характеристиками навоза.", "limitations": ["Неизвестны точные доли метана в биогазе", "Не подтверждено использование метана"], "next_question": "Можно ли использовать метан для отопления или продажи?", "evidence_ids": ["s1.methane", "s1.biogas", "s1.vessel"], "decision": "not_established"}, {"conclusion": "Метана в 478 л жидкого коровьего навоза в диапазоне 9.84–13.85 м³, при условии 55–60% содержания метана в биогазе. Реактор 700 л не ограничивает метановый потенциал.", "explanation": "Емкость реактора не влияет на метановый потенциал, так как он определяется характеристиками навоза.", "limitations": ["Неизвестны точные доли метана в биогазе", "Не подтверждено использование метана"], "next_question": "Можно ли использовать метан для отопления или продажи?", "evidence_ids": ["s1.methane", "s1.biogas", "s1.vessel"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Навоз КРС (отдельный сценарий s1): потенциал метана: 9.8392–13.849 м³ CH₄ (условный сценарий). |  | Навоз КРС (отдельный сценарий s1): масса VS: 49.196–55.394 кг VS (условный сценарий). |  | Навоз КРС (отдельный сценарий s1): потенциал общего биогаза: 16.399–25.179 м³ биогаза (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "cattle_manure", "quantity": 478.0, "unit": "L", "reactor_total_volume_l": 700.0}
#### Turn 2
User request: Исправь: 47 литров навоза, реактор 114 литров.
Tools: none
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=ok; checked=False; outcome=not recorded; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Объем навоза 47 л, объем реактора 114 л. Реактор должен быть больше объема навоза для эффективной обработки. |  | Объем реактора должен быть больше объема навоза для обеспечения достаточного пространства для биологических процессов. |  | Неизвестны затраты на обработку и прибыль не определена. |  | Каковы затраты на обработку навоза в вашем регионе?
Persisted state facts: {"material": "manure", "quantity": 47.0, "unit": "L", "reactor_total_volume_l": 114.0}

### D11 (automated non-pass)
Expected: Changing only vessel size from 100 to 150 L should not change methane potential for the same 12 kg batch; show the computed value.
Root-cause assessment: Turn 1 model draft gave unsupported 0.66-1.05 m3 vs tool 0.78339; verifier caught it. Turn 2 draft omitted computed methane; repair timed out; fallback retained 0.78339. Categories: F/H/K; incorrect range, omission and timeout are separately confirmed..
#### Turn 1
User request: Есть 12 кг свежей травы и реактор 100 литров. Сколько газа?
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Объем газа зависит от сценария. Для 12 кг свежей травы в 100-литровом реакторе потенциал метана составляет от 0,66 до 1,05 м³ CH₄.", "explanation": "Емкость реактора ограничивает загрузку, но не определяет объем газа. Результаты основаны на литературных оценках.", "limitations": ["Неизвестны параметры реактора и условия процесса", "Не подтверждено использование газа"], "next_question": "Какой объем метана можно получить при оптимальных условиях?", "evidence_ids": ["s1.methane", "s2.methane", "s3.methane", "s4.methane", "s5.methane"], "decision": "not_established"}, {"conclusion": "Объем газа зависит от сценария. Для 12 кг свежей травы в 100-литровом реакторе потенциал метана составляет от 0,66 до 1,05 м³ CH₄.", "explanation": "Емкость реактора ограничивает загрузку, но не определяет объем газа. Результаты основаны на литературных оценках.", "limitations": ["Неизвестны параметры реактора и условия процесса", "Не подтверждено использование газа"], "next_question": "Какой объем метана можно получить при оптимальных условиях?", "evidence_ids": ["s1.methane", "s2.methane", "s3.methane", "s4.methane", "s5.methane"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Трава (отдельный сценарий s1): потенциал метана: 0.78339 м³ CH₄ (условный сценарий). |  | Трава (отдельный сценарий s1): масса VS: 2.964 кг VS (условный сценарий). |  | Трава (отдельный сценарий s1): номинальная ёмкость (ограничивает загрузку, не задаёт метан): 100 л (по сообщённым данным). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"reactor_total_volume_l": 100.0, "material": "grass", "quantity": 12.0, "unit": "kg"}
#### Turn 2
User request: А если реактор будет 150 литров, увеличится ли выход?
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Увеличение объема реактора до 150 литров не гарантирует увеличения выхода метана, так как выход зависит от количества сырья и его свойств, а не только от объема.", "explanation": "Объем реактора влияет на загрузку, но не напрямую на выход газа. Для точного расчета необходимо учитывать массу сырья и его потенциал.", "limitations": ["Неизвестны параметры работы реактора", "Не заданы условия газа"], "next_question": "Какой объем загрузки сырья возможен в реакторе 150 литров?", "evidence_ids": ["s1.vessel", "s2.vessel", "s3.vessel", "s4.vessel", "s5.vessel"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=computed_methane_omitted, synthesis: Provider unreachable or invalid JSON: TimeoutError, v9_synthesis: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Трава (отдельный сценарий s1): потенциал метана: 0.78339 м³ CH₄ (условный сценарий). |  | Трава (отдельный сценарий s1): масса VS: 2.964 кг VS (условный сценарий). |  | Трава (отдельный сценарий s1): номинальная ёмкость (ограничивает загрузку, не задаёт метан): 150 л (по сообщённым данным). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"reactor_total_volume_l": 100.0, "material": "grass", "quantity": 12.0, "unit": "kg"}

### D12 (automated non-pass)
Expected: Bind 5 kg, TS 20%, VS 80% of TS and BMP 400 mL CH4/g VS; compute the conditional potential.
Root-cause assessment: NLU stopped with Unbound material quantities: 400 mL; no tool calls; asked whether a number referred to feed or reactor. Categories: B/C; parser assigned a BMP unit quantity to the wrong role..
#### Turn 1
User request: 5 кг пищевых отходов, TS 20%, VS 80% от TS, BMP 400 мл CH4/г VS. Рассчитай потенциал метана.
Tools: none
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=not recorded; checked=not recorded; outcome=not recorded; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Неясно, к каким параметрам относятся новые значения. Это неоднозначность назначения чисел, а не противоречие измерений. |  | Какое значение относится к сырью, а какое — к реактору?

### D15 (automated non-pass)
Expected: Show supported literature scenarios for 6 kg fresh grass without changing the batch/unit basis.
Root-cause assessment: Substrate tool returned several scenarios; Qwen draft normalized to an unsupported range; verifier rejected it; fallback displayed separate scenarios. Categories: D/F/H; typed basis mismatch is evidenced by the rejected draft and diagnostics..
#### Turn 1
User request: Есть 6 кг свежей травы. Каков метановый потенциал по опубликованным данным?
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Метановый потенциал свежей травы по опубликованным данным составляет 0.3917–0.5230 м³ CH₄ на 1 кг сырой массы.", "explanation": "Данные взяты из литературных оценок, но требуют дополнительной проверки на соответствие реальным условиям.", "limitations": ["Неизвестны параметры реактора и условия анализа"], "next_question": "Каковы условия анализа и параметры реактора для точного расчета метанового потенциала?", "evidence_ids": ["s1.methane", "s2.methane", "s3.methane", "s4.methane", "s5.methane"], "decision": "not_established"}, {"conclusion": "Метановый потенциал свежей травы по опубликованным данным составляет 0.3917–0.5230 м³ CH₄ на 1 кг сырой массы.", "explanation": "Данные взяты из литературных оценок, но требуют дополнительной проверки на соответствие реальным условиям.", "limitations": ["Неизвестны параметры реактора и условия анализа"], "next_question": "Каковы условия анализа и параметры реактора для точного расчета метанового потенциала?", "evidence_ids": ["s1.methane", "s2.methane", "s3.methane", "s4.methane", "s5.methane"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Трава (отдельный сценарий s1): потенциал метана: 0.39169 м³ CH₄ (условный сценарий). |  | Трава (отдельный сценарий s1): масса VS: 1.482 кг VS (условный сценарий). |  | Трава (отдельный сценарий s2): потенциал метана: 0.3291 м³ CH₄ (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "grass", "quantity": 6.0, "unit": "kg"}

### D18 (automated non-pass)
Expected: Assess 2 kg chicken litter potential and evidence-based inhibition risks, separating unknowns from facts.
Root-cause assessment: No tools. Qwen claimed inhibition was limited by low toxic concentration and mentioned emissions/market; verification was unchecked, yet prose was shown. Categories: C/F/H; unchecked qualitative claims were published in the historical trace..
#### Turn 1
User request: Есть 2 кг куриного помёта. Оцени потенциал и риски ингибирования.
Tools: none
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=ok; checked=False; outcome=not recorded; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Потенциал ингибирования куриного помёта ограничен из-за низкой концентрации токсичных веществ. Риски связаны с неполной разложимостью и возможными выбросами. Без подтверждённых данных о рынке и условиях, экономическая оценка не возможна. |  | Роль ёмкости: определяет объём и срок хранения, влияет на эффективность и безопасность процесса. |  | недостаток данных о рынке |  | неподтверждённые условия использования |  | Какие данные о рынке и условиях использования куриного помёта доступны для анализа?
Persisted state facts: {"material": "poultry_manure", "quantity": 2.0, "unit": "kg"}

### D19 (automated non-pass)
Expected: Use 8 kg swine manure and a conditional 60% methane fraction to calculate methane and total biogas without equating kg and m3.
Root-cause assessment: Tool computed methane under two profiles. Qwen draft treated 8 kg as 8 m3 biogas and 4.8 m3 methane; verifier rejected units; fallback omitted the conditional biogas conversion. Categories: B/C/D/H; wrong units are confirmed. Missing deterministic fraction conversion is supported by absent tool evidence..
#### Turn 1
User request: 8 кг свиного навоза, условно 60% метана в биогазе. Рассчитай метан и общий биогаз.
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "Метан: 4.8 м³, общий биогаз: 8 м³. Метан составляет 60% от общего биогаза.", "explanation": "Использовано 8 кг свиного навоза с 60% метана в биогазе. Метан рассчитан как 60% от общего биогаза.", "limitations": ["Неизвестны параметры реактора и условия, влияющие на выход биогаза."], "next_question": "Каковы затраты на обработку 8 кг свиного навоза?", "evidence_ids": ["s1.methane", "s1.vs", "s2.methane", "s2.vs"], "decision": "not_established"}, {"conclusion": "Метан: 0.0378 м³, общий биогаз: 0.063 м³. Метан составляет 60% от общего биогаза.", "explanation": "Использованы 8 кг свиного навоза с 60% метана в биогазе. Метан рассчитан как 60% от общего биогаза.", "limitations": ["Неизвестны параметры реактора и условия, влияющие на выход биогаза."], "next_question": "Каковы затраты на обработку 8 кг свиного навоза?", "evidence_ids": ["s1.methane", "s1.vs", "s2.methane", "s2.vs"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=not recorded; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Свиной навоз (отдельный сценарий s1): потенциал метана: 0.037845 м³ CH₄ (условный сценарий). |  | Свиной навоз (отдельный сценарий s1): масса VS: 0.182 кг VS (условный сценарий). |  | Свиной навоз (отдельный сценарий s2): потенциал метана: 0.020778 м³ CH₄ (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены.
Persisted state facts: {"material": "swine_manure", "quantity": 8.0, "unit": "kg"}

### D22 (automated non-pass)
Expected: Show scientific sources and limitations of BMP transfer without requiring batch mass.
Root-cause assessment: Profile search, study comparison and source verification succeeded; another tool-selection call timed out. Verifier unchecked; fallback asked irrelevant mass and omitted useful source findings. Categories: C/G/H/K; extra tool-selection timeout and loss of prior evidence are in the trace..
#### Turn 1
User request: Покажи научные источники по пищевым отходам и ограничения переноса BMP.
Tools: search_substrate_profiles=ok, compare_scientific_studies=ok, verify_scientific_sources=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=ok; checked=False; outcome=not recorded; failed checks=none recorded; diagnostics=selection: Provider unreachable or invalid JSON: TimeoutError, v9_tool_selection: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: Модель не завершила проверенный краткий вывод. Сохранены доступные результаты инструментов. |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены. |  | Какова масса партии в килограммах?
Persisted state facts: {"material": "food_waste"}

### D23 (automated non-pass)
Expected: Do not infer that 30 C is non-optimal from one literature reference; evaluate payback only with heating inputs/costs.
Root-cause assessment: Process evidence returned missing heating inputs; final still said 30 C was below optimum (35 C), with temperature_not_optimum; verification was checked=false. Categories: F/H; unsupported assertion and unchecked verification are confirmed historical facts; see current-code D04 guard recheck below..
#### Turn 1
User request: 5 кг пищевых отходов, температура 30 градусов. Окупится ли повышение температуры?
Tools: assess_process_evidence=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=ok; checked=False; outcome=not recorded; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Окупаемость повышения температуры не определена. |  | Температура опубликованного опыта, не уставка: 35 °C (литературные данные). |  | Недостаточно данных о затратах и выгодах. Температура 30°C ниже оптимальной (35°C). |  | heating_missing |  | temperature_not_optimum |  | Какие затраты связаны с повышением температуры?
Persisted state facts: {"material": "food_waste", "quantity": 5.0, "unit": "kg"}

## Stage 9 D04 manual-review failure

### Turn 1
User request: В реакторе 30 градусов. Стоит ли повышать температуру?
Tools: assess_process_evidence=ok
Saved Qwen draft: not separately persisted.
Verifier: status=ok; checked=False; failed checks=none.
Displayed final answer: Не рекомендуется повышать температуру без дополнительной информации о нагрузке и эффективности нагрева.

Температура 30°C не оптимальна, но недостаточно данных для оценки экономической выгоды.

Неизвестны затраты на нагрев

Неизвестны потери тепла

Какова масса нагреваемого вещества и его теплоемкость?

Manual review says scientific_correctness=false because the displayed answer asserted that 30 C was non-optimal without evidence.
Current source review: `validate_synthesis` rejects unsupported optimum language as `temperature_optimum_not_established` (`src/agent/verification9.py`, around lines 203-209); `may_synthesize` requires checked and all-checks-passed verification for status=ok (around lines 118-120). Two existing tests cover the exact 30 C claim and checked=false synthesis suppression. These defenses passed a targeted deterministic rerun (2 passed); actual Qwen/active Dashboard replay remains NOT RUN due the RAM gate.

## Prior real-Qwen acceptance records (all scenarios)

### onion_peel - FAIL
Expected: Check literature profile before giving a range; distinguish literature estimate from measurement.
Root-cause assessment: No science tool. NLU intent process_guidance. Unsupported 0.5-1.2 m3 draft was rejected; synthesis timed out; final said numeric results failed validation. Categories: A/C/H/K; intent/tool miss and timeout in trace..
#### Turn 1
User request: У меня 12 кг луковой шелухи и реактор 120 л. Можно ли дать предварительный диапазон метана по научным данным? Отдели литературную оценку от измерения.
Tools: none
Saved Qwen rejected draft(s): [{"conclusion": "На основании 12 кг луковой шелухи и реактора 120 л, диапазон метана может составлять 0.5–1.2 м³. Данные основаны на типичных выходах биогаза. Дополнительные факторы, такие как температура и pH, влияют на эффективность.", "explanation": "Ёмкость реактора влияет на объем биогаза, но точный выход зависит от условий брожения. Данные не подтверждены экспериментально.", "limitations": ["Неизвестны условия брожения", "Неизвестны затраты на обработку"], "next_question": "Какие условия брожения у вас будут использоваться?", "evidence_ids": [], "decision": "not_established"}]
Verifier: status=not_applicable; checked=False; outcome=not_applicable; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit, synthesis: Provider unreachable or invalid JSON: TimeoutError, v9_synthesis: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: Численные результаты не прошли проверку; подробности доступны в диагностике.
Persisted state facts: {"quantity": 12.0, "unit": "kg", "reactor_total_volume_l": 120.0}

### whey_economics - FAIL
Expected: Compute 25 x 40 = 1000 KZT gross sale offer and show only supported comparison; do not claim net profit.
Root-cause assessment: Market/science/economics tools ran, but saved state lacked sale_offer_amount. Two Qwen calls timed out; fallback omitted gross offer. Categories: B/K; missing sale fact in saved state confirmed; current parser postdates trace and needs a new replay..
#### Turn 1
User request: Молокозавод предлагает забрать 25 кг сыворотки по 40 тенге за кг. Стоит ли вместо этого направить её в биореактор? Посчитай только то, что подтверждается данными, перечисли неизвестные расходы.
Tools: get_market_prices=ok, assess_substrate_potential=needs_input, evaluate_partial_economics=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=ok; checked=True; outcome=passed; failed checks=none recorded; diagnostics=selection: Provider unreachable or invalid JSON: TimeoutError, synthesis: Provider unreachable or invalid JSON: TimeoutError, v9_tool_selection: Provider unreachable or invalid JSON: TimeoutError, v9_synthesis: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены. |  | Для объёма общего биогаза нужна доля метана на той же газовой базе. Объём метана не равен объёму всего биогаза.
Persisted state facts: {"material": "dairy_waste", "quantity": 25.0, "unit": "kg"}

### apple_pomace_profile - FAIL
Expected: Check local index and report exact/direct vs analog coverage.
Root-cause assessment: No tools; final claimed no suitable profile without lookup. Categories: A/C; lack of search is confirmed; global scientific absence is not..
#### Turn 1
User request: Для 10 кг сухого яблочного жмыха какой профиль из каталога научно подходит? Укажи, если это только ближайший аналог, и какие параметры не совпадают.
Tools: none
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=not_applicable; checked=False; outcome=not_applicable; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Нет подходящего профиля в каталоге для 10 кг сухого яблочного жмыха. Параметры не совпадают с доступными вариантами. |  | Нет данных о соответствующих параметрах для сухого яблочного жмыха в каталоге. Неизвестны расходы и условия использования. |  | Недостаток информации о параметрах и условиях использования |  | Какие параметры и условия использования сухого яблочного жмыха у вас есть?
Persisted state facts: {"quantity": 10.0, "unit": "kg"}

### horse_sawdust - FAIL
Expected: Explain that unknown component shares limit transfer and quantitative estimate; name missing fields.
Root-cause assessment: Substrate returned needs_input with no profile IDs or specific missing items; generic fallback. Categories: E/H/I; tool response lacks explanation, confirmed..
#### Turn 1
User request: Есть 6 кг конского навоза с опилками, но доли компонентов неизвестны. Какой профиль допустимо применить и можно ли честно дать диапазон метана?
Tools: assess_substrate_potential=needs_input
Saved Qwen rejected draft(s): [{"conclusion": "Профиль не определён из-за недостатка данных. Метан не может быть указан без знания долей компонентов и базы газа. Объём реактора влияет на потенциал биогаза, но его не указали.", "explanation": "Для оценки метана требуется информация о составе и условиях. Без данных о долях компонентов и базе газа невозможно определить диапазон метана.", "limitations": ["bmp_ml_g_vs", "ts_fraction"], "next_question": "Можно ли получить доли компонентов или данные о базе газа для уточнения метана?", "evidence_ids": [], "decision": "not_established"}, {"conclusion": "Профиль не определён из-за недостатка данных. Метан не может быть указан без знания долей компонентов и базы газа. Объём реактора влияет на потенциал биогаза, но его не указали.", "explanation": "Для оценки метана требуется информация о составе и условиях. Без данных о долях компонентов и базе газа невозможно определить диапазон метана.", "limitations": ["bmp_ml_g_vs", "ts_fraction"], "next_question": "Можно ли получить доли компонентов или данные о базе газа для уточнения метана?", "evidence_ids": [], "decision": "not_es
Verifier: status=ok; checked=True; outcome=passed; failed checks=none recorded; diagnostics=internal_parameter_name_in_prose.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены. |  | Для объёма общего биогаза нужна доля метана на той же газовой базе. Объём метана не равен объёму всего биогаза.

### broiler_litter - FAIL
Expected: Compare broiler/layer identity and explain transfer limitations, not economics.
Root-cause assessment: Intent economic_comparison; substrate needs_input plus economics; final did not address transfer. Categories: A/C; wrong intent and tool route confirmed..
#### Turn 1
User request: 9 кг подстилки бройлеров с соломой. Подходит ли профиль помёта кур-несушек, или такое перенесение требует оговорки?
Tools: assess_substrate_potential=needs_input, evaluate_partial_economics=ok
Saved Qwen rejected draft(s): [{"conclusion": "Не хватает данных о ёмкости для оценки совместимости профиля помёта кур-несушек с подстилкой из соломы. Без объёма или плотности невозможно определить пригодность переноса.", "explanation": "Для оценки требуется информация о ёмкости, которая отсутствует в предоставленных данных.", "limitations": ["volume_or_density:c1", "inoculum_volume_l"], "next_question": "Какова ёмкость или плотность подстилки из соломы в кг/м³?", "evidence_ids": [], "decision": "not_established"}, {"conclusion": "Не хватает данных о ёмкости для оценки совместимости профиля помёта кур-несушек с подстилкой из соломы. Без объёма или плотности невозможно определить пригодность переноса.", "explanation": "Для оценки требуется информация о ёмкости, которая отсутствует в предоставленных данных.", "limitations": ["volume_or_density:c1", "inoculum_volume_l"], "next_question": "Какова ёмкость или плотность подстилки из соломы в кг/м³?", "evidence_ids": [], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=passed; failed checks=none recorded; diagnostics=internal_parameter_name_in_prose, selection: Disallowed or repeated tool selection.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены. |  | Для объёма общего биогаза нужна доля метана на той же газовой базе. Объём метана не равен объёму всего биогаза.
Persisted state facts: {"material": "straw", "quantity": 9.0, "unit": "kg"}

### sewage_sludge - FAIL
Expected: Check exact sludge profile coverage and state local-index limits.
Root-cause assessment: Substrate needs_input without profile IDs/missing details; generic final. Categories: E/H/I; tool output gap confirmed; absence of all literature is not..
#### Turn 1
User request: Для 4 кг осадка городских очистных сооружений проверь научный каталог: есть ли применимый BMP профиль? Не подменяй его навозом.
Tools: assess_substrate_potential=needs_input
Saved Qwen rejected draft(s): [{"conclusion": "Нет применимого BMP профиля для 4 кг осадка городских очистных сооружений. Данные о метановом потенциале и других параметрах отсутствуют. Неизвестные расходы не позволяют определить экономическую целесообразность.", "explanation": "Для оценки BMP требуется информация о метановом потенциале, содержании твердых и влажных фракций, а также объеме реактора. Эти данные отсутствуют, что делает невозможной точную оценку.", "limitations": ["bmp_ml_g_vs", "ts_fraction"], "next_question": "Какой метановый потенциал у осадка городских очистных сооружений (в мл/г)?", "evidence_ids": [], "decision": "not_established"}, {"conclusion": "Нет применимого BMP профиля для 4 кг осадка городских очистных сооружений. Данные о метановом потенциале и других параметрах отсутствуют.", "explanation": "Для оценки BMP требуется информация о метановом потенциале, содержании твердых и влажных фракций, а также объеме реактора. Эти данные отсутствуют, что делает невозможной точную оценку.", "limitations": ["bmp_ml_g_vs", "ts_fraction"], "next_question": "Какой метановый потенциал у осадка городских о
Verifier: status=ok; checked=True; outcome=passed; failed checks=none recorded; diagnostics=internal_parameter_name_in_prose.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены. |  | Для объёма общего биогаза нужна доля метана на той же газовой базе. Объём метана не равен объёму всего биогаза.
Persisted state facts: {"material": "manure", "quantity": 4.0, "unit": "kg"}

### spent_grain - FAIL
Expected: Retain brewer spent-grain identity and explain wet/dry form differences.
Root-cause assessment: Search found profiles; assessment then said material identity missing; final asked what waste user had. Categories: B/G/H; bridge/state conflict confirmed by trace..
#### Turn 1
User request: У меня 11 кг пивной дробины. Что можно оценить по найденному профилю, а какие различия между влажной и сухой дробиной мешают точному выводу?
Tools: search_substrate_profiles=ok, assess_substrate_potential=needs_input, evaluate_partial_economics=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=insufficient_evidence; checked=False; outcome=insufficient_evidence; failed checks=none recorded; diagnostics=selection: Disallowed or repeated tool selection.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Вид сырья или состав смеси не определён. Без этого нельзя обоснованно выбрать TS, VS и BMP для численного сценария. |  | Какие именно отходы вы планируете сбраживать?
Persisted state facts: {"quantity": 11.0, "unit": "kg"}

### beet_vs_straw - FAIL
Expected: Compare two separate 3 kg cases.
Root-cause assessment: No tools; parser reported ambiguity despite two materials each bound to 3 kg. Categories: B; parser rejection confirms false ambiguity..
#### Turn 1
User request: Сравни только литературный потенциал метана для 3 кг свекловичного жома и 3 кг пшеничной соломы. Не делай вывод о прибыли без цен и затрат.
Tools: none
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=not recorded; checked=not recorded; outcome=not recorded; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Неясно, к каким параметрам относятся новые значения. Это неоднозначность назначения чисел, а не противоречие измерений. |  | Какое значение относится к сырью, а какое — к реактору?

### methane_fraction_missing - PASS
Expected: Explain that total biogas volume needs methane fraction; ask one useful clarification.
Root-cause assessment: No tools; final correctly explained missing fraction and asked a relevant question. Categories: PASS control..
#### Turn 1
User request: Газовый счётчик показал 0,20 м³ метана. Можно ли по этому числу узнать объём всего биогаза?
Tools: none
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=not_applicable; checked=False; outcome=not_applicable; failed checks=none recorded; diagnostics=selection: Invalid provider planning schema.
Displayed final answer: Нет, объём биогаза не может быть определён только по объёму метана, так как биогаз содержит другие компоненты. |  | Объём биогаза зависит от его состава, включая метан, углекислый газ и другие газы. Без информации о составе биогаза невозможно точно определить его объём. |  | Неизвестный состав биогаза |  | Отсутствие данных о других компонентах |  | Какой состав имеет биогаз в вашем случае?

### raw_biogas_price - FAIL
Expected: Explain natural-gas tariff is not a raw-biogas sale price; identify quality, cleanup and market conditions.
Root-cause assessment: Market/history/science/economics tools ran; selection timed out; final asked for feedstock and omitted commodity distinction. Categories: C/H/K; timeout and fallback loss confirmed..
#### Turn 1
User request: Тариф природного газа в моей таблице — 35 KZT/м³. Можно ли оценить сырое биогазовое топливо по той же цене или нужны очистка, состав и отдельная цена продажи?
Tools: get_market_prices=ok, get_price_history=ok, assess_substrate_potential=needs_input, evaluate_partial_economics=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=insufficient_evidence; checked=False; outcome=insufficient_evidence; failed checks=none recorded; diagnostics=selection: Provider unreachable or invalid JSON: TimeoutError, v9_tool_selection: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Вид сырья или состав смеси не определён. Без этого нельзя обоснованно выбрать TS, VS и BMP для численного сценария. |  | Какие именно отходы вы планируете сбраживать?

### conditional_bmp_arithmetic - FAIL
Expected: Calculate 0.6 kg VS x 250 mL/g VS = 0.15 m3 as an explicit assumption, independent of material profile.
Root-cause assessment: Substrate returned needs_input because material unknown; no arithmetic result. Categories: C/D; deterministic calculation was routed through a substrate-dependent tool..
#### Turn 1
User request: Для условного примера: VS масса 0,6 кг, а BMP я задаю как допущение 250 мл CH₄/г VS. Посчитай арифметический потенциал и не называй BMP измеренным.
Tools: assess_substrate_potential=needs_input
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=insufficient_evidence; checked=False; outcome=insufficient_evidence; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Вид сырья или состав смеси не определён. Без этого нельзя обоснованно выбрать TS, VS и BMP для численного сценария. |  | Какие именно отходы вы планируете сбраживать?
Persisted state facts: {"vs_mass_kg": 0.6}

### sunflower_husks - FAIL
Expected: Check exact profile coverage and distinguish local index from wider literature.
Root-cause assessment: Search returned dossiers without sunflower husks; synthesis timed out; final generic numeric-failure message. Categories: E/H/K; retrieval and timeout confirmed..
#### Turn 1
User request: Пять килограммов лузги подсолнечника: проверь точное покрытие научными профилями и скажи, если оценка потребует переноса с другого сырья.
Tools: search_substrate_profiles=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=not_applicable; checked=False; outcome=not_applicable; failed checks=none recorded; diagnostics=synthesis: Provider unreachable or invalid JSON: TimeoutError, v9_synthesis: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: Численные результаты не прошли проверку; подробности доступны в диагностике.
Persisted state facts: {"quantity": 5.0, "unit": "kg"}

### sludge_ts_missing_vs - FAIL
Expected: Use 30 kg and measured TS 18% for dry-solids calculation if supported; do not infer VS/BMP without data.
Root-cause assessment: Assessment treated material/quantity as missing; no partial TS calculation. Categories: B/C/D; state/tool bridge loss and no partial arithmetic in trace..
#### Turn 1
User request: У меня 30 кг обезвоженного осадка, лабораторно измеренный TS равен 18%. VS/TS не измеряли. Какую часть расчёта метана можно выполнить без выдумывания VS?
Tools: assess_substrate_potential=needs_input
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=insufficient_evidence; checked=False; outcome=insufficient_evidence; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Вид сырья или состав смеси не определён. Без этого нельзя обоснованно выбрать TS, VS и BMP для численного сценария. |  | Какие именно отходы вы планируете сбраживать?
Persisted state facts: {"quantity": 30.0, "unit": "kg"}

### volume_without_density - PARTIAL
Expected: State that 5 m3 cannot establish mass/BMP without density; label any transfer as hypothetical.
Root-cause assessment: Tool returned 102.92-144.86 m3 hypothetical CH4; final omitted transferred density/mass and direct limitation. Categories: H/I; result was labeled hypothetical but assumptions were underexplained..
#### Turn 1
User request: Загружаю 5 м³ жидкого коровьего навоза в реактор объёмом 6 м³. Достаточно ли этого, чтобы определить массу сырья и BMP?
Tools: assess_substrate_potential=ok
Saved Qwen rejected draft(s): [{"conclusion": "5 м³ жидкого навоза КРС не достаточно для точного определения массы сырья и BMP без дополнительных данных о плотности и составе.", "explanation": "Объём реактора 6 м³ не влияет на расчёт массы и BMP, так как загрузка не заполнена. Для точных значений требуется плотность и состав навоза.", "limitations": ["density_kg_l", "inoculum_volume_l"], "next_question": "Какова плотность жидкого навоза КРС в кг/л?", "evidence_ids": ["s1.methane", "s1.vs", "s1.biogas", "s1.vessel", "s2.vessel"], "decision": "not_established"}, {"conclusion": "5 м³ жидкого навоза КРС недостаточно для точного определения массы сырья и BMP без плотности и состава.", "explanation": "Объём реактора 6 м³ не влияет на расчёт, так как загрузка не заполнена. Требуется плотность и состав навоза для массы и BMP.", "limitations": ["density_kg_l", "inoculum_volume_l"], "next_question": "Какова плотность жидкого навоза КРС в кг/л?", "evidence_ids": ["s1.methane", "s1.vs", "s1.biogas", "s1.vessel", "s2.vessel"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=passed; failed checks=none recorded; diagnostics=internal_parameter_name_in_prose, ungrounded_quantity_or_wrong_unit.
Displayed final answer: Предварительная оценка по доступным и проверенным данным: |  | Навоз КРС (отдельный сценарий s1): потенциал метана: 102.92–144.86 м³ CH₄ (условный сценарий). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены. |  | Номинальная ёмкость ограничивает загрузку, но сама по себе не задаёт потенциал метана; нужны рабочий объём, инокулят, вода и газовое пространство.
Persisted state facts: {"material": "cattle_manure", "quantity": 5.0, "unit": "m3", "reactor_total_volume_l": 6000.0}

### conditional_electricity - FAIL
Expected: Compute 0.10 x 9.97 x 0.30 = 0.2991 kWh as a conditional calculation.
Root-cause assessment: Energy, substrate, economics, process tools called; final asked material and omitted arithmetic. Categories: C/D/H; unrelated substrate requirement blocked explicit arithmetic..
#### Turn 1
User request: Условный инженерный расчёт: 0,10 м³ CH₄, LHV 9,97 кВт·ч/м³, электрический КПД генератора 30%. Сколько электричества получится теоретически? Это не измерение установки.
Tools: estimate_process_energy=ok, assess_substrate_potential=needs_input, evaluate_partial_economics=ok, assess_process_evidence=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=insufficient_evidence; checked=False; outcome=insufficient_evidence; failed checks=none recorded; diagnostics=selection: Disallowed or repeated tool selection.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Вид сырья или состав смеси не определён. Без этого нельзя обоснованно выбрать TS, VS и BMP для численного сценария. |  | Какие именно отходы вы планируете сбраживать?
Persisted state facts: {"quantity": 0.1, "unit": "m3"}

### stale_price - FAIL
Expected: Display saved 20.39 KZT/kWh, publication 2026-10-09, age 38 days, stale/not current.
Root-cause assessment: Market tool returned fields; final generic numeric-validation failure. Categories: H/I; valid tool output lost during synthesis/fallback..
#### Turn 1
User request: Проверь сохранённые цены на электроэнергию для Караганды: есть ли свежая подтверждённая цена, какова дата публикации, возраст и можно ли считать её текущей?
Tools: get_market_prices=ok
Saved Qwen rejected draft(s): [{"conclusion": "Сохранённая цена на электроэнергию для Караганды: 20.39 KZT/kWh, дата публикации 2026-10-09, возраст 38 дней, не считается текущей. Дата действия 2026-09-30. Дополнительные цены: 33.51 и 38.87 KZT/kWh, но не считаются текущими.", "explanation": "Цены не подтверждены как текущие, так как дата действия устарела. Данные из официальных источников, но не актуальны для текущего периода.", "limitations": ["Неизвестна дата публикации второй цены", "Не подтверждено, что цена актуальна"], "next_question": "Какие дополнительные источники могут подтвердить актуальность цен на электроэнергию в Караганде?", "evidence_ids": [], "decision": "not_established"}, {"conclusion": "Сохранённая цена на электроэнергию для Караганды: 20.39 KZT/kWh, дата публикации 2026-10-09, возраст 38 дней, не считается текущей. Дата действия 2026-09-30. Дополнительные цены: 33.51 и 38.87 KZT/kWh, но не считаются текущими.", "explanation": "Цены не подтверждены как текущие, так как дата действия устарела. Данные из официальных источников, но не актуальны для текущего периода.", "limitations": ["Неизвестна
Verifier: status=not_applicable; checked=False; outcome=not_applicable; failed checks=none recorded; diagnostics=ungrounded_quantity_or_wrong_unit.
Displayed final answer: Численные результаты не прошли проверку; подробности доступны в диагностике.

### digestate_value - FAIL
Expected: Do not assign NPK price without digestate quality and legality; explain missing evidence.
Root-cause assessment: Legacy synchronous /messages; analysis 8.5; response discussed gas market/cattle risks instead. Categories: A/C/J; wrong route/runtime and unrelated topic confirmed..
#### Turn 1
User request: После переработки останется 80 л дигестата. Можно ли считать его удобрением и приписать ему цену минерального NPK без анализа состава и разрешений?
Tools: get_market_prices=needs_input, verify_scientific_sources=ok, assess_scientific_risks=ok
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=insufficient_evidence; checked=False; outcome=insufficient_evidence; failed checks=none recorded; diagnostics=tool_selection: Provider unreachable or invalid JSON: TimeoutError.
Displayed final answer: В регионе нет подходящих сохранённых цен; нужен проверенный импорт или успешное обновление источника. |  | Local citation audit only. No live fetch or full-text verification performed in this call. |  | Qualitative risk screen; inhibition cannot be quantified without measurements. |  | Ошибка языковой модели прервала исследование; доступные вычисления сохранены.
Persisted state facts: {"quantity": 80.0, "unit": "L"}

### measured_gas_balance - FAIL
Expected: Compute measured 0.42 x 58% = 0.2436 m3 CH4, label measurement balance, not BMP.
Root-cause assessment: Substrate needs_input; parser treated 0.42 as feed volume; final asked material. Categories: B/C/D; role-binding and missing arithmetic path confirmed..
#### Turn 1
User request: Мои приборы измерили 0,42 м³ сырого биогаза и 58% CH₄ на той же сухой базе. Рассчитай измеренный объём CH₄, укажи, что это баланс измерений, а не BMP.
Tools: assess_substrate_potential=needs_input
Saved Qwen rejected draft(s): not separately persisted.
Verifier: status=insufficient_evidence; checked=False; outcome=insufficient_evidence; failed checks=none recorded; diagnostics=none recorded.
Displayed final answer: Для научной оценки не хватает исходных данных: |  | Вид сырья или состав смеси не определён. Без этого нельзя обоснованно выбрать TS, VS и BMP для численного сценария. |  | Какие именно отходы вы планируете сбраживать?
Persisted state facts: {"quantity": 0.42, "unit": "m3"}

### temperature_transfer - PASS
Expected: Do not recommend raising 37 to 40 C without process evidence.
Root-cause assessment: Process-evidence tool ran; cautious reply; one relevant question. Categories: PASS control..
#### Turn 1
User request: Температура содержимого сейчас 37 °C. Есть ли основание поднять её до 40 °C именно в моём процессе, если я не сообщал pH, состав сырья, теплопотери и стабильность?
Tools: assess_process_evidence=ok
Saved Qwen rejected draft(s): [{"conclusion": "Нет оснований поднимать температуру без данных о составе сырья, pH, теплопотерях и стабильности. Недостающие параметры влияют на оптимальность и безопасность процесса.", "explanation": "Роль ёмкости: обеспечивает равномерное распределение тепла и предотвращает локальные перегревы.", "limitations": ["heating_missing"], "next_question": "Можно ли определить оптимальную температуру без полного состава сырья и теплопотерь?", "evidence_ids": [], "decision": "not_established"}, {"conclusion": "Нет оснований поднимать температуру без данных о составе сырья, pH, теплопотерях и стабильности. Недостающие параметры влияют на оптимальность и безопасность процесса.", "explanation": "Роль ёмкости: обеспечивает равномерное распределение тепла и предотвращает локальные перегревы.", "limitations": ["heating_missing"], "next_question": "Можно ли определить оптимальную температуру без полного состава сырья и теплопотерь?", "evidence_ids": [], "decision": "not_established"}]
Verifier: status=not_applicable; checked=False; outcome=not_applicable; failed checks=none recorded; diagnostics=internal_parameter_name_in_prose, temperature_optimum_not_established.
Displayed final answer: Качественный анализ по доступным данным: |  | Сообщённая температура 37 °C сама по себе не обосновывает её повышение. Подогрев повышает энергозатраты, влияет на скорость процесса и аммиачный риск; оптимум без данных о сырье, инокуляте, pH и динамике газа не определён. Следует оценить теплопотери и устойчивость процесса до изменения режима. |  | Какое сырьё и инокулят сейчас находятся в реакторе?

### batch_workflow - IN PROGRESS / FAIL SO FAR
Expected: Save 4 kg straw as confirmed; estimate only if catalog supports it; preserve vessel/feed roles.
Root-cause assessment: One of five turns only. Mass persisted; catalog had no numeric straw profile; reply focused on vessel, no methane estimate. Categories: E/I; coverage limit and incomplete workflow confirmed; remaining turns unrun..
#### Turn 1
User request: Начинаем новую партию: 4 кг измельчённой пшеничной соломы, реактор 60 л. Оцени потенциальный метан и сохрани массу как подтверждённый ввод.
Tools: assess_substrate_potential=needs_input
Saved Qwen rejected draft(s): [{"conclusion": "Метановый потенциал не определён из-за недостающих данных. Реактор ёмкостью 60 л ограничивает загрузку, но не влияет на метановый выход. Масса соломы 4 кг подтверждена.", "explanation": "Реакторная ёмкость ограничивает загрузку, но метановый выход зависит от других факторов, таких как состав субстрата и условия брожения.", "limitations": ["bmp_ml_g_vs", "ts_fraction"], "next_question": "Уточните данные о содержании VS и BMP для соломы.", "evidence_ids": ["s1.vessel"], "decision": "not_established"}, {"conclusion": "Метановый потенциал не определён из-за недостающих данных. Реактор ёмкостью 60 л ограничивает загрузку, но не влияет на метановый выход. Масса соломы 4 кг подтверждена.", "explanation": "Реакторная ёмкость ограничивает загрузку, но метановый выход зависит от других факторов, таких как состав субстрата и условия брожения.", "limitations": ["bmp_ml_g_vs", "ts_fraction"], "next_question": "Уточните данные о содержании VS и BMP для соломы.", "evidence_ids": ["s1.vessel"], "decision": "not_established"}]
Verifier: status=ok; checked=True; outcome=passed; failed checks=none recorded; diagnostics=internal_parameter_name_in_prose.
Displayed final answer: Предварительная оценка по доступным и проверенным данным: |  | Солома: номинальная ёмкость (ограничивает загрузку, не задаёт метан): 60 л (по сообщённым данным). |  | Это предварительные сценарии. Фактическая выработка, прибыль и безопасность установки не установлены. |  | Номинальная ёмкость ограничивает загрузку, но сама по себе не задаёт потенциал метана; нужны рабочий объём, инокулят, вода и газовое пространство. |  | Для объёма общего биогаза нужна доля метана на той же газовой базе. Объём метана не равен объёму всего биогаза.
Persisted state facts: {"reactor_total_volume_l": 60.0, "material": "straw", "quantity": 4.0, "unit": "kg"}

## Shared root-cause families and A-K classification

| Shared mechanism | Trace examples | Evidence | Minimal component to validate/fix | Status |
|---|---|---|---|---|
| Parameter role/unit binding | D12, D19; beet/straw, conditional arithmetic, sludge TS, measured gas, spent grain, whey offer | NLU errors, state facts and tool contexts show wrong role, omitted value or kg/m3 mismatch | NLU binder -> typed context -> explicit calculation tools | Confirmed in listed historical records; current parser must be replayed before any re-fix
| Planner/tool completeness and stop conditions | D07-D10,D18,D22; onion/apple, conditional electricity | Requested science/economics/profile tools missing or an unnecessary extra search timed out | Runtime9 required-tool matrix and stop condition | Behavior confirmed; shared code-level cause needs current replay
| Fallback loses valid evidence | D03,D07,D22; stale price, onion | successful tool output coexists with one-sided/generic final | evidence-preserving fallback composer | Behavior confirmed; different branches may have different causes
| Verifier has strict and uncovered areas | D05,D11,D15,D19,D23,D04 | rejected grounded values and historical unchecked qualitative claim | typed reference model plus checked gate and claim validation | Defects evidenced; current temperature/check gates exist and deterministic tests pass
| Qwen timeout/loop cost | D03,D07,D11,D22; whey/raw gas/sunflower | Provider logs have timeout phase/error | runtime budget, context and bounded repair loop | Timeout confirmed; causal contribution of context size remains a hypothesis
| Sparse local profile coverage | horse/sludge/sunflower/straw/spent grain | `needs_input` or no direct profile | catalog coverage metadata plus precise missing-data answer | Local coverage limit confirmed; no conclusion about all global literature
| Runtime/route mismatch | old 470/114 answer and legacy digestate | stale process source and legacy `/messages` route documented in audit | endpoint/runtime deployment | Historically confirmed; current browser path not replayed

| Class | Examples |
|---|---|
| A. Request understanding | onion intent; broiler intent; D23/D04 optimum language |
| B. Parameter extraction | TS/VS/BMP; quantities for two materials; measured gas role; offer value |
| C. Tool selection | missing science/economics/profile; substrate tool used for simple arithmetic |
| D. Calculations | missing explicit products; unit/fraction conversion |
| E. Scientific database | sparse direct profile coverage |
| F. LLM hallucination | profitability ranking, yield conversion, inhibition and optimum claims |
| G. Context | corrections/new batches and state mutation such as D10 generic material |
| H. Verification | grounded quantity false rejection; unchecked qualitative prose in old D04/D23 |
| I. Synthesis/formatting | generic fallback, omitted alternatives, internal keys |
| J. Frontend/backend | stale service and legacy route documented |
| K. Performance | model selection/synthesis timeouts |

## Already protected or not current until reproduced

- Capacity preflight and visible warning have deterministic endpoint tests in prior audit; old 470/114 traces predate the fix.
- Current D04 protections and their focused tests passed in this session; real model/browser still not verified.
- Sale-offer parsing and explicit arithmetic have deterministic code/tests, but older failures predate changes. Do not re-edit without current reproduction.
- Live Ollama cancellation remains INCONCLUSIVE from previous one-shot trial; a CANCELLED job alone is not proof inference stopped.
- No application code, DB, BMP bundle, historic trace or holdout was changed.

## Evidence boundaries

- The user-facing saved answer is authoritative for what the user saw. Missing intermediate prose is not fabricated.
- Existing traces are development/acceptance records and already used; they are not an untouched holdout.
- Historical `provider=offline` records prove some actual qwen3:8b generation, not successful generation for every phase.
- The current model baseline and browser validation are BLOCKED/NOT RUN until the case-specific memory gate passes.

## 2026-11-09 update — BMP concept routing remediation and live replay

This section supersedes the earlier statement above that the current model baseline was still waiting only for a three-point memory gate. The gate passed, but the first runtime load crossed it; no valid scientific answer was produced.

### Confirmed root cause in the historical BMP trace

The failure was not just a Qwen wording problem. Deterministic NLU had mapped the concept question to `methane_yield`; Runtime 9 then made `assess_substrate_potential` mandatory. The public runtime manifest did not include `search_scientific_sources`, so the relevant explanation tool was unavailable to model planning. The `needs_input` result then led to a fallback asking for material and mass. The saved trace therefore shows a route/manifest/fallback contract error before final synthesis.

### Minimal general fix and deterministic regression evidence

The fix adds request-kind classification for scientific explanation, explicit arithmetic, batch assessment, reactor management, economics, follow-up, correction and uncertainty. Concept questions require local source search without requiring a batch assessment; explicit `VS × BMP` calculations remain a separate route. `search_scientific_sources` is now available in the Runtime manifest and treated as informational by verification. The local reviewed catalogue now contains bounded explanations for BMP versus actual reactor yield, TS/VS, temperature, HRT versus batch duration, and nominal versus working vessel volume. Existing language and legacy-route behavior for English/Kazakh temperature prompts and a context-provided BMP calculation was restored after the initial targeted test exposed regressions.

Changed components: `src/agent/dialogue_types.py`, `src/agent/nlu.py`, `src/agent/runtime9.py`, `src/agent/tool_manifest.py`, `src/agent/verification9.py`, `src/recommendations/retrieval.py`, `data/knowledge/imported/scientific_concepts_20261109.json`, and `tests/test_scientific_question_routing.py`.

Command: `pytest -q tests/test_scientific_question_routing.py tests/test_stage9_runtime.py tests/test_stage9_verification.py tests/test_conversation.py tests/test_stage9_jobs.py --basetemp .pytest_scientific_routing_after_20261109` — **135 passed, 0 failed** in 27.05 s; one Starlette/httpx deprecation warning. This suite exercises the actual FastAPI Dashboard jobs handler with a deterministic fixture provider. It does not prove real-Qwen behavior or browser rendering.

### Guarded real-Qwen attempt: blocked, not scoreable

Three preflight samples at 23:02:58, 23:03:10 and 23:03:21 +05:00 passed: 7,813–7,914 MiB available RAM, about 20.9 GiB commit headroom, RTX 3070 Laptop at 56 °C, 728/8,192 MiB VRAM, no HW/SW thermal slowdown, Ollama 0.40.15, and no loaded model/request. An isolated backend (PID 11548, port 8775, copied SQLite, `qwen3:8b`, context 8192, 16 GPU layers, online research disabled) was launched. Existing Dashboard PID 3412 was not touched.

During the first job, available RAM fell from 7,900.2 MiB to 4,773.0 MiB while Ollama started llama-server; the local 6,246.4 MiB gate was crossed. GPU was 58 °C, VRAM 3,088/8,192 MiB, thermal slowdown inactive. The harness cancelled the job; the database confirms `CANCELLED`, `cancel_requested=1`, and no saved reply. Ollama logged `client connection closed before llama-server finished loading, aborting load`, `Load failed ... context canceled`, and HTTP 499. `/api/ps` was empty afterward, RAM recovered to 7,803 MiB, GPU was 57 °C / 710 MiB VRAM, and only the QA PID was stopped. This was not a CUDA crash, but it does not establish a completed inference.

The intended question was: «Чем лабораторный BMP отличается от фактического выхода метана в реакторе? Объясни, почему результат BMP нельзя напрямую считать измеренным выходом конкретной установки». The saved job message confirms PowerShell's stdin pipeline replaced Cyrillic text with `?` before the HTTP request. This independent test-harness encoding defect makes the request invalid for scientific scoring even apart from resource cancellation. Both facts and Ollama log excerpts are preserved in `reports/scientific_qwen_baseline_20261109.json`. No Qwen answer, verifier result, tool trace, mixed calculation, or 5→6 kg multi-turn result is available; those scenarios were not run after the gate tripped. No browser E2E or holdout was run.

### Status and next action

Deterministic routing fix: **PASS for the tested API-level regressions**. Real-Qwen acceptance of the fix: **BLOCKED / NOT RUN**. Next live attempt requires a verified UTF-8 request transport, a fresh three-sample preflight, and enough user-controlled memory headroom to keep available RAM at or above 6,246.4 MiB throughout Qwen loading. The single observed ~3,127 MiB decrease is a local measurement, not a universal model requirement. Project readiness remains **NOT READY**.

### 2026-11-10 — test harness follow-up

The PowerShell stdin path is now replaced for new runs by `evaluations/real_qwen_baseline_runner.py`, which reads a UTF-8 JSON fixture, rejects damaged text before submission, compares the exact UTF-8 bytes after the Dashboard job is accepted, and has a local HTTP byte-echo regression. RU, KK, EN, `әғқңөұүһі`, math symbols, units, and `CH₄` are covered. The earlier attempt remains invalid and is not retroactively scored.

The guarded runner now separates cold-start admission from runtime cancellation. The temporary admission floor for the observed QA profile (`qwen3:8b`, context 8192, 16 GPU layers, batch/ubatch 64) is 9,373.6 MiB: the old 6,246.4 MiB runtime reserve plus the single observed 3,127.2 MiB available-RAM drop during the failed load. This is a provisional local guard derived from one failed attempt, not a model-wide requirement. The last 3-sample preflight on 2026-11-09 recorded 6,566.5–6,605.0 MiB free RAM and 19,731.5–19,783.0 MiB commit headroom; GPU was 58 °C, 832–838 MiB VRAM, with slowdown inactive and Ollama idle. Admission was **BLOCKED** by the provisional cold-start floor, so no QA backend, model load, or inference was started. The owner of the earlier RAM drop remains unknown because that attempt did not capture PID-level memory deltas.

Infrastructure regression command: `pytest -q tests/test_scientific_question_routing.py tests/test_stage9_runtime.py tests/test_stage9_verification.py tests/test_conversation.py tests/test_stage9_jobs.py tests/test_real_qwen_baseline_runner.py --basetemp .pytest_qwen_infra_final_20261109` — **152 passed, 0 failed**, one existing Starlette/httpx deprecation warning. Python compilation and `real_qwen_baseline_runner.py validate` also passed. The validation command did not invoke inference. Ollama 0.40.15 reported `OLLAMA_NUM_PARALLEL=1`, keep-alive 5m, context env default 0; the QA request profile explicitly uses `num_ctx=8192`. No global Ollama setting or system configuration was changed.

The prior “Next action” statement requiring only the 6,246.4 MiB runtime floor is superseded for cold starts by this profile-specific admission gate. Any future live run still requires a fresh passing 3-sample preflight and the explicit `--allow-real-inference` switch. Model-ready, generation, answer quality, Browser E2E, and independent holdout remain **NOT RUN**. Quality acceptance remains **BLOCKED / NOT READY**.

### 2026-11-10 — profile comparison and memory blocker

A new static resource study is recorded in `reports/qwen_resource_optimization_20261110.md`. The current QA path forces context 8192, batch64, 16 GPU layers, and 6 threads, while the Ollama startup log selected a 4096 context default. A version-matched historical run with auto GPU placement and batch512 fully placed the Qwen model in VRAM and generated two responses, but its conceptual answer failed the rubric; the third request did not complete after the RAM guard and an 86°C sample. This evidence supports a candidate for further resource testing, not a quality recommendation.

The latest current-machine preflight was **BLOCKED** at 4,625.1–4,646.7 MiB free RAM. The Ollama desktop app process (PID 21768) used about 3,600 MiB working set; the Dashboard port 8766 was not listening. No application was stopped, no global configuration was changed, and no real-Qwen request was sent. The profile matrix is in `evaluations/qwen_resource_profiles_20261110.json`; new generation and quality comparisons remain **NOT RUN**.
