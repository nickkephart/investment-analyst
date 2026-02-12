#!/usr/bin/env python3
"""
CLI for Portfolio Recommendation Service.
"""

import argparse
import sys
from pathlib import Path

import yaml


def load_config(config_path: str = None) -> dict:
    """Load config from YAML."""
    base = Path(__file__).parent.parent
    path = Path(config_path) if config_path else base / "config.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def cmd_import_theses(args, config):
    from portrec.thesis_store import ThesisStore

    store = ThesisStore(db_path=config.get("db_path", "portrec.db"))
    count = store.import_from_json(args.json_path)
    print(f"Imported {count} theses")


def cmd_list_theses(args, config):
    from portrec.thesis_store import ThesisStore
    store = ThesisStore(db_path=config.get("db_path", "portrec.db"))
    selected_only = getattr(args, "selected", False)
    theses = store.list_theses(selected_only=selected_only)

    if not theses:
        print("No theses in store. Use: portrec import-theses <path-to-json>")
        return

    for t in theses:
        sel = "[*]" if t["selected"] else "[ ]"
        print(f"  {sel} {t['id']}: {t['title']} (priority={t['priority']})")


def cmd_select(args, config):
    from portrec.thesis_store import ThesisStore
    store = ThesisStore(db_path=config.get("db_path", "portrec.db"))
    ok = store.select(args.thesis_id)
    if ok:
        print(f"Selected thesis {args.thesis_id}")
    else:
        print(f"Thesis {args.thesis_id} not found")
        sys.exit(1)


def cmd_deselect(args, config):
    from portrec.thesis_store import ThesisStore
    store = ThesisStore(db_path=config.get("db_path", "portrec.db"))
    ok = store.deselect(args.thesis_id)
    if ok:
        print(f"Deselected thesis {args.thesis_id}")
    else:
        print(f"Thesis {args.thesis_id} not found")
        sys.exit(1)


def cmd_set_priority(args, config):
    from portrec.thesis_store import ThesisStore
    store = ThesisStore(db_path=config.get("db_path", "portrec.db"))
    ok = store.set_priority(args.thesis_id, args.priority)
    if ok:
        print(f"Set priority of thesis {args.thesis_id} to {args.priority}")
    else:
        print(f"Thesis {args.thesis_id} not found")
        sys.exit(1)


def cmd_research(args, config):
    from portrec.thesis_store import ThesisStore
    from portrec.equity_analyst import MultiSourceEquityAnalyst

    store = ThesisStore(db_path=config.get("db_path", "portrec.db"))
    theses = store.get_selected_theses()

    if not theses:
        print("No theses selected. Use: portrec select <id>")
        sys.exit(1)

    if args.thesis_ids:
        theses = [t for t in theses if t["id"] in args.thesis_ids]
        if not theses:
            print(f"No matching selected theses for ids: {args.thesis_ids}")
            sys.exit(1)

    securities_db = config.get("securities_db_path", "portrec_securities.db")
    analyst = MultiSourceEquityAnalyst(
        db_path=securities_db,
        enable_massive=config.get("enable_massive"),
        enable_alpha_vantage=config.get("enable_alpha_vantage"),
        polygon_api_key=config.get("polygon_api_key") or None,
        alpha_vantage_api_key=config.get("alpha_vantage_api_key") or None,
    )

    max_sec = args.max_securities or 20
    for thesis in theses:
        print(f"\nResearching: {thesis['title']}")
        results = analyst.analyze_thesis(thesis, max_securities=max_sec)
        print(f"  Found {len(results)} securities, top score: {results[0]['score']:.0f}" if results else "  No results")


