"""Authentication entry points with JSON-only responses."""

from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


def _tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def login_flexible(request):
    """Accept multiple credential keys and return JWT pair."""

    data = request.data or {}
    identifier = (
        data.get("usernameOrEmail")
        or data.get("username")
        or data.get("email")
        or ""
    ).strip()
    password = (data.get("password") or "").strip()

    if not identifier or not password:
        return Response({"detail": "Missing credentials."}, status=status.HTTP_400_BAD_REQUEST)

    user_obj = User.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier)
    ).first()
    if not user_obj:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    user = authenticate(request, username=user_obj.username, password=password)
    if not user:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response({"detail": "User inactive."}, status=status.HTTP_403_FORBIDDEN)

    tokens = _tokens_for_user(user)
    return Response(
        {
            **tokens,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_superuser": getattr(user, "is_superuser", False),
                "is_staff": getattr(user, "is_staff", False),
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_view(request):
    """Exchange a refresh token for a new access token."""

    token = request.data.get("refresh")
    if not token:
        return Response({"detail": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        refresh = RefreshToken(token)
        access = refresh.access_token
    except TokenError:
        return Response({"detail": "Invalid refresh token"}, status=status.HTTP_401_UNAUTHORIZED)

    return Response({"access": str(access)}, status=status.HTTP_200_OK)
