# Task Manager API (FastAPI + SQLAlchemy)

A complete, production-style **Task Manager REST API** built with
**FastAPI** and **SQLAlchemy 2.0**, written with extensive comments as a
learning project.

![Python](https://img.shields.io/badge/Python-3.13-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.136-green) ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-purple)

---

## Features

- 🔐 **JWT authentication** — register, login, protected routes
- 👤 **User accounts** — bcrypt-hashed passwords (never stored in plaintext)
- ✅ **Tasks** — full CRUD with status, priority, due date, search & filters
- 🗂 **Categories** — group your tasks (e.g. "Work", "Personal")
- 📊 **Per-user stats** — task counts by status / priority
- 🔒 **Row-level ownership** — every query is scoped to the logged-in user
- 📄 **Pagination** — filter + page through results
- 🧩 **Clean layout** — `app/` package with routers, core & schemas separated

---

## Project structure

```
sql_FastAPI/
├── app/
│   ├── main.py            # FastAPI app, mounts routers, creates tables
│   ├── database.py        # Engine, SessionLocal, Base, get_db dependency
│   ├── models.py          # SQLAlchemy ORM: User, Task, Category (+ enums)
│   ├── schemas.py         # Pydantic request/response DTOs
│   ├── deps.py            # get_current_user (extracts user from JWT)
│   ├── core/
│   │   ├── config.py      # pydantic-settings, reads .env
│   │   └── security.py    # bcrypt hashing + JWT create/decode
│   └── routers/
│       ├── auth.py        # /auth/register, /auth/login, /auth/me
│       ├── tasks.py       # /tasks CRUD, filters, pagination, stats
│       └── categories.py  # /categories CRUD
├── .env.example           # template for your secrets (copy to .env)
├── requirements.txt
└── README.md
```

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env   # then edit .env with your real database and secret
```

The required variables:

```ini
SECRET_KEY=some-long-random-string
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/taskdb
```

> Generate a good `SECRET_KEY` with:
> `python -c "import secrets; print(secrets.token_urlsafe(48))"`

### 3. Create the database

```sql
CREATE DATABASE taskdb;
```

### 4. Run the server

```bash
uvicorn app.main:app --reload
```

Open the interactive docs: **http://127.0.0.1:8000/docs**

> Tables are created automatically on startup (`Base.metadata.create_all`).
> In production you'd use Alembic migrations instead.

---

## API endpoints

### Auth

| Method | Path                    | Description                   |
| ------ | ----------------------- | ----------------------------- |
| POST   | `/api/v1/auth/register` | Create a new user account     |
| POST   | `/api/v1/auth/login`    | Get a JWT (form: username+password) |
| GET    | `/api/v1/auth/me`       | Current user profile (protected)    |

### Tasks (all protected)

| Method | Path                         | Description                          |
| ------ | ---------------------------- | ------------------------------------ |
| GET    | `/api/v1/tasks`              | List tasks (filters + pagination)    |
| POST   | `/api/v1/tasks`              | Create a task                        |
| GET    | `/api/v1/tasks/{id}`         | Get one task                         |
| PUT    | `/api/v1/tasks/{id}`         | Update a task (partial allowed)      |
| DELETE | `/api/v1/tasks/{id}`         | Delete a task                        |
| GET    | `/api/v1/tasks/stats/overview` | Task dashboard numbers             |

`GET /tasks` supports query params:
`status` (pending/in_progress/completed), `priority` (low/medium/high/urgent),
`category_id`, `search` (in title/description), `due_from`, `due_to`,
`page`, `size`.

### Categories (all protected)

| Method | Path                    | Description          |
| ------ | ----------------------- | -------------------- |
| GET    | `/api/v1/categories`    | List my categories   |
| POST   | `/api/v1/categories`    | Create a category    |
| GET    | `/api/v1/categories/{id}` | Get one category   |
| PUT    | `/api/v1/categories/{id}` | Update a category |
| DELETE | `/api/v1/categories/{id}` | Delete a category |

---

## Trying it out (curl)

```bash
# 1. Register
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email":"a@b.com","username":"lavish","full_name":"Lavish Mehra","password":"supersecret123"}'

# 2. Login -> copy the access_token
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=lavish&password=supersecret123"

# 3. Use the token on protected routes
curl http://127.0.0.1:8000/api/v1/tasks \
     -H "Authorization: Bearer <access_token>"
```

---

## Learning notes

- ❗ **ORM models** (`models.py`) map to database tables;
  **Pydantic schemas** (`schemas.py`) validate JSON. Don't mix them up.
- 🔎 Turn on `DEBUG=True` in `.env` to see **every SQL statement** printed
  in the console while learning SQLAlchemy.
- 🧹 Each request uses a fresh DB session via the `get_db()` dependency,
  which **always** closes it (`finally`) to avoid leaking connections.
- 🔑 Passwords are hashed with **bcrypt**; sessions are stateless **JWTs**
  signed with `SECRET_KEY`.
- ⚠️ `SECRET_KEY` and `DATABASE_URL` live in `.env`, which is git-ignored.
  Never commit real credentials.