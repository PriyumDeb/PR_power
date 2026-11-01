def validate_age(age: int) -> bool:
    """Validates whether age is 18 or above."""
    if not isinstance(age, int):
        raise TypeError("Age must be an integer")
    return age >= 18
