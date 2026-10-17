# Fitness Studio Booking API

A Booking API for a fictional fitness studio, built with **Python + FastAPI**, **SQLAlchemy** and **SQLite**. Users sign up, log in (JWT), browse upcoming classes, create classes, book slots and view their bookings.

## Features

- JWT authentication (access token + refresh token)
- Create / list classes; list returns upcoming classes only
- Booking with overbooking protection (atomic slot decrement) and duplicate-booking prevention
- All class times stored in **IST (Asia/Kolkata)**; responses can be converted via `?tz=<IANA zone>`
- Input validation, request logging, auto-generated Swagger docs, unit tests

## Project Structure

```
app/
  main.py        # app + logging middleware
  database.py    # engine / session
  models.py      # User, FitnessClass, Booking
  schemas.py     # request/response models
  security.py    # password hashing + JWT
  deps.py        # current-user dependency
  timeutils.py   # IST helpers
  routers/       # auth, classes, bookings
tests/test_api.py
seed.py          # sample data
```

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your own `SECRET_KEY`. Optional environment variables: `DATABASE_URL` (default `sqlite:///./fitness.db`), `SECRET_KEY`, `ACCESS_TOKEN_MINUTES` (30), `REFRESH_TOKEN_DAYS` (7).

## Run Locally

```bash
python seed.py                 # optional: demo user + classes
uvicorn app.main:app --reload
```

- Swagger docs: http://127.0.0.1:8000/docs
- Demo login after seeding: `demo@example.com` / `password123`

## Run Tests

```bash
pytest
```

## API Usage

### Sign up

```bash
curl -X POST http://127.0.0.1:8000/signup -H "Content-Type: application/json" \
  -d '{"name":"Alice","email":"alice@example.com","password":"secret123"}'
```

### Log in

```bash
curl -X POST http://127.0.0.1:8000/login -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"secret123"}'
```

Returns `access_token`, `refresh_token`, `expires_in`. Use `Authorization: Bearer <access_token>` below.

### Refresh token

```bash
curl -X POST http://127.0.0.1:8000/refresh -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

### Create a class (auth)

`dateTime` must be in the future. Offsets are converted to IST; a value without an offset is treated as IST.

```bash
curl -X POST http://127.0.0.1:8000/classes -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Yoga Flow","dateTime":"2030-06-15T10:00:00Z","instructor":"John Doe","availableSlots":20}'
```

### List upcoming classes

```bash
curl http://127.0.0.1:8000/classes
curl "http://127.0.0.1:8000/classes?tz=America/New_York"
```

Optional query parameters:

| Param | Meaning |
| ----- | ------- |
| `limit` | Page size, 1-100 (default 20) |
| `offset` | Rows to skip (default 0) |
| `name`, `instructor` | Case-insensitive "contains" filters |
| `from`, `to` | Time range (ISO 8601; no offset = IST) |
| `tz` | Convert response times to an IANA timezone |

The total number of matches is returned in the `X-Total-Count` response header.

```bash
curl -i "http://127.0.0.1:8000/classes?instructor=john&limit=5&offset=0&from=2030-06-01T00:00:00Z"
```

### Book a class (auth)

```bash
curl -X POST http://127.0.0.1:8000/book -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"class_id":1,"client_name":"Alice","client_email":"alice@example.com"}'
```

### View my bookings (auth)

```bash
curl http://127.0.0.1:8000/bookings -H "Authorization: Bearer $TOKEN"
```

## Error Handling

| Status | When |
| ------ | ---- |
| 401 | Missing, invalid or expired token; wrong credentials |
| 404 | Class not found |
| 409 | Email already registered, class full, or class already booked by this user |
| 400 | Unknown timezone, or class already started |
| 422 | Missing / invalid fields, or class date in the past |
| 429 | Rate limit exceeded (see `Retry-After` header) |

## Rate Limiting

Per-IP sliding window: `/signup`, `/login` and `/refresh` allow 10 requests per minute, and everything else 100 per minute. Configure with `RATE_LIMIT_AUTH`, `RATE_LIMIT_GENERAL` and `RATE_LIMIT_WINDOW_SECONDS`. It is in-memory, so it is per process; use Redis for multi-worker deployments.

## Design Notes

- Overbooking is prevented with a single conditional `UPDATE ... WHERE available_slots > 0`, so concurrent requests cannot oversell.
- Passwords are hashed with salted PBKDF2-SHA256.
- `GET /classes` is public (as in the spec's "view upcoming classes"); creating, booking and viewing bookings need a token.
