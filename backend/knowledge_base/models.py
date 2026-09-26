from django.db import models


class Document(models.Model):
    title = models.CharField(max_length=255)
    source = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    content = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["document_id", "position"]
