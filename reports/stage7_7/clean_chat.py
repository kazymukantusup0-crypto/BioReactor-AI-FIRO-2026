from pathlib import Path
p=Path('frontend/src/pages/Chat.tsx');s=p.read_text(encoding='utf-8').replace('<Badge tone="green">Python tools</Badge>','').replace('Ollama + Python','Локальная модель').replace('Только Python · без LLM','Расчёт без языковой модели');p.write_text(s,encoding='utf-8')