def cmd_recommend(args, config):
    from portrec.thesis_store import ThesisStore
    from portrec.equity_analyst import MultiSourceEquityAnalyst
    from portrec.portfolio_recommender import load_portfolio_csv, generate_recommendations

    portfolio_path = args.portfolio_csv or config.get("portfolio_csv")
    if not portfolio_path:
        print("No portfolio CSV specified. Set in config or use --portfolio-csv")
        sys.exit(1)

    portfolio = load_portfolio_csv(portfolio_path)

    store = ThesisStore(db_path=config.get("db_path", "portrec.db"))
    theses = store.get_selected_theses()
    if not theses:
        print("No theses selected. Use: portrec select <id>")
        sys.exit(1)

    securities_db = config.get("securities_db_path", "portrec_securities.db")
    analyst = MultiSourceEquityAnalyst(
        db_path=securities_db,
        enable_massive=config.get("enable_massive"),
        enable_alpha_vantage=config.get("enable_alpha_vantage"),
        polygon_api_key=config.get("polygon_api_key") or None,
        alpha_vantage_api_key=config.get("alpha_vantage_api_key") or None,
    )

    thesis_results = {}
    for thesis in theses:
        tid = thesis["id"]
        results = analyst.get_thesis_results(tid, limit=20)
        if not results:
            print(f"  No stored results for {tid}, running research...")
            results = analyst.analyze_thesis(thesis, max_securities=20)
        thesis_name = thesis.get("name", thesis.get("title", tid))
        for r in results:
            r.setdefault("thesis_name", thesis_name)
        thesis_results[tid] = results

    recs = generate_recommendations(
        portfolio=portfolio,
        thesis_results=thesis_results,
        add_threshold=config.get("add_threshold", 50),
        top_n_adds=config.get("top_n_adds_per_thesis", 5),
        consider_removals=config.get("consider_removals", False),
        removal_threshold=config.get("removal_threshold", 30),
    )

    print("\n=== ADD RECOMMENDATIONS ===")
    for r in recs["add"]:
        print(f"  + {r['symbol']} - {r['name']} (score: {r['score']:.0f})")
        print(f"    Thesis: {r['thesis_name']}")
        print(f"    Rationale: {r['rationale']}")

    if recs["hold"]:
        print("\n=== HOLD (strong alignment) ===")
        for r in recs["hold"]:
            print(f"  ~ {r['symbol']} - {r['description']} (score: {r['score']:.0f})")

    if recs["remove"]:
        print("\n=== CONSIDER REMOVING ===")
        for r in recs["remove"]:
            print(f"  - {r['symbol']}: {r['rationale']}")


def cmd_run_background(args, config):
    from portrec.background_worker import run_worker
    run_worker(config)


def main():
    config = load_config()

    parser = argparse.ArgumentParser(prog="portrec", description="Portfolio Recommendation Service")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # import-theses
    p = subparsers.add_parser("import-theses", help="Import theses from JSON")
    p.add_argument("json_path", help="Path to theses JSON file")
    p.set_defaults(func=cmd_import_theses)

    # list-theses
    p = subparsers.add_parser("list-theses", help="List all theses")
    p.add_argument("--selected", action="store_true", help="Only list selected theses")
    p.set_defaults(func=cmd_list_theses)

    # select
    p = subparsers.add_parser("select", help="Select a thesis for research")
    p.add_argument("thesis_id", help="Thesis ID")
    p.set_defaults(func=cmd_select)

    # deselect
    p = subparsers.add_parser("deselect", help="Deselect a thesis")
    p.add_argument("thesis_id", help="Thesis ID")
    p.set_defaults(func=cmd_deselect)

    # set-priority
    p = subparsers.add_parser("set-priority", help="Set thesis priority (lower = higher)")
    p.add_argument("thesis_id", help="Thesis ID")
    p.add_argument("priority", type=int, help="Priority value")
    p.set_defaults(func=cmd_set_priority)

    # research
    p = subparsers.add_parser("research", help="Run equity analysis for selected theses")
    p.add_argument("--thesis-ids", nargs="+", help="Limit to these thesis IDs")
    p.add_argument("--max-securities", type=int, default=20, help="Max securities per thesis")
    p.set_defaults(func=cmd_research)

    # recommend
    p = subparsers.add_parser("recommend", help="Generate add/remove recommendations")
    p.add_argument("--portfolio-csv", help="Portfolio CSV path (overrides config)")
    p.set_defaults(func=cmd_recommend)

    # run-background
    p = subparsers.add_parser("run-background", help="Run background worker")
    p.set_defaults(func=cmd_run_background)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args, config)


if __name__ == "__main__":
    main()
