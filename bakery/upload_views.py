from typing import Dict, List, Optional

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

try:
    import pandas as pd  # type: ignore
except ImportError:  # pragma: no cover - handled below
    pd = None  # type: ignore


REQUIRED_COLUMNS: Dict[str, List[str]] = {
    "sales": ["billed_at", "total"],
    "products": ["sku", "name", "price"],
    "inventory": ["product_sku", "qty", "unit_cost"],
    "kitchen": ["ingredient", "qty"],
}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_data(request):
    if pd is None:
        return Response({"error": "Server missing pandas/openpyxl"}, status=status.HTTP_400_BAD_REQUEST)

    upload_type = request.query_params.get("type")
    if upload_type not in REQUIRED_COLUMNS:
        return Response(
            {"error": "Invalid type parameter. Expected one of sales, products, inventory, kitchen."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    upload = request.FILES.get("file")
    if not upload:
        return Response({"error": "File is required."}, status=status.HTTP_400_BAD_REQUEST)

    name = upload.name or ""
    lowered = name.lower()
    df = None

    try:
        if lowered.endswith(".csv"):
            df = pd.read_csv(upload)
        elif lowered.endswith(".xlsx"):
            try:
                df = pd.read_excel(upload)  # requires openpyxl
            except ImportError:
                return Response(
                    {"error": "Server missing pandas/openpyxl"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {"error": "Unsupported file type. Upload .csv or .xlsx files."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except Exception as exc:  # broad: surface parsing errors
        return Response({"error": f"Failed to parse file: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

    missing = [col for col in REQUIRED_COLUMNS[upload_type] if col not in df.columns]
    if missing:
        return Response(
            {"error": f"Missing required columns: {', '.join(missing)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    total_rows = int(len(df))
    preview: Optional[List[Dict]] = df.head(3).to_dict(orient="records") if total_rows else []

    payload = {
        "status": "ok",
        "rows": total_rows,
        "type": upload_type,
    }
    if preview:
        payload["preview"] = preview

    return Response(payload, status=status.HTTP_200_OK)
