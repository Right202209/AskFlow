import pytest

from askflow.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestSecurity:
    def test_hash_and_verify_password(self):
        password = "test_password_123"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrong_password", hashed)

    def test_create_and_decode_token(self):
        data = {"sub": "user-id-123", "role": "admin"}
        token = create_access_token(data)
        decoded = decode_access_token(token)
        assert decoded["sub"] == "user-id-123"
        assert decoded["role"] == "admin"
        assert "exp" in decoded

    def test_invalid_token_raises(self):
        with pytest.raises(Exception):
            decode_access_token("invalid-token")
