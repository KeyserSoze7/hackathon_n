"""Optional JSON snapshot of a processor run, for local debugging/demo. Not a source of truth:
the API reads contractor_monthly_scorecards in Supabase."""
import json
import pathlib

from .processor import ProcessResult
from .service import shape_row


def export_json(result: ProcessResult, path: str | pathlib.Path) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"run": result.run, "notes": result.notes, "rows": [shape_row(r) for r in result.rows]}
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str, sort_keys=False))
    return p
