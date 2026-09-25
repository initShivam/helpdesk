from django.test import TestCase


class HealthEndpointTests(TestCase):
    def test_health_reports_database_status(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_health_rejects_non_get_requests(self):
        response = self.client.post("/health/")

        self.assertEqual(response.status_code, 405)
