from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .adapters import EvaluatorInputError
from .annotations import AnnotationError
from .automated import evaluate_automated_file
from .report import evaluate_files, report_to_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Quarto Harness logs (human gold annotations or --auto mode)."
    )
    parser.add_argument("--harness", required=True, help="Restricted Harness log or Kaggle .run.json file")
    parser.add_argument("--annotations", help="Human gold annotation JSON (required unless --auto is set)")
    parser.add_argument("--traces", help="Optional Decision Trace v1 JSONL file")
    parser.add_argument("--auto", action="store_true", help="Run automated deterministic evaluation without human gold labels")
    parser.add_argument("--output", help="Write report JSON to this path instead of stdout")
    arguments = parser.parse_args()
    try:
        if arguments.auto:
            report = evaluate_automated_file(arguments.harness)
            serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        else:
            if not arguments.annotations:
                parser.error("--annotations is required unless --auto is specified.")
            report = evaluate_files(
                arguments.harness,
                arguments.annotations,
                arguments.traces,
            )
            serialized = report_to_json(report) + "\n"
        if arguments.output:
            Path(arguments.output).write_text(serialized, encoding="utf-8")
        else:
            sys.stdout.write(serialized)
    except (EvaluatorInputError, AnnotationError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
