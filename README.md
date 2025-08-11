# money_bot
Очень класный бот
# Возможности
- Получение курсов валют через API (USD/RUB, USD/KZT и расчёт RUB/KZT)
- Автоматическое обновление раз в час (можно настроить через `asyncio`)
- Сохранение истории курсов в PostgreSQL
- Уведомления при значительном изменении курса

## Технологии
- Aiogram 3.21.0
- Python 3.12
- SQLAlchemy
- Asyncio
- Requests / httpx (для запросов к API)

## Установка
```bash
git clone https://github.com/Mllleed/money_bot.git
cd money_bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
