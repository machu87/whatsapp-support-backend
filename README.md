# WhatsApp Support Backend (Python + FastAPI + MongoDB + Twilio)

API para inbox de WhatsApp con Twilio y persistencia en MongoDB.

## Setup local
```powershell
copy .env.example .env
# editar .env con credenciales/URI
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload --port 3000
```
API: http://localhost:3000

### Docker (local)
```bash
docker compose up --build
```

## Endpoints
- `POST /webhooks/whatsapp` (Twilio → backend; `application/x-www-form-urlencoded`)
- `POST /messages/send` body: `{ "to":"whatsapp:+NNNN", "body":"Hola", "mediaUrl":"https://..."? }`
- `GET /conversations` listar
- `GET /conversations/{id}/messages` mensajes por conversación
