# bakery/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

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
        "email": user.email,
    })

@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Simple health check endpoint.
    Useful for frontend / API tests.
    """
    return Response({"status": "ok"})