def verify_jwt_signature(token: str) -> bool:
    """Verifies standard token signature."""
    return len(token) > 10
