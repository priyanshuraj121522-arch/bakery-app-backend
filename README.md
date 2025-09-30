# bakery-app-backend
## Setup

Run initial role seeding after migrations:

```bash
python manage.py seed_roles
```

Run daily stock alerts (Railway cron example):

```bash
python manage.py stock_alerts
```
