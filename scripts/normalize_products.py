import json
import re
import unicodedata
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_PATH = PROJECT_ROOT / "data" / "products.json"
IMAGE_DIR = PROJECT_ROOT / "images"
VALID_PROCESSES = ("鍛造", "旋壓", "鑄造")
MISSING_IMAGE_VALUES = {"", "-", "-or-760"}

IMAGE_FILES = sorted(
    (item.name for item in IMAGE_DIR.iterdir() if item.is_file() and item.name != ".DS_Store"),
    key=str.casefold,
)

MANUAL_IMAGE_MAP = {
    ("050", "鍛造-消光黑"): "050.jpg",
    ("1550", "MGM_灰車面"): "1550灰車面.PNG",
    ("1559", "S"): "1559銀色.JPG",
    ("2256", "銀色"): "2256 銀車面.jpg",
    ("C-63", "鋼琴黑車邊"): "C63亮黑車邊.JPG",
    ("C-63", "消光黑車邊"): "C63消光黑車邊.PNG",
    ("851", "消光黑紅線"): "851黑紅車邊.JPG",
    ("933", "黑紅邊"): "933黑紅車邊.JPG",
    ("DW68", "銀色"): "DW68S.jpg",
    ("M317A", "消光黑"): "M317消光黑.PNG",
    ("S514", "銀車面"): "514 銀車面.jpg",
}


def remove_extension(value: str) -> str:
    return re.sub(r"\.(webp|jpe?g|png)$", "", value, flags=re.IGNORECASE)


def strict_key(value: str = "") -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).lower()
    normalized = remove_extension(normalized).replace("電渡", "電鍍")
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def loose_key(value: str = "") -> str:
    normalized = strict_key(value)
    normalized = re.sub(r"(旋壓|鍛造|鑄造)", "", normalized)
    return normalized.replace("色", "")


FILE_INDEX = [
    {"name": name, "strict": strict_key(name), "loose": loose_key(name)}
    for name in IMAGE_FILES
]


def unique_match(matches: list[dict]) -> str:
    return matches[0]["name"] if len(matches) == 1 else ""


def resolve_image(product: dict) -> str:
    existing = product.get("image", "").strip()
    if existing in IMAGE_FILES:
        return existing

    manual = MANUAL_IMAGE_MAP.get((product.get("model", ""), product.get("look", "")))
    if manual in IMAGE_FILES:
        return manual

    base = product.get("imageBase", "").strip()
    if base not in MISSING_IMAGE_VALUES:
        strict_base = strict_key(base)
        match = unique_match([item for item in FILE_INDEX if item["strict"] == strict_base])
        if match:
            return match

        loose_base = loose_key(base)
        match = unique_match([item for item in FILE_INDEX if item["loose"] == loose_base])
        if match:
            return match

    model = strict_key(product.get("model", ""))
    finish = loose_key(product.get("look", ""))
    if not model or len(finish) < 2:
        return ""

    return unique_match(
        [item for item in FILE_INDEX if model in item["strict"] and finish in item["loose"]]
    )


def normalize_number(value: str = "") -> str:
    text = str(value).strip().removeprefix("+")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else str(number)


def normalize_pcd(value: str = "") -> str:
    text = str(value).strip()
    return {"4/114": "4/114.3", "5/114": "5/114.3"}.get(text, text)


def find_process(product: dict) -> str:
    source = " ".join(
        str(product.get(key, "")) for key in ("category", "desc", "look", "imageBase")
    )
    return next((process for process in VALID_PROCESSES if process in source), "")


def normalize_product(product: dict) -> dict:
    spec = product.get("spec", {})
    return {
        "model": str(product.get("model", "")).strip(),
        "look": str(product.get("look", "")).strip(),
        "category": find_process(product),
        "spec": {
            "吋": str(spec.get("吋", "")).strip(),
            "孔徑": normalize_pcd(spec.get("孔徑", "")),
            "ET值": normalize_number(spec.get("ET值", "")),
            "J值": normalize_number(spec.get("J值", "")),
            "中心孔": normalize_number(spec.get("中心孔", "")),
        },
        "image": resolve_image(product),
    }


source_products = json.loads(PRODUCT_PATH.read_text(encoding="utf-8"))
normalized_products = [normalize_product(product) for product in source_products]

deduplicated = []
seen = set()
for product in normalized_products:
    key = json.dumps(product, ensure_ascii=False, sort_keys=True)
    if key in seen:
        continue
    seen.add(key)
    deduplicated.append(product)

output = [{"id": index, **product} for index, product in enumerate(deduplicated, start=1)]
serialized = "[\n  " + ",\n  ".join(
    json.dumps(product, ensure_ascii=False, separators=(",", ":")) for product in output
) + "\n]\n"
PRODUCT_PATH.write_text(serialized, encoding="utf-8")

with_images = sum(bool(product["image"]) for product in output)
categorized = sum(bool(product["category"]) for product in output)
print(json.dumps({
    "sourceRecords": len(source_products),
    "outputRecords": len(output),
    "removedDuplicates": len(source_products) - len(output),
    "withImages": with_images,
    "missingImages": len(output) - with_images,
    "categorized": categorized,
    "uncategorized": len(output) - categorized,
}, ensure_ascii=False, indent=2))
