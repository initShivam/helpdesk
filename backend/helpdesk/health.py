from django.db import connection
from django.http import JsonResponse


def health(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unhealthy", "database": "unavailable"}, status=503)

    return JsonResponse({"status": "ok", "database": "ok"})
