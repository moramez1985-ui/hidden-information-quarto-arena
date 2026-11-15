from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .adapters import EvaluatorInputError
from .annotations import AnnotationError
from .report import evaluate_files, report_to_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Quarto restricted Harness logs using independent human gold labels."
    )
    parser.add_argument("--harness", required=True, help="Restricted Tournament Harness JSON log")
    parser.add_argument("--annotations", required=True, help="Human gold annotation JSON")
    parser.add_argument("--traces", help="Optional Decision Trace v1 JSONL file")
    parser.add_argument("--output", help="Write report JSON to this path instead of stdout")
    arguments = parser.parse_args()
    try:
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

