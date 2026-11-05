"""Windows CLI: audited preparation, training and JSON inference."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
_local_deps = ROOT / '.deps'
if _local_deps.exists():
    # Some managed environments expose the directory but deny reads of a
    # shadowing vendored module. Do not make the whole CLI unusable in that
    # case; the interpreter can continue with its normal installed packages.
    _shadowed_six = _local_deps / 'six.py'
    try:
        if _shadowed_six.exists():
            with _shadowed_six.open('rb'):
                pass
        sys.path.insert(0, str(_local_deps))
    except OSError:
        pass
import argparse
import json


def main():
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    dashboard=sub.add_parser('dashboard',help='Local React dashboard served by existing FastAPI')
    dashboard.add_argument('--port',type=int,default=8765)
    dashboard.add_argument('--no-browser',action='store_true')
    dashboard.add_argument('--no-scheduler',action='store_true')
    knowledge=sub.add_parser('knowledge',help='Validated operator-reviewed scientific source documents')
    knowledge_commands=knowledge.add_subparsers(dest='knowledge_command',required=True)
    knowledge_import=knowledge_commands.add_parser('import')
    knowledge_import.add_argument('--input',type=Path,required=True)
    knowledge_commands.add_parser('list')
    for name in ['prepare', 'train']:
        p = sub.add_parser(name)
        p.add_argument('--source', type=Path, help='Original Hafner repository directory with README, LICENSE and data/')
    p = sub.add_parser('predict')
    p.add_argument('--input', type=Path, required=True, help='Measured feature JSON file')
    p.add_argument('--model', choices=['stage1', 'stage1_5'], default='stage1', help='Select preserved stage1 artifact or stage1.5 research artifact')
    sub.add_parser('research', help='Run stage1.5 audit and nested training-only grouped CV; preserves stage1')
    p=sub.add_parser('chat',help='Hybrid read-only AI agent; verified tools work without LLM')
    p.add_argument('--mode',choices=['offline','online','auto'],default='auto')
    p.add_argument('--model',choices=['stage1','stage1_5'],default='stage1_5')
    p.add_argument('--message',help='Single turn instead of interactive chat')
    p.add_argument('--conversation',help='Resume an existing SQLite conversation by ID')
    p.add_argument('--context',type=Path,help='Explicit measured user facts as JSON')
    p.add_argument('--json',action='store_true',help='Include actual tool traces and provider status')
    p.add_argument('--no-llm',action='store_true',help='Explicit deterministic tool mode, no LLM requests')
    p.add_argument('--research',action='store_true',help='Enable v7 autonomous sourced research and literature estimates')
    p=sub.add_parser('providers',help='Probe providers with an actual generation request')
    p.add_argument('--mode',choices=['offline','online','auto'],default='auto')
    p=sub.add_parser('market',help='Local market server, updates and verified CSV import')
    commands=p.add_subparsers(dest='market_command',required=True)
    serve=commands.add_parser('serve')
    serve.add_argument('--port',type=int,default=8765)
    update=commands.add_parser('update')
    update.add_argument('--category',choices=['natural_gas','electricity','organic_fertilizer','mineral_fertilizer','organic_feedstock','heat_energy'])
    importer=commands.add_parser('import-csv')
    importer.add_argument('--input',type=Path,required=True)
    commands.add_parser('status')
    p=sub.add_parser('tool',help='Call one verified Python tool without LLM')
    from src.agent.tools import TOOL_NAMES
    p.add_argument('name',choices=TOOL_NAMES)
    p.add_argument('--input',type=Path,help='Explicit tool facts JSON')
    p.add_argument('--query',default='',help='Query for the curated scientific source catalogue')
    p = sub.add_parser('import-csv')
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--dictionary', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'knowledge':
            from src.recommendations.retrieval import import_document,documents
            value=import_document(args.input) if args.knowledge_command=='import' else {'documents':[d.model_dump(mode='json') for d in documents()]}
            print(json.dumps(value,ensure_ascii=False,indent=2))
        elif args.command == 'dashboard':
            from src.dashboard.launcher import run
            run(args)
        elif args.command == 'market':
            from src.market.cli import run
            run(args)
        elif args.command == 'chat':
            from src.agent.cli import chat
            chat(args)
        elif args.command == 'providers':
            from src.agent.providers import HybridLLM
            print(json.dumps(HybridLLM(args.mode).probe(),ensure_ascii=False,indent=2))
        elif args.command == 'tool':
            from src.agent.cli import call_tool
            return call_tool(args)
        elif args.command == 'research':
            from threadpoolctl import threadpool_limits
            from src.ml.stage1_5 import run
            with threadpool_limits(limits=2):
                run()
        elif args.command == 'prepare':
            from src.data.prepare import prepare
            print('Prepared rows:', len(prepare(args.source)))
        elif args.command == 'train':
            from src.ml.train import train
            train(args.source)
        elif args.command == 'import-csv':
            import hashlib
            import shutil
            import pandas as pd
            from src.data.prepare import write_json
            frame = pd.read_csv(args.input)
            dest = ROOT / 'data/raw/mendeley_manual'
            if dest.exists():
                raise ValueError('Manual import already exists; preserve original and review before replacing')
            if args.input.suffix.lower() != '.csv' or not args.dictionary.is_file() or frame.empty:
                raise ValueError('Nonempty CSV and data dictionary are required')
            dest.mkdir(parents=True)
            shutil.copy2(args.input, dest / 'dataset_v1_theoretical.csv')
            shutil.copy2(args.dictionary, dest / 'data_dictionary.md')
            write_json(dest / 'import_audit.json', {'columns': list(frame.columns), 'rows': len(frame), 'sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
                'status': 'Quarantined: not used in training until provenance, license, units, study identifiers and target-derived features are reviewed.'})
            print('CSV imported for review; it has NOT been merged or trained.')
        else:
            from src.inference.predict import predict_bmp
            payload = json.loads(args.input.read_text(encoding='utf-8-sig'))
            model_path = ROOT / 'models/stage1_5/bmp.joblib' if args.model == 'stage1_5' else None
            print(json.dumps(predict_bmp(payload, model_path=model_path), ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError, ImportError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
