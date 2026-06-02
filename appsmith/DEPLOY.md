# Appsmith Deploy

Минимальный self-hosted запуск на текущем DigitalOcean-сервере.

## Что используется

- Docker
- порт `8082`
- volume `appsmith-stacks`

## Файлы

- [`docker-compose.yml`](/Users/Peter/Documents/Morpheus%20Metrics/appsmith/docker-compose.yml)

## Запуск на сервере

```bash
mkdir -p /opt/analytics/appsmith
cd /opt/analytics/appsmith
# положить сюда docker-compose.yml
docker compose up -d
```

## После запуска

Открывать:

- `http://134.122.83.160:8082`

На первом входе Appsmith предложит создать администратора.

## Что подключать в Appsmith

Datasource:

- PostgreSQL
- Host: `134.122.83.160`
- Port: `5432`
- DB: `analytics`
- User: `admin`
- Password: `strongpassword`

Лучше потом перевести datasource на внутренний адрес/сеть, но для быстрого старта этого достаточно.
