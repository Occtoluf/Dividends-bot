# Dividends Bot

Личный Telegram-бот для учёта дивидендов по акциям из портфеля T-Bank
(брокерский счёт + ИИС). Читает портфель через T-Invest API (read-only),
считает, сколько дивидендов вы получили по каждой покупке, и выводит
отчёт в Telegram.

## Что умеет (MVP)

- Команда `/dividends <тикер или название>` — показывает:
  1. Суммарный полученный дивидендный доход и его процент от суммы
     покупок.
  2. Сумму с добавленным будущим подтверждённым дивидендом.
  3. Список покупок этого актива от новой к старой, у каждой покупки —
     сколько дивидендов получено, пока вы её держите.
- Поиск: точное совпадение тикера, запомненные вами алиасы, fuzzy-поиск
  по всему биржевому справочнику (рус/англ/транслит). Если точного
  совпадения нет — бот присылает inline-кнопки с ближайшими вариантами;
  выбор запоминается, повторно спрашивать не будет.
- Данные собираются сразу по всем вашим счетам (БС и ИИС), результаты
  суммируются — без указания, что где.
- Доступ к боту ограничен одним Telegram user_id из `.env`.

## Подготовка

### 1. Токен T-Invest (read-only)
1. Откройте https://www.tbank.ru/invest/settings/api/
2. Создайте новый токен с правами «только чтение».
3. Скопируйте токен — он будет показан один раз.

### 2. Telegram-бот
1. В Telegram напишите `@BotFather` → `/newbot`, придумайте имя.
2. Скопируйте токен вида `1234567:AA...`.
3. Узнайте свой numeric user_id через `@userinfobot`.

### 3. Настройки
```bash
cp .env.example .env
# заполните TBANK_TOKEN, TELEGRAM_TOKEN, TELEGRAM_USER_ID
```

## Запуск

### Локально (venv)
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"   # опционально: подтягивает pytest для тестов
python run.py
```

> SDK T-Bank `t-tech-investments` лежит не на публичном PyPI, а в приватном
> индексе Т-Банка. В `requirements.txt` первая строка уже прописывает
> `--extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple`,
> так что обычный `pip install -r requirements.txt` сам его подтянет.
> Если ставите через `pip install -e .`, флаг нужно передать вручную:
> ```bash
> pip install -e ".[dev]" --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple
> ```

### Docker Compose (рекомендуется для VPS)
```bash
docker compose up --build -d
docker compose logs -f
```

В `docker-compose.yml` выставлены лимиты `cpus: "1.0"`, `memory: 256M`
и ротация логов — подходит для слабых VPS (2 CPU).

### Тесты
```bash
pytest
```

## Карта проекта

```
Dividends-bot/
├── run.py                  # Точка входа, вызывает src.bot.main.run()
├── Dockerfile              # Multi-stage билд на python:3.12-slim
├── docker-compose.yml      # Volume data:/app/data, лимиты ресурсов
├── pyproject.toml          # Зависимости и dev-extras для pytest
├── requirements.txt        # То же + --extra-index-url на T-Bank SDK
├── data/                   # (gitignored) SQLite и кэш живут здесь
└── src/
    ├── config.py           # pydantic Settings: токены, whitelist, пути
    ├── bot/                # Слой Telegram (aiogram 3)
    │   ├── main.py             # Dispatcher, middleware, long-polling
    │   ├── middleware_auth.py  # Whitelist по TELEGRAM_USER_ID
    │   ├── formatters.py       # Рендер сообщения отчёта
    │   ├── pending_queries.py  # In-memory мапа для callback_data
    │   ├── report_service.py   # Тонкая склейка tbank+calculator
    │   └── handlers/
    │       ├── dividends.py    # /start, /dividends
    │       └── alias_pick.py   # Обработчик inline-кнопок выбора
    ├── tbank/              # Обёртки поверх T-Bank Invest SDK (пакет t-tech-investments)
    │   ├── client.py           # Фабрика AsyncClient + helpers по Quotation/Money
    │   ├── accounts.py         # list_accounts() — БС + ИИС
    │   ├── instruments.py      # Кэш справочника акций, будущие дивиденды
    │   └── operations.py       # Инкрементный pull через GetOperationsByCursor
    ├── domain/             # Чистая бизнес-логика без IO
    │   ├── models.py           # Purchase, Sale, DividendEvent, AssetReport
    │   └── calculator.py       # FIFO-атрибуция дивидендов по лотам
    ├── search/             # Fuzzy-резолв «тикер или название»
    │   ├── normalize.py        # lower/strip/translit
    │   └── matcher.py          # Exact | Suggestions | NotFound
    └── storage/            # SQLite-уровень
        ├── db.py               # Схема + connect()
        ├── aliases.py          # query_norm -> figi
        ├── cache_instruments.py  # Справочник акций с TTL
        ├── cache_dividends.py    # Кэш расписания дивидендов
        └── cursor_store.py       # Операции + курсор GetOperationsByCursor

tests/
├── test_calculator.py      # FIFO-атрибуция, edge-кейсы
└── test_matcher.py         # Alias / exact / fuzzy / not found
```

### Куда писать новое
- **Новая команда Telegram** → новый файл в `src/bot/handlers/`, подключить
  в `src/bot/handlers/__init__.py`.
- **Новый тип актива (облигации, золото)**:
  - расширьте `src/domain/models.py` (`CouponPayment`, `GoldPurchase` и т.п.);
  - логика расчёта — новый метод в `src/domain/calculator.py` или
    соседний файл рядом (например `calculator_bonds.py`);
  - если нужен новый API-вызов T-Invest — добавляйте в `src/tbank/` с
    изолированным кэшем в `src/storage/`.
- **Новое поле в отчёте** → `src/domain/models.py` + `src/bot/formatters.py`.
- **Новый fuzzy-источник (например прозвища)** → `src/search/normalize.py`
  / `src/search/matcher.py`.

## Безопасность

- `.env` находится в `.gitignore`. Никогда не коммитьте токены.
- Бот не отвечает никому, кроме `TELEGRAM_USER_ID`. Остальные апдейты
  молча отбрасываются middleware.
- Используется **read-only** токен T-Invest — бот не может совершать
  сделки. При компрометации токена его можно отозвать в личном кабинете.

## Известные ограничения MVP

- Валюта: отчёт выводится в валюте инструмента без конвертации в ₽.
  Для БС это может быть USD/HKD/CNY — смотрим как есть.
- Сплиты и конвертация акций отражены в T-Bank отдельными операциями —
  MVP их не пересчитывает. Если столкнётесь — пишите issue с примером.
- Курсы/цены акций в реальном времени не показываются (вне MVP).
- Облигации (с купонами) и золото в плане на следующий этап —
  структура под них уже готова.

## Верификация

1. Заполнить `.env`.
2. `docker compose up --build -d` (или `python run.py` локально).
3. `/start` — получить приветствие. От чужого user_id — тишина.
4. `/dividends PLZL` — сверить `Получено:` с разделом «Доход» в T-Bank.
5. `/dividends полюс` / `Polyus` / `plzl` — всё резолвится без кнопок.
6. `/dividends палюс` — приходят кнопки, после выбора ответ запоминается.
7. Перезапуск контейнера — alias’ы и кэш справочника сохранились (том `./data`).
