import argparse, json
from .bots import BOT_TYPES
from .engine import SimulationRunner
from .dataset import validate_dataset
def main():
    parser=argparse.ArgumentParser(description="Local heads-up poker simulator"); sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("list-bots"); validate=sub.add_parser("validate-dataset"); validate.add_argument("path"); run=sub.add_parser("run")
    for name,default in (("--bot-a","random"),("--bot-b","random")): run.add_argument(name,choices=BOT_TYPES,default=default)
    run.add_argument("--hands",type=int,default=100); run.add_argument("--seed",type=int); run.add_argument("--starting-stack-bb",type=int,default=100); run.add_argument("--equity-iterations",type=int,default=1000); run.add_argument("--dataset-output"); run.add_argument("--overwrite",action="store_true")
    args=parser.parse_args()
    if args.command=="list-bots": print("\n".join(BOT_TYPES)); return
    if args.command=="validate-dataset":
        result=validate_dataset(args.path); print(json.dumps(result,indent=2)); raise SystemExit(1 if result["invalid_records"] else 0)
    a=BOT_TYPES[args.bot_a](seed=args.seed,equity_iterations=args.equity_iterations); b=BOT_TYPES[args.bot_b](seed=None if args.seed is None else args.seed+1,equity_iterations=args.equity_iterations)
    result=SimulationRunner(a,b,args.hands,args.starting_stack_bb,args.seed,args.equity_iterations,args.dataset_output,args.overwrite).run(); print(json.dumps(result,indent=2))
if __name__=="__main__": main()
