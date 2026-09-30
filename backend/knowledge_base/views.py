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
        title = request.data.get("title", "")
        content = request.data.get("content", "")
        source = request.data.get("source", "")
        if not isinstance(title, str) or not title.strip() or len(title) > 255:
            return Response({"title": "A title of 1 to 255 characters is required."}, status=400)
        if not isinstance(content, str) or not content.strip() or len(content) > 100_000:
            return Response({"content": "Content must contain 1 to 100,000 characters."}, status=400)
        if not isinstance(source, str) or len(source) > 255:
            return Response({"source": "Source must be at most 255 characters."}, status=400)
        document = index_document(
            title=title.strip(),
            content=content,
            source=source,
        )
        return Response(self.get_serializer(document).data, status=status.HTTP_201_CREATED)
