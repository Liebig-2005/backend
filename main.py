from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.chatbot import router as chatbot_router
# If you have scanner routes, keep this import; otherwise remove it
# from routes.scanner import router as scanner_router

app = FastAPI()

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (for dev)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(chatbot_router, prefix="/api/chatbot")
# app.include_router(scanner_router, prefix="/api/scanner")  # Uncomment if scanner exists

@app.get("/")
def home():
    return {"message": "FastAPI backend is running"}