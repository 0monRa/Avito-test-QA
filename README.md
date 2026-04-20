# Avito QA Trainee Assignment (Spring 2026)

В репозитории выполнены:
- Задание 1: анализ багов на скриншоте (см. `BUGS.md`, раздел "Баги на скриншоте")
- Задание 2.1: API тестирование сервиса объявлений

## Стек

- Python 3.11+
- pytest
- requests
- jsonschema (контрактные проверки)
- allure-pytest (опционально, для отчётов)

## Структура

- `TESTCASES.md` - полный список тест-кейсов (включая contract/matrix/v2)
- `test_api.py` - автоматизированные API тесты (40 тестов)
- `BUGS.md` - баг-репорты
- `requirements.txt` - зависимости
- `pytest.ini` - маркеры и настройки запуска

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Запуск тестов

Базовый запуск:

```bash
pytest -v
```

Запуск отдельных наборов по маркерам:

```bash
pytest -v -m contract
pytest -v -m matrix
pytest -v -m v2
```

Запуск с Allure-результатами:

```bash
pytest -v --alluredir=allure-results
```

Генерация и открытие отчёта:

```bash
allure serve allure-results
```

## Примечания по стабильности

- Каждый тест создаёт собственные данные (уникальные `sellerID`, `name`) и не зависит от фиксированного состояния стенда.
- Тесты не опираются на фиксированное число объявлений в выдаче.
- Для нестабильной сети добавлены повторные попытки запросов (`ConnectionError`/`ReadTimeout`).