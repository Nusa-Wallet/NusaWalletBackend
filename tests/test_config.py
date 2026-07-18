import unittest

from pydantic import ValidationError

from app.core.config import Settings


class ConfigTest(unittest.TestCase):
    def test_development_defaults_are_demo_friendly(self):
        settings = Settings(_env_file=None)

        self.assertFalse(settings.is_production)
        self.assertTrue(settings.auto_create_tables)
        self.assertIn("http://localhost:8081", settings.cors_origins)

    def test_production_rejects_default_secret(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                app_env="production",
                auto_create_tables=False,
                cors_allow_origins="https://app.nusawallet.id",
            )

    def test_production_rejects_wildcard_cors(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                app_env="production",
                jwt_secret="replace-with-a-long-random-secret",
                auto_create_tables=False,
                cors_allow_origins="*",
            )

    def test_production_rejects_auto_create_tables(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                app_env="production",
                jwt_secret="replace-with-a-long-random-secret",
                auto_create_tables=True,
                cors_allow_origins="https://app.nusawallet.id",
            )


if __name__ == "__main__":
    unittest.main()
