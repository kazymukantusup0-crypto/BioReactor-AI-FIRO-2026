from pathlib import Path
p=Path('README.md');s=p.read_text(encoding='utf-8')
if '## Dashboard и Smart Agent v7.7' not in s:
 s+='\n\n## Dashboard и Smart Agent v7.7\n\nЕдиный раздел «Сырьё и смеси», короткие ответы по текущему вопросу, память состава и переключение Simple/Scientific. Старые ссылки перенаправляются в объединённый раздел; прежние backend API и модели сохранены.\n\nЗапуск: python main.py dashboard --port 8765 --no-scheduler. Адрес: http://127.0.0.1:8765/dashboard/#/substrates.\n\n[Инструкция](docs/smart_dashboard.md) · [Отчёт, тесты и измерения](reports/stage7_7_smart_agent_dashboard.md).\n'
 p.write_text(s,encoding='utf-8')
