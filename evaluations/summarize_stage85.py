"""Summarize recorded live runs without generating or altering test evidence."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/stage8_5'


def main():
    records = json.loads((OUT / 'live_qwen_cases.json').read_text(encoding='utf-8'))
    rows = []
    for record in records:
        reply = record.get('reply', {})
        metadata = reply.get('technical_metadata', {})
        rows.append({
            'id': record['id'], 'passed': record['passed'],
            'failed_checks': [name for name, passed in record['checks'].items() if not passed],
            'actual_qwen_generation': any(p.get('model') == 'qwen3:8b' and p.get('actual_generation')
                                          for p in reply.get('provider_status', [])),
            'tools': [{'tool': t['tool'], 'status': t['status']} for t in reply.get('tools', [])],
            'termination': metadata.get('autonomous_termination'),
            'seconds': metadata.get('latency_seconds'),
            'diagnostics': metadata.get('diagnostics', []),
            'question': (reply.get('user_facing_answer') or {}).get('question'),
        })
    normal = [r for r in rows if int(r['id'].split('_')[0]) <= 40]
    fault = [r for r in rows if int(r['id'].split('_')[0]) > 40]
    suites = ET.parse(OUT / 'python_results.xml').getroot()
    summary = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'normal_cases': len(normal), 'normal_passed': sum(r['passed'] for r in normal),
        'normal_actual_qwen_generations': sum(r['actual_qwen_generation'] for r in normal),
        'fault_or_budget_cases': len(fault), 'fault_or_budget_passed': sum(r['passed'] for r in fault),
        'terminations': dict(Counter(r['termination'] for r in rows)),
        'python': [s.attrib for s in suites.iter('testsuite')],
        'browser': json.loads((OUT / 'browser_checks.json').read_text(encoding='utf-8')),
        'cases': rows,
        'scope': 'Latest recorded attempt per case. Prior attempts are archived. A one-second timeout case checks an actual request, not completed generation.',
    }
    (OUT / 'validation_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Recorded Qwen3 8B checks', '', '| Case | Passed | Seconds | Actual tools | Failed checks |',
             '|---|---|---|---|---|']
    for row in rows:
        tools = ', '.join(t['tool'] + ':' + t['status'] for t in row['tools'])
        lines.append(f"| {row['id']} | {row['passed']} | {row['seconds']} | {tools} | {', '.join(row['failed_checks'])} |")
    (OUT / 'live_qwen_summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"Normal: {summary['normal_passed']}/{len(normal)}; faults/budgets: {summary['fault_or_budget_passed']}/{len(fault)}")


if __name__ == '__main__':
    main()
