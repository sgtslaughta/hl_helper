from __future__ import annotations


from server.app.auth.password import (
    PasswordHasher,
    validate_password,
    check_hibp,
)


class TestPasswordHasher:
    def test_hash_and_verify_roundtrip(self) -> None:
        hasher = PasswordHasher()
        password = "Test1234!@#$"
        hashed = hasher.hash(password)

        assert hasher.verify(hashed, password)

    def test_verify_fails_wrong_password(self) -> None:
        hasher = PasswordHasher()
        password = "Test1234!@#$"
        hashed = hasher.hash(password)

        assert hasher.verify(hashed, "WrongPassword1!") is False

    def test_needs_rehash_false_with_default_params(self) -> None:
        hasher = PasswordHasher()
        password = "Test1234!@#$"
        hashed = hasher.hash(password)

        assert not hasher.needs_rehash(hashed)

    def test_needs_rehash_true_with_changed_params(self) -> None:
        hasher1 = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
        password = "Test1234!@#$"
        hashed = hasher1.hash(password)

        hasher2 = PasswordHasher(time_cost=5, memory_cost=65536, parallelism=4)
        assert hasher2.needs_rehash(hashed)

    def test_needs_rehash_true_with_higher_memory_cost(self) -> None:
        hasher1 = PasswordHasher(time_cost=3, memory_cost=32768, parallelism=4)
        password = "Test1234!@#$"
        hashed = hasher1.hash(password)

        hasher2 = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
        assert hasher2.needs_rehash(hashed)


class TestValidatePassword:
    def test_strong_password_accepted(self) -> None:
        errors = validate_password("Tr0ub4dor&3xy!")
        assert errors == []

    def test_password_too_short(self) -> None:
        errors = validate_password("Pass1!")
        assert "too_short" in errors

    def test_password_low_complexity(self) -> None:
        errors = validate_password("PASSWORD1234567")
        assert "low_complexity" in errors

    def test_password_contains_email(self) -> None:
        errors = validate_password(
            "User1234Pass!",
            user_context={"email": "user@example.com"}
        )
        assert "contains_user_info" in errors

    def test_password_contains_name(self) -> None:
        errors = validate_password(
            "MyPass123!",
            user_context={"name": "MyPass"}
        )
        assert "contains_user_info" in errors

    def test_password_with_no_user_context(self) -> None:
        errors = validate_password("Tr0ub4dor&3xy!")
        assert errors == []

    def test_password_with_empty_user_context(self) -> None:
        errors = validate_password("Tr0ub4dor&3xy!", user_context={})
        assert errors == []


class TestCheckHibp:
    def test_hibp_disabled_returns_false(self) -> None:
        sha1_hex = "a" * 40
        assert check_hibp(sha1_hex, fetch=None) is False

    def test_hibp_mock_hit(self) -> None:
        sha1_hex = "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8"

        def mock_fetch(prefix: str) -> bytes:
            return b"1E4C9B93F3F0682250B6CF8331B7EE68FD8:5\n"

        assert check_hibp(sha1_hex, fetch=mock_fetch) is True

    def test_hibp_mock_miss(self) -> None:
        sha1_hex = "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8"

        def mock_fetch(prefix: str) -> bytes:
            return b"0000000000000000000000000000000000000001:1\n"

        assert check_hibp(sha1_hex, fetch=mock_fetch) is False

    def test_hibp_sends_5_char_prefix(self) -> None:
        sha1_hex = "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8"
        prefixes_received = []

        def mock_fetch(prefix: str) -> bytes:
            prefixes_received.append(prefix)
            return b""

        check_hibp(sha1_hex, fetch=mock_fetch)

        assert len(prefixes_received) == 1
        assert prefixes_received[0] == "5baa6"
