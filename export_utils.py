from __future__ import annotations

import json
from pathlib import Path

from docling_core.types.doc.document import DoclingDocument


def save_docling_json(doc: DoclingDocument, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = doc.export_to_dict()
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
