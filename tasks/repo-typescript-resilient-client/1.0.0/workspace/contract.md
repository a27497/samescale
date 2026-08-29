# Client contract

Configuration is explicit and validated. Transport injection is preserved. Retry limits count
additional attempts, apply only to transport failures and 5xx responses, and never cause network
access during verification.
