import csv
import io
import json
from typing import List
from app.schemas.expense import ExpenseWithRunningBalance


def sanitize_csv_cell(value: str) -> str:
    """
    Neutralize CSV / spreadsheet formula injection.
    If text begins with =, +, -, @, \\t, or \\r, prepend a single quote (')
    to prevent spreadsheet applications from evaluating it as a command or formula.
    """
    if not value:
        return ""
    str_val = str(value)
    if str_val and str_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{str_val}"
    return str_val


def generate_csv_data(expenses: List[ExpenseWithRunningBalance]) -> str:
    """Generate CSV text output for transaction ledger."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Write Header
    writer.writerow([
        "Sequence",
        "Transaction ID",
        "Timestamp (UTC)",
        "Description",
        "Category",
        "Amount (LKR)",
        "Running Balance (LKR)",
        "Status"
    ])

    for exp in expenses:
        writer.writerow([
            exp.sequence_number,
            exp.tx_code,
            exp.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            sanitize_csv_cell(exp.description),
            sanitize_csv_cell(exp.category),
            f"{exp.amount:.2f}",
            f"{exp.running_balance:.2f}",
            "VERIFIED"
        ])

    return output.getvalue()


def generate_json_data(expenses: List[ExpenseWithRunningBalance]) -> str:
    """Generate pretty formatted JSON export of transaction ledger."""
    data = [
        {
            "sequence": exp.sequence_number,
            "tx_code": exp.tx_code,
            "id": exp.id,
            "created_at": exp.created_at.isoformat(),
            "description": exp.description,
            "category": exp.category,
            "currency": exp.currency,
            "amount": float(exp.amount),
            "running_balance": float(exp.running_balance),
            "status": "VERIFIED"
        }
        for exp in expenses
    ]
    return json.dumps({"transactions": data, "count": len(data)}, indent=2)
