import os
import tempfile
import unittest
from unittest import mock

from app import create_app
from app.config import Config
from app.models import (
    db,
    seed_application_reference_data,
    _seed_application_reference_data_postgresql,
    SubsidyScheme,
    TariffTable,
)


class StartupDatabaseTests(unittest.TestCase):
    def setUp(self):
        database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        database_file.close()
        self.database_path = database_file.name
        self.original_uri = Config.SQLALCHEMY_DATABASE_URI
        self.original_database_url = Config.DATABASE_URL
        Config.DATABASE_URL = None
        Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{self.database_path}"

    def tearDown(self):
        if hasattr(self, "app"):
            with self.app.app_context():
                db.session.remove()
                db.engine.dispose()
        Config.SQLALCHEMY_DATABASE_URI = self.original_uri
        Config.DATABASE_URL = self.original_database_url
        if os.path.exists(self.database_path):
            os.unlink(self.database_path)

    def test_database_initialization_then_fresh_request(self):
        app = create_app(skip_seed=True)
        self.app = app
        app.config.update(TESTING=True, SECRET_KEY="startup-test-secret")

        with app.app_context():
            db.create_all()
            seed_application_reference_data()
            db.session.remove()

        response = app.test_client().get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_repeated_reference_data_seeding_is_idempotent(self):
        app = create_app(skip_seed=True)
        self.app = app

        with app.app_context():
            db.create_all()
            seed_application_reference_data()
            seed_application_reference_data()
            tariff_count = TariffTable.query.count()
            subsidy_count = SubsidyScheme.query.count()

        self.assertEqual(tariff_count, 8)
        self.assertEqual(subsidy_count, 3)

    def test_reference_data_seeding_exception_rolls_back_session(self):
        app = create_app(skip_seed=True)
        self.app = app

        with app.app_context():
            db.create_all()
            with mock.patch(
                "app.models.seed_real_installers",
                side_effect=RuntimeError("seed failed"),
            ), mock.patch.object(db.session, "rollback") as rollback:
                with self.assertRaisesRegex(RuntimeError, "seed failed"):
                    seed_application_reference_data()

                rollback.assert_called_once_with()

    def test_postgresql_transaction_lock_never_explicitly_unlocks(self):
        statements = []
        transaction = mock.MagicMock()

        class TransactionConnection:
            def __enter__(self):
                return transaction

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        class LockEngine:
            def begin(self):
                return TransactionConnection()

        def capture(statement):
            statements.append(str(statement))

        transaction.execute.side_effect = capture
        with mock.patch("app.models.seed_solar_solutions"), mock.patch(
            "app.models.seed_real_installers"
        ), mock.patch("app.models.seed_reference_data"):
            _seed_application_reference_data_postgresql(LockEngine())

        self.assertEqual(
            statements,
            ["SELECT pg_advisory_xact_lock(867530912)"],
        )


if __name__ == "__main__":
    unittest.main()
