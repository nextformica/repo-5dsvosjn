# Нейро-SMM для бьюти-мастеров — Telegram-бот (MVP)

Карманный SMM-менеджер для мастеров маникюра, бровистов, колористов и косметологов.
Мастер за 30 секунд настраивает профиль (ниша, tone of voice, услуги), после чего бот в её стиле:

| Кнопка | Что делает |
|---|---|
| 📅 Контент-план | Сетка тем на 7 или 14 дней с форматами (Пост / Reels / Stories / Карусель) |
| ✍️ Написать пост | Черновик текстом или **голосовым** → готовый пост с хуком, абзацами и призывом записаться |
| 🎬 Идеи для Reels | 3 сценария: что снимать, текст на видео, описание, тип аудио |
| 💬 Ответ в Директ | 3 варианта ответа на «дорого» / «у другого дешевле» + совет, что делать дальше |

Любой текст вне сценария считается черновиком поста — мастер может просто написать боту пару слов.

Монетизация: `FREE_GENERATIONS` (по умолчанию 3) бесплатных генераций, затем пейволл с тарифами
**Базовый 990 ₽/мес** и **Безлимит 2490 ₽/мес**. Оплата — через ЮKassa (СБП/карты), Robokassa или Platega (СБП QR),
переключается командой `/pay`; без ключей работает режим `manual` (мастер пишет `PAYMENT_CONTACT`, админ включает `/grant`).

