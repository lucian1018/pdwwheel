from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    project_root: Path
    product_data_path: Path
    wheel_images_root: Path
    inventory_dir: Path
    stock_excel_filename: str
    stock_excel_filename_prefix: str
    stock_worksheet_name: str
    image_index_cache_ttl: int
    stock_cache_ttl: int
    local_scan_max_depth: int
    host: str
    port: int
    debug: bool

    @classmethod
    def local(cls) -> "Settings":
        return cls(
            project_root=PROJECT_ROOT,
            product_data_path=PROJECT_ROOT / "data" / "products.json",
            wheel_images_root=PROJECT_ROOT / "public" / "images" / "wheels",
            inventory_dir=PROJECT_ROOT / "data" / "inventory",
            stock_excel_filename="",
            stock_excel_filename_prefix="台北庫存",
            stock_worksheet_name="",
            image_index_cache_ttl=30,
            stock_cache_ttl=30,
            local_scan_max_depth=3,
            host="127.0.0.1",
            port=8000,
            debug=False,
        )
