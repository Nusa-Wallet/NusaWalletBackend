"""Authentication regression tests for JSON and Swagger OAuth2 login flows."""

import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

        def override_db():
            db = TestingSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_login_token_authenticates_me(self):
        email = "auth-test@nusawallet.id"
        password = "password123"
        register = self.client.post(
            "/auth/register",
            json={
                "email": email,
                "full_name": "Auth Test",
                "password": password,
            },
        )
        self.assertEqual(register.status_code, 201, register.text)

        login = self.client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(login.status_code, 200, login.text)
        body = login.json()
        self.assertEqual(body["token_type"], "bearer")

        me = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], email)
        self.assertEqual(me.json()["full_name"], "Auth Test")

    def test_phone_login_normalizes_country_code(self):
        email = "phone-auth-test@nusawallet.id"
        phone = "081298765432"
        password = "password123"
        register = self.client.post(
            "/auth/register",
            json={
                "email": email,
                "phone": phone,
                "full_name": "Phone Auth Test",
                "password": password,
            },
        )
        self.assertEqual(register.status_code, 201, register.text)

        login = self.client.post(
            "/auth/login",
            json={"phone": "+62 812-9876-5432", "password": password},
        )
        self.assertEqual(login.status_code, 200, login.text)

        me = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], email)
        self.assertEqual(me.json()["phone"], phone)

    def test_login_requires_exactly_one_identifier(self):
        both = self.client.post(
            "/auth/login",
            json={
                "email": "auth-test@nusawallet.id",
                "phone": "081298765432",
                "password": "password123",
            },
        )
        neither = self.client.post("/auth/login", json={"password": "password123"})

        self.assertEqual(both.status_code, 422, both.text)
        self.assertEqual(neither.status_code, 422, neither.text)

    def test_oauth2_form_token_authenticates_me(self):
        email = "swagger-auth-test@nusawallet.id"
        password = "password123"
        register = self.client.post(
            "/auth/register",
            json={
                "email": email,
                "full_name": "Swagger Auth Test",
                "password": password,
            },
        )
        self.assertEqual(register.status_code, 201, register.text)

        token = self.client.post(
            "/auth/token",
            data={"username": email, "password": password},
        )
        self.assertEqual(token.status_code, 200, token.text)
        body = token.json()
        self.assertEqual(body["token_type"], "bearer")

        me = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], email)

    def test_oauth2_form_rejects_invalid_credentials(self):
        response = self.client.post(
            "/auth/token",
            data={"username": "missing@nusawallet.id", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid credentials")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_oauth2_form_accepts_phone_as_username(self):
        email = "swagger-phone-test@nusawallet.id"
        password = "password123"
        register = self.client.post(
            "/auth/register",
            json={
                "email": email,
                "phone": "081377766655",
                "full_name": "Swagger Phone Test",
                "password": password,
            },
        )
        self.assertEqual(register.status_code, 201, register.text)

        token = self.client.post(
            "/auth/token",
            data={"username": "6281377766655", "password": password},
        )
        self.assertEqual(token.status_code, 200, token.text)

    def test_me_without_bearer_token_is_unauthorized(self):
        response = self.client.get("/auth/me")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Not authenticated")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_me_with_invalid_token_is_unauthorized(self):
        response = self.client.get(
            "/auth/me",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid or expired token")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")


if __name__ == "__main__":
    unittest.main()
