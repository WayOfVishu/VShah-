"""
CLI entry point — project-charter.md Section 5.4.

Fully built (argparse wiring, mechanical) — but every module it calls into
that's still a docs/TODO.md stub will raise NotImplementedError. That's
expected at this stage of the project; this file's job is to give you one
consistent place to run things from as each piece lands, not to work
end-to-end on day one. Run it early and often anyway — it tells you
exactly which TODO you're blocked on next.

Usage (from the python/ directory, or via the repo-root hwcheck.py wrapper):
    python -m cli.main                          # full pass: telemetry + Gemini analysis
    python -m cli.main --raw                    # also print the raw telemetry JSON
    python -m cli.main --no-ai                  # skip the Gemini call entirely (dev/rate-limit friendly)
    python -m cli.main --export json            # write a report file under data/reports/
    python -m cli.main --memory-demo leak        # opt into the C++ memory-bug demo (see cpp/src/main.cpp)
    python -m cli.main --ping-host 1.1.1.1 --dns-host example.com --port-range 1024:1124
"""

import argparse
import sys

from ai_analyzer import gemini_client, prompt_builder, response_parser
from netdiag import config, dns_probe, engine_runner, ping_probe, port_scan, report_writer, schema


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hwcheck",
        description="System & network diagnostics with a Gemini-generated plain-language summary.",
    )
    parser.add_argument("--raw", action="store_true", help="also print the raw merged telemetry JSON")
    parser.add_argument("--no-ai", action="store_true", help="skip the Gemini analysis call")
    parser.add_argument(
        "--export", choices=["json", "text"], default=None, help="write a report file under data/reports/"
    )
    parser.add_argument(
        "--memory-demo",
        choices=["clean_cycle", "leak", "dangling_pointer", "double_free", "all"],
        default=None,
        help="run one of the C++ memory-sandbox demos as part of this pass (see cpp/src/main.cpp)",
    )
    parser.add_argument("--ping-host", default="1.1.1.1", help="host to measure ICMP latency against")
    parser.add_argument("--dns-host", default="example.com", help="hostname to time DNS resolution for")
    parser.add_argument(
        "--port-range",
        default=None,
        metavar="START:END",
        help="e.g. 1024:1124 — overrides netdiag.config.DEFAULT_PORT_RANGE",
    )
    return parser.parse_args(argv)


def _parse_port_range(raw: str | None) -> tuple[int, int]:
    if raw is None:
        return config.DEFAULT_PORT_RANGE
    start_str, _, end_str = raw.partition(":")
    return int(start_str), int(end_str)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        engine_report = engine_runner.run_engine(memory_demo=args.memory_demo)
        ping_result = ping_probe.measure_ping(args.ping_host)
        dns_result = dns_probe.measure_dns(args.dns_host)
        port_result = port_scan.scan_ports(args.ping_host, _parse_port_range(args.port_range))

        telemetry = schema.merge_telemetry(engine_report, ping_result, dns_result, port_result)

        if args.raw:
            import json

            print(json.dumps(telemetry, indent=2))

        analysis = None
        if not args.no_ai:
            prompt = prompt_builder.build_prompt(telemetry)
            raw_response = gemini_client.call_gemini(prompt, response_schema=None)
            analysis = response_parser.parse_analysis(raw_response)
            print(f"\nSummary: {analysis.get('summary')}")
            print(f"Severity: {analysis.get('severity')}")

        if args.export:
            out_path = report_writer.write_report(telemetry, analysis, fmt=args.export)
            print(f"\nReport written to {out_path}")

        return 0

    except NotImplementedError as e:
        print(f"Not implemented yet: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