## Быстрый старт

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить BOT_TOKEN, ключи LLM, ADMIN_IDS
python -m bot.main
```

Или в Docker:

```bash
cp .env.example .env
docker compose up -d --build
```

### Переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | токен от [@BotFather](https://t.me/BotFather) |
| `LLM_PROVIDER` | провайдер по умолчанию: `openai` / `gemini` / `deepseek` / `openrouter` / `ollama` / `lmstudio` / `custom` |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` | ключи провайдеров — можно задать несколько и переключаться |
| `OLLAMA_BASE_URL`, `LMSTUDIO_BASE_URL` | адреса локальных серверов (ключ не нужен) |
| `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` | общий ключ-фолбэк, переопределение модели, произвольный OpenAI-совместимый endpoint (`custom`) |
| `FREE_GENERATIONS` | размер триала |
| `ADMIN_IDS` | Telegram user_id админов через запятую (узнать: [@userinfobot](https://t.me/userinfobot)) |
| `PAYMENT_PROVIDER` | активный способ оплаты: `manual` / `yookassa` / `robokassa` / `platega` |
| `PAYMENT_CONTACT`, `SUBSCRIPTION_DAYS` | контакт для режима `manual`; на сколько дней включать подписку |
| `YOOKASSA_*`, `ROBOKASSA_*`, `PLATEGA_*` | ключи платёжек — см. раздел «Оплата» |
| `WEBHOOK_PORT`, `WEBHOOK_HOST` | HTTP-сервер для вебхуков платёжек (`0` — выключен) |
| `DB_PATH` | путь к SQLite (по умолчанию `data/bot.db`) |

### Провайдеры LLM и переключение

Все провайдеры ходят через один OpenAI-совместимый клиент (пресеты — в `bot/providers.py`):

| Провайдер | Модель по умолчанию | Зачем |
|---|---|---|
| `ollama` | `llama3.1` | разработка бесплатно локально: `ollama pull llama3.1` |
| `lmstudio` | модель, загруженная в LM Studio | то же, через GUI (Developer → Start Server) |
| `deepseek` | `deepseek-chat` | дёшево и хорошо по-русски, для тестов спроса |
| `openrouter` | `openai/gpt-4o-mini` | любые модели одним ключом, работает из РФ |
| `gemini` | `gemini-2.0-flash` | Google, большой бесплатный лимит |
| `openai` | `gpt-4o-mini` | прод + единственный, кто распознаёт голосовые (`whisper-1`) |

Админ переключает провайдера прямо в Telegram, без рестарта:

```
/llm                      — что активно, у кого есть ключ
/llm deepseek             — переключиться на DeepSeek с моделью по умолчанию
/llm ollama qwen2.5:7b    — локальная модель с явным именем
/llm openai gpt-4o        — продакшен
```

Выбор сохраняется в SQLite и переживает рестарт. Типичный путь: разработка на Ollama/DeepSeek → купили подписку →
добавили `OPENAI_API_KEY` в `.env` → `/llm openai`.

Голосовые сообщения расшифровывает `whisper-1`: если активен не OpenAI, но `OPENAI_API_KEY` задан — бот использует его
только для распознавания; иначе попросит написать текстом.

### Оплата: ЮKassa / Robokassa / Platega с СБП

Все платёжки реализованы за одним интерфейсом `PaymentProvider` (`bot/payments/`). Сценарий для мастера одинаков:
тариф → кнопка «💳 Оплатить» (ссылка на страницу платёжки с QR СБП / картой) → «✅ Я оплатила» → бот спрашивает статус у платёжки
и включает подписку на `SUBSCRIPTION_DAYS`. Платежи пишутся в таблицу `payments`, повторная активация невозможна.

| Способ | Что нужно в `.env` | СБП | Проверка статуса | Вебхук |
|---|---|---|---|---|
| `manual` | `PAYMENT_CONTACT` | — | админ `/grant` | — |
| `yookassa` | `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` | да (`YOOKASSA_SBP_ONLY=true` — сразу QR) | `GET /v3/payments/{id}` | `POST /webhook/yookassa` (статус перепроверяется по API) |
| `robokassa` | `ROBOKASSA_LOGIN`, `ROBOKASSA_PASSWORD1`, `ROBOKASSA_PASSWORD2` (+`ROBOKASSA_TEST`, `ROBOKASSA_HASH`) | да (`ROBOKASSA_INC_CURR_LABEL=SBPPSR`) | `OpStateExt` | `POST /webhook/robokassa` = ResultURL, подпись Пароль№2 |
| `platega` | `PLATEGA_MERCHANT_ID`, `PLATEGA_SECRET` (+`PLATEGA_PAYMENT_METHOD`, 2 = СБП) | да | `GET /transaction/{id}` | `POST /webhook/platega`, проверка `X-MerchantId`/`X-Secret` |

Вебхуки необязательны: кнопка «Я оплатила» работает без публичного домена. Чтобы подписка включалась сама,
задайте `WEBHOOK_PORT=8080`, выведите порт на https-домен и укажите `https://<домен>/webhook/<provider>` в личном кабинете
платёжки (ЮKassa → HTTP-уведомления `payment.succeeded`; Robokassa → ResultURL, метод POST; Platega → Callback URLs).

Переключение без рестарта (выбор сохраняется в SQLite):

```
/pay              — что активно, у кого заполнены ключи
/pay yookassa     — переключиться на ЮKassa
/pay platega      — на Platega
/pay manual       — вернуть ручной режим
```

### Команды

Пользователь: `/start`, `/profile`, `/setup` (перенастроить профиль), `/tariff`.

Админ (только `ADMIN_IDS`):
- `/grant <user_id> [days=30]` — включить премиум вручную (ID мастер видит при нажатии на тариф);
- `/llm [provider] [model]` — посмотреть / переключить LLM-провайдера;
- `/pay [provider]` — посмотреть / переключить способ оплаты;
- `/stats` — пользователи / прошли онбординг / генераций / премиум / оплаты и выручка.

## Где что лежит

```
bot/
  main.py          точка входа, polling
  config.py        настройки из .env
  db.py            SQLite: users, generations (лог всех запросов), payments, settings
  providers.py     пресеты OpenAI / Gemini / DeepSeek / OpenRouter / Ollama / LM Studio
  llm.py           OpenAI-совместимый клиент, MockLLM, LLMRouter (переключение на лету)
  payments/        PaymentProvider: manual, yookassa, robokassa, platega; PaymentRouter (/pay); service — активация
  webhook.py       aiohttp-сервер POST /webhook/<provider> (включается WEBHOOK_PORT)
  prompts.py       ВСЕ системные промпты — править здесь, код трогать не нужно
  keyboards.py     кнопки меню и inline-клавиатуры
  handlers/
    onboarding.py  /start, анкета: ниша → tone of voice → услуги
    generate.py    4 генератора, лимит, «Ещё вариант», голосовые
    subscription.py тарифы, пейволл, создание счёта и кнопка «Я оплатила»
    admin.py       /grant, /llm, /pay, /stats
tests/             сквозные тесты через фейковый Bot (без сети): pytest
```

## Проверка

```bash
ruff check bot tests && ruff format --check bot tests
mypy bot
pytest
```

## Что дальше (после проверки спроса)

- Счётчик 50 генераций в месяц для «Базового» (сейчас оба тарифа дают безлимит на срок подписки); автопродление; чеки 54-ФЗ.
- Telegram Payments (счёт прямо в чате) — как ещё один `PaymentProvider`.
- Redis вместо `MemoryStorage` для FSM, если бот будет перезапускаться под нагрузкой.
- VIP-функции из тарифа «Безлимит»: генерация картинок для сторис, анализ конкурентов.
- Telegram Mini App поверх тех же промптов, когда потребуется более богатый интерфейс.
