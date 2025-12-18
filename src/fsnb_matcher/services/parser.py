# src/fsnb_matcher/services/parser.py
from __future__ import annotations
from pathlib import Path
from typing import Iterable
from lxml import etree

def _list_xml(fsnb_dir: Path) -> list[Path]:
    files: list[Path] = []
    for p in fsnb_dir.iterdir():
        if p.is_file() and p.suffix.lower() == ".xml":
            files.append(p)
    return sorted(files)

def iter_items(fsnb_dir: Path) -> Iterable[tuple[str, str, str | None, str]]:
    files = _list_xml(fsnb_dir)
    print(f"[INFO] FSNB dir: {fsnb_dir}")
    print(f"[INFO] XML files found: {len(files)}")
    for p in files:
        print(f"  - {p.name}")

    for xml_path in files:
        name_lc = xml_path.name.lower()
        try:
            root = etree.parse(str(xml_path)).getroot()
        except Exception as e:
            print(f"[WARN] parse failed: {xml_path.name}: {e}")
            continue

        if "гэсн" in name_lc:
            count = 0
            for el in root.xpath(".//NameGroup"):
                begin = (el.get("BeginName") or "").strip()
                for w in el.xpath("./Work"):
                    code = (w.get("Code") or "").strip()
                    end = (w.get("EndName") or "").strip()
                    unit = (w.get("MeasureUnit") or "").strip() or None
                    if not code or not end:
                        continue
                    full = f"{begin} {end}".strip() if begin else end
                    count += 1
                    yield (code, full, unit, "work")
            print(f"[INFO] Parsed {count} works from {xml_path.name}")

        if "фсбц" in name_lc:
            count = 0
            for r in root.xpath(".//Resource[@Code]"):
                code = (r.get("Code") or "").strip()
                title = (r.get("Name") or r.get("EndName") or "").strip()
                unit = (r.get("MeasureUnit") or "").strip() or None
                if not code or not title:
                    continue
                count += 1
                yield (code, title, unit, "resource")
            print(f"[INFO] Parsed {count} resources from {xml_path.name}")
