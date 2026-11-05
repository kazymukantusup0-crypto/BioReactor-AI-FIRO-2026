import json
from src.market.service import get_store
from src.market.adapters import parse_csv
from src.market.api import manual_observation
from src.market.updater import Updater


def run(args):
    if args.market_command=='serve':
        import uvicorn
        from src.market.api import create_app
        uvicorn.run(create_app(),host='127.0.0.1',port=args.port,log_level='info')
        return
    store=get_store()
    if args.market_command=='update':result=Updater(store).update_category(args.category) if args.category else Updater(store).update_all()
    elif args.market_command=='import-csv':
        result=store.import_prices([manual_observation(p) for p in parse_csv(args.input.read_text(encoding='utf-8-sig'))])
    else:result={'database':str(store.path),'sources':store.sources(),'source_states':store.source_states(),'observations':len(store.prices()),'updates':store.updates()}
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
