from fastapi import FastAPI, HTTPException, Request, Depends
from sqlalchemy import create_engine, Column, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
import logging
import time
from fastapi.middleware.cors import CORSMiddleware
import httpx
from auth import AuthError, get_current_user
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()
logger.info("latest API codebase from github commit")
logger.info(f"AZURE_OPENAI_ENDPOINT: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
logger.info(f"AZURE_OPENAI_API_KEY: {os.getenv('AZURE_OPENAI_API_KEY')}")
logger.info(
    f"AZURE_OPENAI_DEPLOYMENT_NAME: {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')}"
)
logger.info(f"AZURE_OPENAI_MODEL_NAME: {os.getenv('AZURE_OPENAI_MODEL_NAME')}")

# Disable SSL certificate verification for the HTTP client
http_client = httpx.Client(verify=False)

# Azure OpenAI setup
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version="2024-12-01-preview",
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
    http_client=http_client,
)
model_name = os.getenv("AZURE_OPENAI_MODEL_NAME")
deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
logger.info(f"Azure OpenAI configured with deployment: {deployment_name}")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add root path handler
@app.get("/")
async def root():
    return {"message": "Audrey AI API dummy"}


# Add API routes
@app.post("/api/chat")
async def chat(message: str, current_user: dict = Depends(get_current_user)):
    logger.info(f"Received chat request with message: {message}")
    try:
        # Store message in database
        db = SessionLocal()
        db_message = Message(content=message)
        db.add(db_message)
        db.commit()

        # Get response from Azure OpenAI
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": message},
            ],
        )

        # Store response in database
        db_message.response = response.choices[0].message.content
        db.commit()
        db.close()

        logger.info("Successfully processed chat request")
        return {"response": response.choices[0].message.content}
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/messages")
async def get_messages():
    logger.info("Fetching all messages")
    try:
        db = SessionLocal()
        messages = db.query(Message).all()
        db.close()
        logger.info(f"Retrieved {len(messages)} messages")
        return [
            {"id": msg.id, "content": msg.content, "response": msg.response}
            for msg in messages
        ]
    except Exception as e:
        logger.error(f"Error fetching messages: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
logger.info(f"Using database URL: {DATABASE_URL}")
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    ),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Define database model
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    response = Column(Text)


# Create tables
Base.metadata.create_all(bind=engine)
logger.info("Database tables created successfully")


# Add HTTP logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.2f}s"
    )
    return response


# Add error handler for AuthError
@app.exception_handler(AuthError)
async def auth_error_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.error})


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting FastAPI application")
    uvicorn.run(app, host="0.0.0.0", port=8000)
