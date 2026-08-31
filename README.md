# Telegram Verification Bot

Верификационный бот для Telegram-групп: новый участник не может писать в чате, пока не заполнит анкету в ЛС. На заполнение — 48 часов, иначе исключение из группы.

## Стек

- Python 3.11+
- [aiogram](https://docs.aiogram.dev/) 3
- SQLite (`data/bot.sqlite3`)
- APScheduler, PyYAML, python-dotenv

## Возможности

- Mute новых участников до заполнения анкеты
- Анкета в ЛС (кнопки + текст), прогресс, пропуск необязательных полей
- Тихий unmute после заполнения
- Кик через 48 часов (`ban` + `unban`)
- Повторный вход с готовой анкетой — доступ сразу
- `/info` — карточка участника
- Админ-алерты в ЛС (одно сообщение, обновляется по мере ответов)
- Обход блокировки `api.telegram.org` через Cloudflare Worker или прокси

## Требования к боту в группе

Администратор с правом **Restrict members** (ограничивать участников).

В @BotFather для учёта сообщений (если нужно): `/setprivacy` → **Disable**.

## Быстрый старт

```bash
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd YOUR_REPO

python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
```

Заполни `.env`:

```env
BOT_TOKEN=токен_от_BotFather
SUPER_ADMIN_ID=твой_telegram_user_id
```

Запуск:

```bash
python main.py
```

## Переменные окружения

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `BOT_TOKEN` | да | Токен бота от @BotFather |
| `SUPER_ADMIN_ID` | да | Telegram user_id супер-админа |
| `TELEGRAM_API_BASE` | нет | URL Cloudflare Worker вместо `api.telegram.org` |
| `PROXY_URL` | нет | SOCKS5/HTTP прокси, например `socks5://127.0.0.1:9150` |

## Если `api.telegram.org` заблокирован

1. Разверни Worker из [`cloudflare_worker.js`](cloudflare_worker.js) на [Cloudflare Workers](https://workers.cloudflare.com).
2. В `.env` укажи `TELEGRAM_API_BASE=https://твой-воркер.workers.dev` (без слэша в конце).

## Конфигурация анкеты

Вопросы, тексты, таймеры — в [`config.yaml`](config.yaml). Меняются без правки кода.

## Команды

### Для всех

| Команда | Где | Описание |
|---------|-----|----------|
| `/start` | ЛС | Начать / продолжить анкету |
| `/edit_anketa` | ЛС | Изменить свои ответы |
| `/info` | Группа / ЛС | Карточка (своя, реплай, `@user`, `user_id`) |

### Админы (только ЛС бота)

| Команда | Описание |
|---------|----------|
| `/admin_info @user` | Служебная информация |
| `/reset_anketa @user` | Сброс анкеты + mute |
| `/force_kick @user` | Кик из известных групп |
| `/stats` | Статистика |

### Супер-админ

| Команда | Описание |
|---------|----------|
| `/make_admin @user` | Добавить в whitelist |
| `/remove_admin @user` | Убрать из whitelist |

## Структура проекта

```
tgbot/
├── main.py              # точка входа
├── settings.py          # .env + config.yaml
├── config.yaml          # анкета и тексты
├── db.py                # SQLite
├── handlers/
│   ├── chat.py          # группа, /info, join
│   ├── dm.py            # ЛС, анкета
│   └── admin.py         # админ-команды
├── services/
│   ├── telegram_chat.py # mute / unmute / kick
│   └── notify.py        # алерты админам
├── cloudflare_worker.js # прокси для Bot API
├── data/                # БД (не в git)
└── requirements.txt
```

## Публикация на GitHub

**Не коммить `.env`** — там токен бота. Файл уже в `.gitignore`.

```bash
cd tgbot
git init
git add .
git status   # убедись, что .env и data/*.sqlite3 НЕ в списке
git commit -m "Initial commit: Telegram verification bot"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

Если токен когда-либо попал в git — сразу отзови его в @BotFather (`/revoke`) и создай новый.

## Лицензия

Приватный проект. Укажи лицензию при необходимости.
