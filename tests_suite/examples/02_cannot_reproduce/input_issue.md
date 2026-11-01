### Bug Report: `validator.validate_age` crashes on positive integers

Calling `validate_age(25)` crashes with an unexpected `ValueError`.

#### Reproduction Steps
```python
from validator import validate_age
res = validate_age(25)
assert res is True
```
