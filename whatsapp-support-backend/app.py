import os
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from twilio.rest import Client as TwilioClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/whatsapp_support")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")

app = FastAPI(title="WhatsApp Support (Python)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- DB ----
client = AsyncIOMotorClient(MONGO_URI) if "mongodb" in MONGO_URI else AsyncIOMotorClient("mongodb://localhost:27017")
db = client.get_default_database() if client else None
if db is None:
    # fallback to default db name if URI didn't include one
    db = client["whatsapp_support"]

# ---- Twilio ----
twilio = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ---- Models ----
Direction = Literal["inbound", "outbound"]

class ConversationOut(BaseModel):
    id: str = Field(alias="_id")
    participant: str
    status: Literal["open","closed"]
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

class MessageOut(BaseModel):
    id: str = Field(alias="_id")
    conversationId: str
    direction: Direction
    from_: str = Field(alias="from")
    to: str
    body: Optional[str] = None
    mediaUrl: Optional[str] = None
    createdAt: Optional[str] = None

class SendMessageIn(BaseModel):
    to: str
    body: Optional[str] = None
    mediaUrl: Optional[str] = None

# ---- Helpers ----
def oid_str(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc

async def ensure_conversation(participant: str):
    conv = await db.conversations.find_one({"participant": participant})
    if not conv:
        res = await db.conversations.insert_one({"participant": participant, "status": "open"})
        conv = await db.conversations.find_one({"_id": res.inserted_id})
    return conv

async def record_message(conversation_id: str, direction: Direction, from_: str, to: str, body: Optional[str], mediaUrl: Optional[str]):
    doc = {
        "conversationId": conversation_id,
        "direction": direction,
        "from": from_,
        "to": to,
        "body": body,
        "mediaUrl": mediaUrl,
    }
    res = await db.messages.insert_one(doc)
    return await db.messages.find_one({"_id": res.inserted_id})

# ---- Routes ----
@app.get("/conversations", response_model=List[ConversationOut])
async def list_conversations():
    cursor = db.conversations.find().sort("updatedAt", -1)
    results = []
    async for c in cursor:
        results.append(oid_str(c))
    return results

@app.get("/conversations/{conv_id}/messages", response_model=List[MessageOut])
async def conversation_messages(conv_id: str):
    cursor = db.messages.find({"conversationId": conv_id}).sort("_id", 1)
    results = []
    async for m in cursor:
        m = oid_str(m)
        m["from_"] = m.pop("from")
        results.append(m)
    return results

@app.post("/messages/send")
async def send_message(payload: SendMessageIn):
    from_ = TWILIO_WHATSAPP_FROM
    # Send via Twilio
    msg = twilio.messages.create(
        from_=from_,
        to=payload.to,
        body=payload.body,
        media_url=[payload.mediaUrl] if payload.mediaUrl else None,
    )
    # Persist outbound
    conv = await ensure_conversation(payload.to)
    doc = await record_message(str(conv["_id"]), "outbound", from_, payload.to, payload.body, payload.mediaUrl)
    return {"ok": True, "sid": msg.sid, "message": oid_str(doc)}

@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request):
    # Twilio sends application/x-www-form-urlencoded
    form = await request.form()
    from_ = str(form.get("From") or "")
    to = str(form.get("To") or "")
    body = str(form.get("Body") or "") or None
    mediaUrl = str(form.get("MediaUrl0") or "") or None

    conv = await ensure_conversation(from_)
    await record_message(str(conv["_id"]), "inbound", from_, to, body, mediaUrl)
    return JSONResponse({"ok": True})
