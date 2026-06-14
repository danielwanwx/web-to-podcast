from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import slugify, stable_id


@dataclass
class SourceDocument:
    id: str
    title: str
    raw_text: str
    source_url: str = ""
    source_path: str = ""
    section: str = ""
    order: int | None = None
    media_type: str = "text/plain"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        prefix = f"{int(self.order):04d}-" if self.order is not None else ""
        return prefix + slugify(self.title, self.id)

    @classmethod
    def build(
        cls,
        *,
        raw_text: str,
        title: str = "",
        source_url: str = "",
        source_path: str = "",
        section: str = "",
        order: int | None = None,
        media_type: str = "text/plain",
        metadata: dict[str, Any] | None = None,
    ) -> "SourceDocument":
        inferred_title = title.strip() or Path(source_path).stem or "Untitled"
        doc_id = stable_id(source_url, source_path, inferred_title, str(order or ""))
        return cls(
            id=doc_id,
            title=inferred_title,
            raw_text=raw_text,
            source_url=source_url,
            source_path=source_path,
            section=section,
            order=order,
            media_type=media_type,
            metadata=metadata or {},
        )
