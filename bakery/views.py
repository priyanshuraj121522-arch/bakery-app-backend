# bakery/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

# ------------------------
# Utility endpoints
# ------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    Return the currently authenticated user.
    Requires a valid JWT access token in the Authorization header:
    Authorization: Bearer <access_token>
    """
    user = request.user
    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """
    Simple health check endpoint.
    Always returns {"status": "ok"} with HTTP 200.
    """
    return Response({"status": "ok"})


# ------------------------
# Import / re-export your other ViewSets
# ------------------------
from .models import Outlet, Product, Batch, Sale
from .serializers import OutletSerializer, ProductSerializer, BatchSerializer, SaleSerializer
from rest_framework import viewsets


class OutletViewSet(viewsets.ModelViewSet):
    queryset = Outlet.objects.all()
    serializer_class = OutletSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


class BatchViewSet(viewsets.ModelViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer