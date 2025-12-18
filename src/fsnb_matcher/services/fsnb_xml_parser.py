from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional, Tuple

from lxml import etree

RowTuple = Tuple[str, str, Optional[str], str]  # (code, name, unit, type)


def iter_items_from_fsnb_xml(fsnb_dir: str | Path) -> Iterator[RowTuple]:
    """
    Потоковый парсер FSNB-2022 XML: отдаёт плоскую витрину items:
      - work:  Work(Code, EndName, MeasureUnit) + BeginName из NameGroup
      - resource: ResourceCatalog -> Resource(Code, Name, MeasureUnit)

    fsnb_dir: директория с *.xml
    """
    fsnb_dir = Path(fsnb_dir)
    if not fsnb_dir.exists():
        raise FileNotFoundError(f"FSNB dir not found: {fsnb_dir}")

    xml_files = sorted([p for p in fsnb_dir.iterdir() if p.is_file() and p.suffix.lower() == ".xml"])
    if not xml_files:
        raise FileNotFoundError(f"No .xml files in: {fsnb_dir}")

    for xml_path in xml_files:
        # Бывает много служебных файлов — просто пропускаем те, что не похожи
        # на base / ResourceCatalog.
        try:
            # Считываем только корневой тег
            for _, root in etree.iterparse(str(xml_path), events=("start",), recover=True, huge_tree=True):
                root_tag = root.tag
                break
            else:
                continue
        except Exception:
            continue

        if root_tag == "base":
            yield from _iter_items_from_base(xml_path)
        elif root_tag == "ResourceCatalog":
            yield from _iter_items_from_resource_catalog(xml_path)
        else:
            continue


def _iter_items_from_base(xml_path: Path) -> Iterator[RowTuple]:
    """
    base -> ... NameGroup(BeginName) -> Work(Code, EndName, MeasureUnit)
    """
    begin_name_stack: list[Optional[str]] = []
    in_name_group = 0

    context = etree.iterparse(
        str(xml_path),
        events=("start", "end"),
        recover=True,
        huge_tree=True,
    )

    for event, el in context:
        tag = el.tag

        if event == "start" and tag == "NameGroup":
            in_name_group += 1
            begin = (el.get("BeginName") or "").strip() or None
            begin_name_stack.append(begin)

        elif event == "end" and tag == "Work":
            code = (el.get("Code") or "").strip()
            end_name = (el.get("EndName") or "").strip()
            unit = (el.get("MeasureUnit") or "").strip() or None

            if code and end_name:
                begin = begin_name_stack[-1] if begin_name_stack else None
                full_name = f"{begin} {end_name}".strip() if begin else end_name
                yield (code, full_name, unit, "work")

            # освобождаем память
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]

        elif event == "end" and tag == "NameGroup":
            if in_name_group > 0:
                in_name_group -= 1
            if begin_name_stack:
                begin_name_stack.pop()
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]


def _iter_items_from_resource_catalog(xml_path: Path) -> Iterator[RowTuple]:
    """
    ResourceCatalog -> ... Section -> Resource(Code, Name, MeasureUnit)
    """
    context = etree.iterparse(
        str(xml_path),
        events=("end",),
        recover=True,
        huge_tree=True,
    )

    for _, el in context:
        if el.tag != "Resource":
            continue

        code = (el.get("Code") or "").strip()
        name = (el.get("Name") or "").strip()
        unit = (el.get("MeasureUnit") or "").strip() or None

        if code and name:
            yield (code, name, unit, "resource")

        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]
