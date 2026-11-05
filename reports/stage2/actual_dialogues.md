# Реальные диалоги проверки 28.10.2026

Запросы Ollama фактически выполнены. Пример бутылки 902 — входы из train, не независимый эксперимент.

## 1. live local LLM; user-request example

**Пользователь:**

У меня 80 литров чернозёма и реактор на 90 литров. Выгоднее продать чернозём или переработать в биогаз?

**Вызовы Python:** analyze_substrate [ok] → predict_bmp [unsupported] → calculate_methane [needs_input] → calculate_profitability [needs_input]

**Ответ:**

Сырьё: чернозём. Почва не подтверждена как продуктивный субстрат этой системой. Нет BMP-данных или режимов для чернозёма; численный ML-прогноз отклоняется. Численный прогноз Hafner для этого материала отклоняется.

Сравнение пока невозможно. Задайте количество, цены, дату, валюту, долю извлечения и все затраты партии (включая явные нули).

Для потенциального метана нужны BMP с единицами, измеренная масса VS и условия приведения газа.

Для сравнения нужны: масса партии, обоснованный потенциал метана и условия приведения, доля извлечения, цены сырья и метана, затраты на подготовку/нагрев/эксплуатацию, валюта и дата цен. Полный список полей доступен с --json.

Литры сырья не равны килограммам: измерьте массу или задайте density_kg_l. Номинальный объём реактора не задаёт безопасный рабочий объём.

Источники:
- FAO Global Soil Partnership, Fifth Plenary (June 2017), GSPPA V/2017/3: https://www.fao.org/fileadmin/user_upload/GSP/Fifth_plenary/en/GSPPA_V_2017_3.pdf

## 2. live hybrid agent; incomplete measured inputs

**Пользователь:**

Оцени BMP пшеничной соломы

**Вызовы Python:** analyze_substrate [ok] → predict_bmp [needs_input]

**Ответ:**

Сырьё: пшеничная солома. Общий эталонный субстрат Hafner; не все партии соломы эквивалентны. Категория есть в обучении; применимость конкретной партии ещё не подтверждена.

Для научного BMP укажите измеренные c_vs_sub_m, c_vs_sub_f, c_vs_inoc, ISR. VS — г/г влажного материала; ISR — отношение масс VS. Эталонную VS нельзя назначать произвольно.

Нужны данные: c_vs_sub_m, c_vs_sub_f, c_vs_inoc, ISR. Ответьте JSON-объектом или полями имя=значение; строки с пробелами — в кавычках.

Источники:
- Hafner et al. — Reliable biochemical methane potential testing (2026), original repository and dictionary: https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP

## 3. live same session; real train-bottle inputs, not independent validation

**Пользователь:**

{
  "substrate": "Wheat straw",
  "c_vs_sub_m": 0.9041,
  "c_vs_sub_f": 0.872,
  "c_vs_inoc": 0.02213,
  "ISR": 1.915
}


**Вызовы Python:** analyze_substrate [ok] → predict_bmp [ok]

**Ответ:**

Сырьё: пшеничная солома. Общий эталонный субстрат Hafner; не все партии соломы эквивалентны. Категория есть в обучении; применимость конкретной партии ещё не подтверждена.

Лабораторный BMP: 279.4 мл CH₄/г VS (SubstrateMedian). Это потенциал, не фактический выход газа. 90% интервал не установлен; перенос на вашу установку не подтверждён.

Источники:
- Hafner et al. — Reliable biochemical methane potential testing (2026), original repository and dictionary: https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP

## 4. legacy ML loading, deterministic tool mode

**Пользователь:**

Оцени BMP

**Вызовы Python:** analyze_substrate [ok] → predict_bmp [ok]

**Ответ:**

В этом ответе LLM не используется. Работает ограниченный расчётный режим, не языковая модель.

Сырьё: пшеничная солома. Общий эталонный субстрат Hafner; не все партии соломы эквивалентны. Категория есть в обучении; применимость конкретной партии ещё не подтверждена.

Лабораторный BMP: 392.656 мл CH₄/г VS (CatBoost). Это потенциал, не фактический выход газа. 90% интервал не установлен; перенос на вашу установку не подтверждён.

Источники:
- Hafner et al. — Reliable biochemical methane potential testing (2026), original repository and dictionary: https://github.com/AU-BCE-EE/Hafner-2026-IL-BMP
