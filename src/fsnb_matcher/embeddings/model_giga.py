from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List
import threading

import torch
from sentence_transformers import SentenceTransformer

from src.core.config import settings

INSTRUCT_QUERY = "Instruct: Given a database query, retrieve relevant FSNB entries\nQuery: "


def _fsnb_dir(path_str: str) -> Path:
    # paths в конфиге у тебя строки — приводим к Path относительно /app
    p = Path(path_str)
    if p.is_absolute():
        return p
    return (Path("/app") / p).resolve()


@lru_cache()
def _gpu_sem() -> threading.Semaphore:
    slots = int(getattr(settings.fsnb, "gpu_slots", 1) or 1)
    return threading.Semaphore(max(1, slots))


def _device() -> str:
    dev = getattr(settings.fsnb, "hf_embed_device", "auto")
    if dev == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return dev


def _use_fp16() -> bool:
    return bool(getattr(settings.fsnb, "hf_embed_fp16", True))


def _dtype():
    if _use_fp16() and _device().startswith("cuda"):
        return torch.float16
    return torch.float32


@lru_cache()
def get() -> SentenceTransformer:
    model_dir = _fsnb_dir(settings.fsnb.model_giga_dir)
    model_path = str(model_dir)

    # ВАЖНО: trust_remote_code нужен для Giga
    model = SentenceTransformer(
        model_path,
        device=_device(),
        trust_remote_code=True,
        model_kwargs={"torch_dtype": _dtype()},
    )
    model.eval()
    return model


def dim() -> int:
    return int(get().get_sentence_embedding_dimension())


def _encode_impl(texts: List[str], batch_size: int) -> List[List[float]]:
    dev = _device()
    if dev.startswith("cuda"):
        with torch.inference_mode(), torch.amp.autocast("cuda", dtype=_dtype()):
            embs = get().encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=False,
                show_progress_bar=False,
            )
            torch.cuda.synchronize()
    else:
        with torch.inference_mode():
            embs = get().encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=False,
                show_progress_bar=False,
            )
    return embs.tolist()


def encode(texts: List[str], *, is_query: bool, batch_size: int | None = None) -> List[List[float]]:
    if batch_size is None:
        if is_query:
            batch_size = int(getattr(settings.fsnb, "giga_query_bs", 2))
        else:
            batch_size = int(getattr(settings.fsnb, "giga_index_bs", getattr(settings.fsnb, "embed_batch_size", 128)))

    if is_query:
        texts = [INSTRUCT_QUERY + (t or "") for t in texts]

    sem = _gpu_sem()
    sem.acquire()
    try:
        return _encode_impl(texts, batch_size=batch_size)
    finally:
        sem.release()


def unload() -> None:
    try:
        get.cache_clear()
    except Exception:
        pass
    if torch.cuda.is_available() and _device().startswith("cuda"):
        torch.cuda.empty_cache()

def embed_texts(texts: list[str], *, is_query: bool = False, batch_size: int | None = None) -> list[list[float]]:
    """
    Backward-compatible alias.
    Старый код ожидает embed_texts(), а новый модуль использует encode().
    """
    return encode(texts, is_query=is_query, batch_size=batch_size)
