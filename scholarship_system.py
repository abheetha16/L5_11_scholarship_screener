"""Evaluate scholarship applicants using a configurable merit formula."""

import ast
import json
import math
import operator
from pathlib import Path
from typing import Any

MERIT_FORMULA = "gpa * 10 + credits * 2"
INCOME_LIMIT = 800_000
CUTOFF = 85
RESULTS_FILE = Path("scholarships.json")

# Only arithmetic operations are allowed in user-supplied merit formulas.
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_NAMES = {"gpa", "credits"}

results: dict[str, dict[str, Any]] = {}


def _evaluate_expression(node: ast.AST, values: dict[str, float]) -> float:
    """Evaluate a validated arithmetic expression without using eval()."""
    if isinstance(node, ast.Expression):
        return _evaluate_expression(node.body, values)
    if (isinstance(node, ast.Constant)
            and type(node.value) in (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
        return values[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_expression(node.left, values)
        right = _evaluate_expression(node.right, values)
        if isinstance(node.op, ast.Pow):
            if abs(right) > 8 or abs(left) > 1_000:
                raise ValueError("Exponent or base is too large")
        return float(_BINARY_OPERATORS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        operand = _evaluate_expression(node.operand, values)
        return float(_UNARY_OPERATORS[type(node.op)](operand))
    raise ValueError(
        "Formula may contain only gpa, credits, numbers, "
        "and arithmetic operators"
    )


def calculate_merit_score(gpa: float, credits: float) -> float:
    """Calculate a merit score using the configured safe arithmetic formula."""
    try:
        expression = ast.parse(MERIT_FORMULA, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid merit formula syntax") from exc
    score = _evaluate_expression(expression, {"gpa": gpa, "credits": credits})
    if not (-1_000_000 <= score <= 1_000_000):
        raise ValueError("Merit score is outside the supported range")
    return score


def evaluate_applicant(
    student_id: str,
    test_scores: dict[str, Any],
    logs: list[str] | None = None,
) -> bool:
    """Validate and evaluate one applicant, recording the result and log."""
    if logs is None:
        logs = []
    if not isinstance(student_id, str) or not student_id.strip():
        raise ValueError("student_id must be a non-empty string")
    if not isinstance(test_scores, dict):
        raise ValueError("test_scores must be a dictionary")
    if "gpa" not in test_scores:
        raise ValueError("Missing required field: gpa")

    gpa = test_scores["gpa"]
    credits = test_scores.get("credits", 0)
    income = test_scores.get("income", 0)
    fields = (("gpa", gpa), ("credits", credits), ("income", income))
    for field, value in fields:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be a number")
        if not math.isfinite(value):
            raise ValueError(f"{field} must be finite")
    if not 0 <= gpa <= 10:
        raise ValueError("gpa must be between 0 and 10")
    if credits < 0:
        raise ValueError("credits cannot be negative")
    if income < 0:
        raise ValueError("income cannot be negative")

    score = calculate_merit_score(gpa, credits)
    eligible = score >= CUTOFF and income < INCOME_LIMIT
    results[student_id] = {"score": score, "eligible": eligible}
    logs.append(f"{student_id} scored {score:g}")
    return eligible



def change_formula(new_formula: str) -> None:
    """Validate a new arithmetic formula before applying it."""
    global MERIT_FORMULA  # Shared configuration updated by the CLI.
    if not isinstance(new_formula, str) or not new_formula.strip():
        raise ValueError("Formula must be a non-empty string")
    old_formula = MERIT_FORMULA
    MERIT_FORMULA = new_formula
    try:
        calculate_merit_score(5, 2)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        MERIT_FORMULA = old_formula
        raise ValueError(f"Invalid merit formula: {exc}") from exc


def persist_results(file: str | Path = RESULTS_FILE) -> None:
    """Write results to JSON, reporting filesystem errors to the caller."""
    path = Path(file)
    with path.open("w", encoding="utf-8") as output_file:
        json.dump(results, output_file, indent=2)


def load_results(file: str | Path = RESULTS_FILE) -> None:
    """Load saved results, rejecting malformed or unreadable data."""
    global results  # Replace in-memory state after loading persisted data.
    path = Path(file)
    try:
        with path.open("r", encoding="utf-8") as input_file:
            loaded = json.load(input_file)
    except FileNotFoundError:
        results = {}
        return
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load results from {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("Saved results must contain a JSON object")
    for student_id, record in loaded.items():
        if not isinstance(record, dict) or not isinstance(
            record.get("eligible"), bool
        ):
            raise ValueError(f"Invalid saved record for {student_id}")
        if not isinstance(record.get("score"), (int, float)):
            raise ValueError(f"Invalid score for {student_id}")
    results = loaded


def print_shortlist() -> None:
    """Print all applicants who meet the eligibility requirements."""
    print("Shortlisted applicants:")
    for student_id, record in results.items():
        if record["eligible"]:
            print(f"  {student_id} score = {record['score']:g}")


def main() -> None:
    """Run the sample scholarship evaluation and save its results."""
    applicants = [
        ("U001", {"gpa": 9.1, "credits": 4, "income": 450_000}),
        ("U002", {"gpa": 7.2, "credits": 1, "income": 300_000}),
        ("U003", {"gpa": 12.5, "credits": -3, "income": -1}),
        ("U004", {"gpa": 6.5}),
    ]
    logs: list[str] = []
    for student_id, scores in applicants:
        try:
            evaluate_applicant(student_id, scores, logs)
        except ValueError as exc:
            print(f"Skipping {student_id}: {exc}")

    formula = input("Merit formula (Enter to keep default): ").strip()
    if formula:
        try:
            change_formula(formula)
        except ValueError as exc:
            print(f"Keeping default formula: {exc}")

    try:
        evaluate_applicant(
            "U005", {"gpa": 8.4, "credits": 3, "income": 600_000}, logs
        )
        persist_results()
        load_results()
    except (ValueError, OSError) as exc:
        print(f"Could not save/load results: {exc}")
        return
    print_shortlist()


if __name__ == "__main__":
    main()
