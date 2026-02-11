from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    storage_dir: Path
    storage_mode: str
    allowed_extensions: set[str]
    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str
    cloudinary_folder: str

    @property
    def is_external(self) -> bool:
        return self.storage_mode == "external"



def load_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    return Settings(
        base_dir=base_dir,
        storage_dir=Path(os.environ.get("LOCAL_STORAGE_DIR", base_dir / "storage")),
        storage_mode=os.environ.get("STORAGE_MODE", "local").strip().lower(),
        allowed_extensions={"png"},
        cloudinary_cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip(),
        cloudinary_api_key=os.environ.get("CLOUDINARY_API_KEY", "").strip(),
        cloudinary_api_secret=os.environ.get("CLOUDINARY_API_SECRET", "").strip(),
        cloudinary_folder=os.environ.get("CLOUDINARY_FOLDER", "charts-library").strip().strip("/"),
    )
