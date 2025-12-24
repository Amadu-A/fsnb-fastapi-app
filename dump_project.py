#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_project.py — собирает код и структуру проекта в JSON для LLM.

Запуск:
  python dump_project.py \
    --out project_dump.json \
    --max-bytes 800000 \
    --tree-depth 5

По умолчанию:
  - сохраняет structure.txt (через `tree`, если доступен; иначе — питоновская обводка);
  - игнорирует бинарные/медийные файлы и стандартные служебные директории;
  - кладёт весь текстовый код в JSON с хэшами и размерами;
  - добавляет поля context.static_instructions и context.current_objectives.

Советы:
  - Для больших репозиториев увеличьте --max-bytes при необходимости.
  - Если нужно включить доп. расширения — правьте TEXT_EXTENSIONS или передавайте --include-ext.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, List, Dict, Any, Set

# --- Настройки по умолчанию ---

DEFAULT_IGNORE_GLOBS: List[str] = [
    # из запроса
    "__pycache__",
    "*.sample",
    "*.txt",  # можно убрать, если нужны README/тексты
    "*.log",
    "*.pdf",
    "*.jpg", "*.jpeg", "*.svg", "*.png",
    "*.pt",
    "venv", ".venv", "env", ".env", "media",
    "objects",  #  "dataset",
    "__init__.pyc",

    # типичные служебные/тяжёлые каталоги
    ".git", ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".cache", ".tox",
    "node_modules", "dist", "build", ".next", ".nuxt", ".turbo",
    "*.egg-info", "weights",
]

# Каталоги, которые игнорируем только на верхнем уровне корня проекта
ROOT_ONLY_IGNORE_DIRS: Set[str] = {"dataset"}

# Текстовые расширения, которые считаем безопасными для LLM
TEXT_EXTENSIONS: Set[str] = {
    # код
    ".py", ".pyi", ".ipynb",
    ".js", ".jsx", ".ts", ".tsx",
    ".html", ".htm", ".css", ".scss", ".sass",
    ".vue", ".svelte",
    ".java", ".kt", ".kts", ".swift", ".go", ".rs",
    ".c", ".h", ".cpp", ".hpp", ".cc",
    ".cs", ".vb",
    ".php", ".rb", ".r", ".m", ".mm", ".jl", ".pl", ".lua",

    # конфиги/данные
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env.example",
    ".sql", ".graphql",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", "Dockerfile", ".dockerfile",
    ".gitignore", ".gitattributes", ".editorconfig",

    # документация
    ".md", ".rst", ".adoc",
}

# Предельно допустимый размер текстового файла (байт) — чтобы не раздувать JSON
DEFAULT_MAX_BYTES = 500_000


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Собрать код и структуру проекта в JSON для LLM")
    p.add_argument("--root", default=".", help="Корень проекта (по умолчанию текущая директория)")
    p.add_argument("--out", default="project_dump.json", help="Путь к JSON-выводу")
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Макс. размер файла для включения")
    p.add_argument("--tree-depth", type=int, default=5, help="Глубина для вывода структуры (tree)")
    p.add_argument("--no-structure", action="store_true", help="Не сохранять structure.txt")
    p.add_argument("--include-ext", nargs="*", default=None,
                   help="Доп. расширения для включения (пример: .lock .txt)")
    p.add_argument("--extra-ignore", nargs="*", default=None,
                   help="Доп. glob-шаблоны игнора (пример: secrets/* *.lock)")
    return p.parse_args()


def load_text(path: Path, max_bytes: int) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        # читаем как текст; невалидные байты заменяем
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def is_ignored(path: Path, rel: str, ignore_globs: Iterable[str]) -> bool:
    name = path.name
    parts = Path(rel).parts
    if parts and parts[0] in ROOT_ONLY_IGNORE_DIRS:
        return True
    for pattern in ignore_globs:
        # Совпадение по имени файла/папки или по относительному пути
        if fnmatch(name, pattern) or fnmatch(rel, pattern):
            return True
        # Для директорий допустим точное совпадение сегмента
        # (например, 'venv' игнорирует любой каталог с таким именем)
        # parts = Path(rel).parts
        if pattern in parts:
            return True
    return False


def detect_language(ext: str, name: str) -> str:
    # Очень грубая эвристика — достаточно для LLM-навигации
    if name.lower() in {"dockerfile", "compose.yaml", "compose.yml"}:
        return "docker"
    MAP = {
        ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescriptreact",
        ".jsx": "javascriptreact", ".html": "html", ".css": "css", ".scss": "scss",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".ini": "ini",
        ".md": "markdown", ".rst": "restructuredtext", ".adoc": "asciidoc",
        ".sh": "bash", ".bash": "bash", ".zsh": "zsh", ".ps1": "powershell",
        ".sql": "sql", ".graphql": "graphql", ".go": "go", ".rs": "rust",
        ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
        ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift",
        ".rb": "ruby", ".php": "php", ".cs": "csharp", ".m": "objectivec", ".mm": "objectivecpp",
        ".lua": "lua", ".r": "r", ".pl": "perl", ".jl": "julia",
    }
    return MAP.get(ext.lower(), ext.lower().lstrip(".") or "text")


