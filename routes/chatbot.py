from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
import re
import google.generativeai as genai

router = APIRouter()

# 1) Put your real API key here
API_KEY = "AIzaSyCxl-9xWKsxg0kiMpjIlfLG83RojJkxU9E"
genai.configure(api_key=API_KEY)

# 2) Request/Response models
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

# 3) In-memory chat history
chat_history_db: Dict[str, List[Dict[str, str]]] = {}

# 4) Simple cleaner (plain text only)
def clean_markdown(text: str) -> str:
    if not text:
        return ""
    text = text.replace('*', '')
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

# 5) Gemini call with correct history format
async def call_gemini(message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
    try:
        # Use a supported model
        model = genai.GenerativeModel("gemini-2.5-flash")

        system_instruction = (
            "You are an expert agricultural assistant.\n"
            "- Provide clear, practical, actionable advice.\n"
            "- Use simple language farmers can understand.\n"
            "- Respond in plain text without markdown formatting."
        )

        # Convert our chat history to Gemini's expected format
        history = []
        if chat_history:
            for msg in chat_history:
                role = "user" if msg.get("role") == "user" else "model"
                content = msg.get("message", "")
                if content:
                    history.append({"role": role, "parts": [content]})

        # If we have history, start a chat; else use a prompt
        if history:
            chat = model.start_chat(history=history)
            response = chat.send_message(message)
        else:
            prompt = f"{system_instruction}\n\nUser: {message}\nAssistant:"
            response = model.generate_content(prompt)

        # Extract text
        reply_text = getattr(response, "text", None)
        if not reply_text and hasattr(response, "candidates") and response.candidates:
            # Fallback extraction
            reply_text = response.candidates[0].content.parts[0].text

        cleaned = clean_markdown(reply_text or "")
        return cleaned if cleaned else "I couldn't generate a response. Please try again."
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}")

# 6) Main endpoint used by React
@router.post("/", response_model=ChatResponse)
async def chatbot_root(req: ChatRequest):
    user_message = req.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = "default-session"
    chat_history = chat_history_db.get(session_id, [])

    # Get reply
    bot_reply = await call_gemini(user_message, chat_history)

    # Save history
    chat_history_db.setdefault(session_id, [])
    chat_history_db[session_id].append({"role": "user", "message": user_message})
    chat_history_db[session_id].append({"role": "assistant", "message": bot_reply})

    # Keep only last 20 messages
    if len(chat_history_db[session_id]) > 20:
        chat_history_db[session_id] = chat_history_db[session_id][-20:]

    return {"response": bot_reply}