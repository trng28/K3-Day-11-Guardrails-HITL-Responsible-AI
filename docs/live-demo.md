# VinBank live demo — React, FastAPI và Docker

## Kiến trúc

```text
Browser :8080 -> Nginx + React -> /api proxy -> FastAPI :8000
              -> local guardrails -> OpenAI Responses API (gpt-4o-mini)
```

`OPENAI_API_KEY` chỉ được truyền vào backend container, không nằm trong React bundle.

## Chạy Docker Compose

Đảm bảo `.env` có `OPENAI_API_KEY`, sau đó chạy:

```powershell
docker compose up --build
```

Mở <http://localhost:8080>. Health check: <http://localhost:8080/api/health>.

```powershell
docker compose down
```

## Chạy development

Backend:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn web_api:app --app-dir src --reload --port 8000
```

Frontend:

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Mở <http://localhost:5173>; Vite proxy `/api` sang port 8000.

## API

- `GET /api/health`: provider và model.
- `POST /api/chat`: response, guardrail layer, HITL route và metrics.
- `GET /api/metrics`: monitoring snapshot.
- `GET /api/audit/{request_id}`: correlated audit records.

Action rủi ro luôn route `escalate`. Demo không có transfer tool thật nên không
tạo giao dịch ngân hàng.
