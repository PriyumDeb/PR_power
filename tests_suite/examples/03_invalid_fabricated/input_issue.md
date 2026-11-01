### Critical Buffer Overflow in `auth_service.quantum_decrypt_kernel`

The internal function `quantum_decrypt_kernel` causes an unhandled memory fault when passed large payload buffers.