def run_tree(root: Path, depth: int) -> str:
    """
    Рендер структуры, уважающий DEFAULT_IGNORE_GLOBS и ROOT_ONLY_IGNORE_DIRS.
    Специально НЕ используем внешнюю утилиту `tree`, чтобы корректно
    игнорировать только корневые каталоги (например, dataset в корне, но не services/dataset).
    """
    lines: List[str] = []
    base = root.resolve()
    max_depth = depth

    for curr, dirs, files in os.walk(base):
        rel = Path(curr).relative_to(base)
        d = len(rel.parts)

        # 1) На верхнем уровне — вырезаем только ROOT_ONLY_IGNORE_DIRS
        if d == 0:
            dirs[:] = [dn for dn in dirs if dn not in ROOT_ONLY_IGNORE_DIRS]

        # 2) Вырезаем прочие игноры НА ВСЕХ уровнях (по нашим же правилам)
        pruned_dirs: List[str] = []
        for dn in dirs:
            full = Path(curr) / dn
            rel_dir = full.relative_to(base).as_posix()
            if is_ignored(full, rel_dir, DEFAULT_IGNORE_GLOBS):
                continue
            pruned_dirs.append(dn)
        dirs[:] = pruned_dirs

        if d > max_depth:
            dirs[:] = []
            continue

        indent = "  " * d
        name = "." if rel == Path(".") else rel.as_posix()
        lines.append(f"{indent}{name}/")

        for f in sorted(files):
            full = Path(curr) / f
            rel_file = full.relative_to(base).as_posix()
            if is_ignored(full, rel_file, DEFAULT_IGNORE_GLOBS):
                continue
            lines.append(f"{indent}  {f}")

    return "\n".join(lines)


def should_take_file(path: Path, include_ext: Set[str]) -> bool:
    name = path.name
    ext = path.suffix
    if name.lower() == "dockerfile":
        return True
    return (ext in include_ext) or (ext in TEXT_EXTENSIONS)


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()

    ignore_globs = list(DEFAULT_IGNORE_GLOBS)
    if args.extra_ignore:
        ignore_globs.extend(args.extra_ignore)

    include_ext: Set[str] = set()
    if args.include_ext:
        include_ext.update({e if e.startswith(".") else f".{e}" for e in args.include_ext})

    files_out: List[Dict[str, Any]] = []

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()

        # игнор директорий целиком
        if any(part.startswith(".git") for part in Path(rel).parts):
            continue
        if is_ignored(path, rel, ignore_globs):
            if path.is_dir():
                # пропускаем поддеревья через os.walk? rglob сам проглотит; этого достаточно
                continue
            else:
                continue

        if path.is_dir():
            continue
        if not path.is_file():
            continue

        if not should_take_file(path, include_ext):
            continue

        text = load_text(path, args.max_bytes)
        if text is None:
            continue

        lang = detect_language(path.suffix, path.name)
        entry = {
            "path": rel,
            "language": lang,
            "size_bytes": len(text.encode("utf-8", errors="replace")),
            "sha256": sha256_text(text),
            "content": text,
        }
        files_out.append(entry)

    # Структура проекта (текстом)
    structure_text = None
    if not args.no_structure:
        structure_text = run_tree(root, args.tree_depth)
        try:
            Path("structure.txt").write_text(structure_text or "", encoding="utf-8")
        except Exception:
            pass

    # Итоговый JSON для LLM
    payload: Dict[str, Any] = {
        "meta": {
            "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "root": str(root),
            "tool": "dump_project.py",
            "max_file_bytes": args.max_bytes,
            "total_files": len(files_out),
        },
        "context": {
            # Заполните эти поля один раз и держите «статикой»
            "project_description": "Краткое описание проекта, архитектура, стек, цели.",
            "static_instructions": [
                "Это команды для обсуждения, rewie, улучшения, оптимизации, модернизации и исправления кода для распознавания pdf-файлов с помощью парсинга и обучения YOLO модели и подготовке на основе этих данных отчетов в excel.",
                "Проанализируй весь код проекта, разберись, что и с чем связано.",
                "Каждый файл, который ты подготовишь, должен быть заполнен.",
                "каждый кусок кода , который ты покажешь должен быть строго указан к какому файлу он принадлежит.",
                "Имена переменных и функций — PEP8.",
                "Писать код с упором на низкое потребление памяти и работу с большими данными.",
                "Единый кастомный JSON-логгер через LoggerAdapter (время, уровень, имя функции, сообщение).",
                "Документировать функции и ключевые участки кода.",
                "Все изменения кода подписывай определенным файлом, в котором мы делаем изменения.",
                "Не приводи допущений, где я сам должен что-то понять и довести дело до конца.",
                "Объясни каждую строку кода.",
                "Предлагай улучшения таким образом, чтобы не порушить существующую логику, которая уже работает.",

            ],
            # Это «динамика»: что нужно сделать прямо сейчас
            "current_objectives": [
                # Примеры:
                # "Исправить фильтрацию по периоду в /users/money",
                # "Усилить OCR: заменить pytesseract на ONNXRuntime PP-OCRv3"
            ],
        },
        "structure_text": structure_text,
        "files": files_out,
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] Saved JSON → {out_path} ({len(files_out)} files)")
    if structure_text and not args.no_structure:
        print(f"[OK] Saved structure → structure.txt")


if __name__ == "__main__":
    main()
