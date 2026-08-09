from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from backend.catalog_service import CatalogService
from backend.excel_service import ExcelStockService, StockFileNotFoundError
from server import app


def settings(root: Path, **overrides):
    values = {
        "project_root": root,
        "product_data_path": root / "data" / "products.json",
        "wheel_images_root": root / "public" / "images" / "wheels",
        "inventory_dir": root / "data" / "inventory",
        "image_index_cache_ttl": 900,
        "stock_cache_ttl": 300,
        "local_scan_max_depth": 3,
        "stock_excel_filename": "",
        "stock_excel_filename_prefix": "台北庫存",
        "stock_worksheet_name": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CatalogMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        image_dir = self.root / "public" / "images" / "wheels" / "15" / "4x100"
        image_dir.mkdir(parents=True)
        (image_dir / "BBS-RI-A.jpg").write_bytes(b"bbs")
        (image_dir / "1663 古銅.jpg").write_bytes(b"bronze")
        (image_dir / "DW68S.jpg").write_bytes(b"fallback")
        self.service = CatalogService(settings(self.root))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_maps_hyphenated_local_name_from_product_name(self):
        products = [{
            "id": 1,
            "name": "BBS RI-A",
            "look": "",
            "size": 15,
            "spec": {"吋": "15", "孔徑": "4/100"},
        }]
        mapped, meta = self.service.map_products(products)
        self.assertEqual(mapped[0]["localImage"]["name"], "BBS-RI-A.jpg")
        self.assertTrue(mapped[0]["imageUrl"].endswith("/15/4x100/BBS-RI-A.jpg"))
        self.assertEqual(meta["mappedProductCount"], 1)

    def test_uses_size_pcd_model_and_finish(self):
        products = [{
            "id": 2,
            "model": "1663",
            "look": "古銅色",
            "spec": {"吋": "15", "孔徑": "4/100"},
        }]
        mapped, _ = self.service.map_products(products)
        self.assertEqual(mapped[0]["localImage"]["name"], "1663 古銅.jpg")
        self.assertIn("+pcd", mapped[0]["localImage"]["mappingStrategy"])
        self.assertIn("+finish", mapped[0]["localImage"]["mappingStrategy"])

    def test_uses_existing_catalog_filename_as_compatibility_fallback(self):
        products = [{
            "model": "#226",
            "look": "MBFP",
            "image": "DW68S.jpg",
            "spec": {"吋": "15", "孔徑": "4/100"},
        }]
        mapped, _ = self.service.map_products(products)
        self.assertEqual(mapped[0]["localImage"]["name"], "DW68S.jpg")
        self.assertIn("catalog-filename", mapped[0]["localImage"]["mappingStrategy"])

    def test_local_image_index_is_cached_until_refresh(self):
        first_count = len(self.service.get_image_index()["images"])
        new_image = self.root / "public" / "images" / "wheels" / "15" / "new.jpg"
        new_image.write_bytes(b"new")
        self.assertEqual(len(self.service.get_image_index()["images"]), first_count)
        self.assertEqual(
            len(self.service.get_image_index(force_refresh=True)["images"]),
            first_count + 1,
        )


class ExcelStockTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        inventory_dir = self.root / "data" / "inventory"
        inventory_dir.mkdir(parents=True)

        for filename, quantity, timestamp in (
            ("台北庫存115.8.1.xlsx", 3, 1_700_000_000),
            ("台北庫存115.8.7.xlsx", 8, 1_800_000_000),
        ):
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "台北庫存"
            sheet.append(["產品型號", "吻數", "庫存量"])
            sheet.append(["BBS RI-A", 15, quantity])
            path = inventory_dir / filename
            workbook.save(path)
            workbook.close()
            os.utime(path, (timestamp, timestamp))

        self.service = ExcelStockService(settings(self.root))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_selects_latest_excel_by_prefix_and_modified_time(self):
        latest = self.service.find_latest_file()
        self.assertEqual(latest["name"], "台北庫存115.8.7.xlsx")

    def test_parses_local_excel_and_merges_inventory(self):
        snapshot = self.service.get_snapshot()
        self.assertEqual(snapshot["rowCount"], 1)
        products = [{"model": "BBS RI-A", "spec": {"吋": "15"}}]
        merged, meta = self.service.merge_inventory(products, snapshot)
        self.assertEqual(merged[0]["inventory"]["quantity"], 8)
        self.assertEqual(meta["merged"], 1)

    def test_missing_excel_returns_clear_error(self):
        empty_root = self.root / "empty"
        empty = ExcelStockService(settings(empty_root))
        with self.assertRaisesRegex(StockFileNotFoundError, "台北庫存"):
            empty.find_latest_file()


class StaticFileSecurityTests(unittest.TestCase):
    def test_only_intended_local_assets_are_public(self):
        client = app.test_client()
        for path in (
            "/.env",
            "/server.py",
            "/backend/config.py",
            "/data/inventory/README.md",
            "/public/%2e%2e/server.py",
        ):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 404)
                response.close()

        response = client.get("/public/images/wheels/21/050.jpg")
        self.assertEqual(response.status_code, 200)
        response.close()


if __name__ == "__main__":
    unittest.main()
