# path: src/scripts/prefetch_models.py
from __future__ import annotations

from pathlib import Path

from huggingface_hub import snapshot_download

from src.core.config import settings


def _snap(*, hf_id: str, local_dir: Path) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=hf_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
        resume_download=True,
        allow_patterns="*",
    )


def main() -> None:
    """
    Скачивает ровно одну модель: giga_instruct (HF repo -> local dir).
    Никаких загрузок модели в память — только prefetch файлов.
    """
    hf_id = str(getattr(settings.fsnb, "model_giga_hf", "") or "").strip()
    if not hf_id:
        raise RuntimeError(
            "settings.fsnb.model_giga_hf is empty. "
            "Set it in config.py or via env APP_CONFIG__FSNB__MODEL_GIGA_HF"
        )

    local = Path(str(settings.fsnb.model_giga_dir))

    print("[step] Prefetch HF repo for giga_instruct (download only)")
    print(f"[DL] {hf_id} → {local}")

    _snap(hf_id=hf_id, local_dir=local)

    print("[OK] Prefetch complete")


if __name__ == "__main__":
    main()
