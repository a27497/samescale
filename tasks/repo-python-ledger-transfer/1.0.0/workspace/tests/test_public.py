from pathlib import Path
from tempfile import TemporaryDirectory

from ledger import LedgerRepository, LedgerService

with TemporaryDirectory() as temporary:
    repository = LedgerRepository(Path(temporary) / "ledger.db")
    repository.create_account("from", 100)
    repository.create_account("to", 20)
    result = LedgerService(repository).transfer("request-1", "from", "to", 25)
    assert result.amount == 25
    assert repository.balance("from") == 75
    assert repository.balance("to") == 45
    repository.close()
