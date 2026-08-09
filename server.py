from __future__ import annotations

from typing import Any

from flask import Flask, abort, jsonify, request, send_from_directory

from backend.catalog_service import CatalogService
from backend.config import Settings
from backend.excel_service import ExcelStockService, StockFileNotFoundError


PUBLIC_FILES = {"index.html", "productlist.html", "data/products.json"}
PUBLIC_DIRECTORIES = ("assets", "public")


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.local()
    app = Flask(__name__, static_folder=None)

    catalog_service = CatalogService(settings)
    stock_service = ExcelStockService(settings)

    def force_refresh_requested() -> bool:
        return request.args.get("refresh", "").lower() in {"1", "true", "yes"}

    @app.get("/api/health")
    def health():
        return jsonify({
            "ok": True,
            "source": "local-files",
            "imageDirectoryReady": settings.wheel_images_root.is_dir(),
            "inventoryDirectoryReady": settings.inventory_dir.is_dir(),
        })

    @app.get("/api/catalog")
    def catalog():
        force_refresh = force_refresh_requested()
        products = catalog_service.load_base_products()
        warnings: list[str] = []
        image_meta: dict[str, Any] = {
            "localImageCount": 0,
            "mappedProductCount": 0,
            "unmappedProductCount": len(products),
        }
        stock_meta: dict[str, Any] = {
            "available": False,
            "merged": 0,
        }

        try:
            products, image_meta = catalog_service.map_products(
                products,
                force_refresh=force_refresh,
            )
        except OSError as exc:
            warnings.append(f"本機圖片索引失敗：{exc}")

        try:
            snapshot = stock_service.get_snapshot(force_refresh=force_refresh)
            products, merge_meta = stock_service.merge_inventory(products, snapshot)
            stock_meta = {
                "available": True,
                "file": snapshot["file"],
                "worksheet": snapshot["worksheet"],
                "rowCount": snapshot["rowCount"],
                **merge_meta,
            }
            warnings.extend(merge_meta.get("warnings", []))
        except StockFileNotFoundError as exc:
            stock_meta["error"] = str(exc)
            warnings.append(str(exc))
        except (OSError, ValueError) as exc:
            stock_meta["error"] = str(exc)
            warnings.append(str(exc))

        response = jsonify({
            "products": products,
            "meta": {
                "source": "local-files",
                "images": image_meta,
                "stock": stock_meta,
                "warnings": list(dict.fromkeys(warnings)),
            },
        })
        response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
        return response

    @app.get("/api/stock/latest")
    def latest_stock():
        try:
            return jsonify(stock_service.get_snapshot(
                force_refresh=force_refresh_requested(),
            ))
        except StockFileNotFoundError as exc:
            return jsonify({
                "error": str(exc),
                "directory": settings.inventory_dir.relative_to(settings.project_root).as_posix(),
                "selection": {
                    "exactFilename": settings.stock_excel_filename or None,
                    "filenamePrefix": settings.stock_excel_filename_prefix or None,
                    "rule": "精確檔名優先，否則以前綴篩選後取本機修改時間最新檔案",
                },
            }), 404
        except (OSError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 422

    @app.get("/")
    def index():
        return send_from_directory(settings.project_root, "index.html")

    @app.get("/<path:asset_path>")
    def static_asset(asset_path: str):
        if asset_path in PUBLIC_FILES:
            return send_from_directory(settings.project_root, asset_path)

        for public_directory in PUBLIC_DIRECTORIES:
            prefix = f"{public_directory}/"
            if asset_path.startswith(prefix):
                relative_path = asset_path.removeprefix(prefix)
                return send_from_directory(
                    settings.project_root / public_directory,
                    relative_path,
                )

        abort(404)

    return app


app = create_app()


if __name__ == "__main__":
    current_settings = Settings.local()
    app.run(
        host=current_settings.host,
        port=current_settings.port,
        debug=current_settings.debug,
    )
