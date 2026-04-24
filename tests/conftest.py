import os

# Тестам не нужны реальные токены — задаём пустышки, чтобы pydantic Settings
# не падал при импорте src.config (он не читается тестами calculator/normalize).
os.environ.setdefault("TBANK_TOKEN", "test")
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("TELEGRAM_USER_ID", "1")
