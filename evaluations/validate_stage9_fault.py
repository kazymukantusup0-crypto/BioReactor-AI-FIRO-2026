"""Explicitly injected TOOL fault; model generation and calculations remain real."""
import json
import sys
import stage9_smoke
stage9_smoke.BASE='http://127.0.0.1:8771'
sys.stdout.reconfigure(encoding='utf-8')
row=stage9_smoke.run('Есть 6 кг пищевых отходов. Оцени метан и ценность энергии, используя доступные научные данные.')
reply=row['result'].get('reply') or {};tools=reply.get('tools',[])
checks={'actual_qwen3_8b':any(p.get('model')=='qwen3:8b' and p.get('actual_generation') for p in reply.get('provider_status',[])),
        'injected_fault_visible':any(t['tool']=='assess_substrate_potential' and t['status']=='error' for t in tools),
        'alternative_selected_by_model':any(t['tool']=='recover_local_scientific_analysis' and t['status']=='ok' for t in tools),
        'qwen_synthesis':reply.get('technical_metadata',{}).get('final_author')=='qwen_verified'}
row.update(checks=checks,scope='Controlled adapter failure, not a spontaneous external-source outage. No model responses were mocked.')
(stage9_smoke.ROOT/'reports/stage9/tool_failure_live.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks))
