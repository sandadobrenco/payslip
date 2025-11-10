from rest_framework import exceptions
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class ManagerTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["is_manager"] = bool(getattr(user, "is_manager", False))
        token["is_top_manager"] = bool(getattr(user, "is_manager", False) and getattr(user, "manager_id", None) is None)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        if not user.is_active:
            raise exceptions.AuthenticationFailed("Inactive account")

        if not (getattr(user, "is_manager", False) or user.is_superuser):
            raise exceptions.AuthenticationFailed("Only managers can obtain API tokens")

        data["user_id"] = user.id
        data["username"] = user.get_username()
        data["is_manager"] = bool(getattr(user, "is_manager", False))
        data["is_top_manager"] = bool(getattr(user, "is_manager", False) and getattr(user, "manager_id", None) is None)
        return data

class ManagerTokenObtainPairView(TokenObtainPairView):
    serializer_class = ManagerTokenObtainPairSerializer
