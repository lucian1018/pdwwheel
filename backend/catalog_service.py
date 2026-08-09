from __future__ import annotations

import json
import mimetypes
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from cachetools import TTLCache

from .config import Settings


SIZE_FOLDER_PATTERN = re.compile(r"^(1[3-9]|2[0-2])$")
PCD_FOLDER_PATTERN = re.compile(r"([4568])\s*[*xX/]\s*(\d+(?:\.\d+)?)")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    text = re.sub(r"\.(JPE?G|PNG|WEBP|GIF|AVIF)\s*$", "", text, flags=re.IGNORECASE)
    text = text.replace("電渡", "電鍍")
    text = re.sub(r"(旋壓|鍛造|鑄造)", "", text)
    text = text.replace("色", "")
    return re.sub(r"[^0-9A-Z\u4E00-\u9FFF]+", "", text)


def normalize_pcd(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    text = re.sub(r"\s+", "", text).replace("*", "/").replace("X", "/")
    if text == "4/114":
        return "4/114.3"
    if text == "5/114":
        return "5/114.3"
    return text


def extract_pcd(folder_name: str) -> str:
    match = PCD_FOLDER_PATTERN.search(unicodedata.normalize("NFKC", folder_name))
    return normalize_pcd(f"{match.group(1)}/{match.group(2)}") if match else ""


def iso_modified_time(path: Path) -> str:
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return modified.isoformat().replace("+00:00", "Z")


class CatalogService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._index_cache: TTLCache = TTLCache(
            maxsize=1,
            ttl=settings.image_index_cache_ttl,
        )

    def load_base_products(self) -> list[dict[str, Any]]:
        return json.loads(self.settings.product_data_path.read_text(encoding="utf-8"))

    def get_image_index(self, force_refresh: bool = False) -> dict[str, Any]:
        if force_refresh:
            self._index_cache.clear()
        if "index" in self._index_cache:
            return self._index_cache["index"]

        root = self.settings.wheel_images_root
        root.mkdir(parents=True, exist_ok=True)
        images: list[dict[str, Any]] = []
        folders: dict[str, dict[str, Any]] = {}

        for size_folder in sorted(root.iterdir(), key=lambda path: path.name):
            if not size_folder.is_dir() or not SIZE_FOLDER_PATTERN.fullmatch(size_folder.name):
                continue
            size = int(size_folder.name)
            folders[str(size)] = {
                "name": size_folder.name,
                "relativePath": size_folder.relative_to(self.settings.project_root).as_posix(),
            }
            self._scan_folder(
                folder=size_folder,
                size=size,
                pcd="",
                depth=0,
                output=images,
            )

        index = {
            "root": root,
            "folders": folders,
            "images": images,
        }
        self._index_cache["index"] = index
        return index

    def _scan_folder(
        self,
        folder: Path,
        size: int,
        pcd: str,
        depth: int,
        output: list[dict[str, Any]],
    ) -> None:
        for path in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
            if path.is_dir():
                if depth >= self.settings.local_scan_max_depth:
                    continue
                self._scan_folder(
                    folder=path,
                    size=size,
                    pcd=extract_pcd(path.name) or pcd,
                    depth=depth + 1,
                    output=output,
                )
                continue

            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            relative_path = path.relative_to(self.settings.wheel_images_root)
            public_path = Path("public") / "images" / "wheels" / relative_path
            output.append({
                "path": path,
                "name": path.name,
                "mimeType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "relativePath": relative_path.as_posix(),
                "folderPath": list(relative_path.parent.parts),
                "size": size,
                "pcd": pcd,
                "modifiedTime": iso_modified_time(path),
                "modifiedTimeNs": path.stat().st_mtime_ns,
                "sizeBytes": path.stat().st_size,
                "nameKey": normalize_name(path.name),
                "url": f"/{quote(public_path.as_posix(), safe='/')}",
            })

    def map_products(
        self,
        products: list[dict[str, Any]],
        force_refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        index = self.get_image_index(force_refresh=force_refresh)
        images = index["images"]
        mapped_products = []
        mapped_count = 0

        for source_product in products:
            product = deepcopy(source_product)
            image, strategy, score = self._find_best_image(product, images)

            if image:
                product["imageUrl"] = image["url"]
                product["localImage"] = {
                    "name": image["name"],
                    "mimeType": image["mimeType"],
                    "relativePath": image["relativePath"],
                    "folderPath": image["folderPath"],
                    "modifiedTime": image["modifiedTime"],
                    "mappingStrategy": strategy,
                    "mappingScore": score,
                }
                mapped_count += 1
            else:
                product["imageUrl"] = ""
                product["localImage"] = None

            mapped_products.append(product)

        return mapped_products, {
            "localImageCount": len(images),
            "mappedProductCount": mapped_count,
            "unmappedProductCount": len(products) - mapped_count,
            "sizeFolders": index["folders"],
            "cacheTtlSeconds": self.settings.image_index_cache_ttl,
        }

    def _find_best_image(
        self,
        product: dict[str, Any],
        images: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str, int]:
        spec = product.get("spec", {})
        try:
            size = int(product.get("size") or spec.get("吋"))
        except (TypeError, ValueError):
            return None, "missing-size", 0

        model = product.get("name") or product.get("model") or ""
        model_key = normalize_name(model)
        finish_key = normalize_name(product.get("look", ""))
        product_pcd = normalize_pcd(product.get("pcd") or spec.get("孔徑"))
        if not model_key:
            return None, "missing-name", 0

        size_candidates = [image for image in images if image["size"] == size]
        if not size_candidates:
            return None, "size-folder-not-found", 0

        exact_pcd = [image for image in size_candidates if image["pcd"] == product_pcd]
        candidates = exact_pcd or size_candidates
        scored: list[tuple[int, str, dict[str, Any]]] = []

        for image in candidates:
            image_key = image["nameKey"]
            safe_prefix = image_key.startswith(model_key) and not (
                model_key.isdigit()
                and len(image_key) > len(model_key)
                and image_key[len(model_key)].isdigit()
            )

            if image_key == model_key:
                base_score = 130
                strategy = "exact-name"
            elif safe_prefix:
                base_score = 110
                strategy = "name-prefix"
            elif not model_key.isdigit() and model_key in image_key:
                base_score = 90
                strategy = "name-contains"
            else:
                continue

            if product_pcd and image["pcd"] == product_pcd:
                base_score += 20
                strategy += "+pcd"
            if finish_key and finish_key in image_key:
                base_score += 25
                strategy += "+finish"

            scored.append((base_score, strategy, image))

        if not scored:
            configured_image_key = normalize_name(product.get("image", ""))
            if configured_image_key:
                configured_candidates = [
                    image for image in candidates
                    if image["nameKey"] == configured_image_key
                ]
                if configured_candidates:
                    configured_candidates.sort(
                        key=lambda image: (image["modifiedTimeNs"], image["name"]),
                        reverse=True,
                    )
                    strategy = "catalog-filename"
                    score = 80
                    if product_pcd and configured_candidates[0]["pcd"] == product_pcd:
                        strategy += "+pcd"
                        score += 20
                    return configured_candidates[0], strategy, score

            return None, "name-not-found", 0

        scored.sort(
            key=lambda item: (item[0], item[2]["modifiedTimeNs"], item[2]["name"]),
            reverse=True,
        )
        score, strategy, image = scored[0]
        return image, strategy, score
