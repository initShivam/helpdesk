from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from .models import Document
from .serializers import DocumentSerializer
from .services import index_document, index_uploaded_file


class IsStaffOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or getattr(request.user, "role", "") == "ADMIN")
        )


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all().order_by("-updated_at")
    serializer_class = DocumentSerializer
    permission_classes = [IsStaffOrAdmin]

    def create(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload:
            document = index_uploaded_file(upload)
            return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)
        document = index_document(
            title=request.data.get("title", ""),
            content=request.data.get("content", ""),
            source=request.data.get("source", ""),
        )
        return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)
