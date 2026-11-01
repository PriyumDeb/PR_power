### Bug Report: ZeroDivisionError in `calculator.divide`

When calling `calculator.divide(100, 0)`, the function crashes with an unhandled `ZeroDivisionError`.

#### Reproduction Steps
```python
from calculator import divide
divide(100, 0)
```
