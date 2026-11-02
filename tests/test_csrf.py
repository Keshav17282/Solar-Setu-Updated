import os
import re
import tempfile
import unittest

from app import create_app
from app.config import Config
from app.models import db


class CsrfProtectionTests(unittest.TestCase):
    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_file.close()
        self.original_uri = Config.SQLALCHEMY_DATABASE_URI
        self.original_database_url = Config.DATABASE_URL
        Config.DATABASE_URL = None
        Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.db_file.name}"
        self.app = create_app(skip_seed=True)
        self.app.config.update(TESTING=True, SECRET_KEY="csrf-test-secret")
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        Config.SQLALCHEMY_DATABASE_URI = self.original_uri
        Config.DATABASE_URL = self.original_database_url
        os.unlink(self.db_file.name)

    def _token(self):
        response = self.client.get("/settings")
        match = re.search(r'name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match)
        return match.group(1)

    def test_form_post_rejects_missing_token(self):
        response = self.client.post("/settings", data={"property_type": "residential"})
        self.assertEqual(response.status_code, 400)

    def test_form_post_rejects_invalid_token(self):
        response = self.client.post(
            "/settings",
            data={"property_type": "residential", "csrf_token": "invalid-token"},
        )
        self.assertEqual(response.status_code, 400)

    def test_form_post_accepts_valid_token(self):
        token = self._token()
        response = self.client.post(
            "/settings",
            data={"property_type": "commercial", "csrf_token": token},
        )
        self.assertEqual(response.status_code, 200)

    def test_json_post_rejects_missing_token(self):
        response = self.client.post(
            "/api/comparisons",
            json={"solution_ids": [1], "location_id": None},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "CSRF validation failed."})

    def test_json_post_rejects_invalid_token(self):
        response = self.client.post(
            "/api/comparisons",
            json={"solution_ids": [1], "location_id": None},
            headers={"X-CSRFToken": "invalid-token"},
        )
        self.assertEqual(response.status_code, 400)

    def test_json_post_accepts_valid_token(self):
        token = self._token()
        response = self.client.post(
            "/api/comparisons",
            json={"solution_ids": [1], "location_id": None},
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
