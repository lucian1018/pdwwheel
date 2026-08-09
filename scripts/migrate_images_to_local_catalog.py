#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_DATA = PROJECT_ROOT / "data" / "products.json"
LEGACY_IMAGES = PROJECT_ROOT / "images"
TARGET_ROOT = PROJECT_ROOT / "public" / "images" / "wheels"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    text = re.sub(r"\.(JPE?G|PNG|WEBP|GIF|AVIF)\s*$", "", text, flags=re.IGNORECASE)
    text = text.replace("電渡", "電鍍")
    text = re.sub(r"(旋壓|鍛造|鑄造)", "", text).replace("色", "")
    return re.sub(r"[^0-9A-Z\u4E00-\u9FFF]+", "", text)


def main() -> None:
    products = json.loads(PRODUCT_DATA.read_text(encoding="utf-8"))
    image_sizes: dict[str, set[str]] = defaultdict(set)
    model_sizes: dict[str, set[str]] = defaultdict(set)

    for product in products:
        size = str(product.get("size") or product.get("spec", {}).get("吋") or "").strip()
        if not size:
            continue
        image_name = str(product.get("image") or "").strip()
        if image_name:
            image_sizes[image_name].add(size)
        model_key = normalize_name(product.get("name") or product.get("model"))
        if model_key:
            model_sizes[model_key].add(size)

    for size in range(13, 23):
        (TARGET_ROOT / str(size)).mkdir(parents=True, exist_ok=True)

    copied_files = 0
    source_files = 0
    unassigned_files = 0
    for source in sorted(LEGACY_IMAGES.iterdir(), key=lambda path: path.name.casefold()):
        if not source.is_file() or source.name.startswith(".") or source.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        source_files += 1
        sizes = set(image_sizes.get(source.name, set()))

        if not sizes:
            file_key = normalize_name(source.name)
            matches = [
                (len(model_key), values)
                for model_key, values in model_sizes.items()
                if file_key.startswith(model_key)
            ]
            if matches:
                sizes.update(max(matches, key=lambda item: item[0])[1])

        if not sizes:
            unassigned = TARGET_ROOT / "unassigned"
            unassigned.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, unassigned / source.name)
            copied_files += 1
            unassigned_files += 1
            continue

        for size in sorted(sizes, key=int):
            shutil.copy2(source, TARGET_ROOT / size / source.name)
            copied_files += 1

    print(f"已處理 {source_files} 張舊圖片，建立 {copied_files} 個尺寸圖片檔案。")
    print(f"無法判定尺寸者 {unassigned_files} 張，已放入 unassigned/。")


if __name__ == "__main__":
    main()
