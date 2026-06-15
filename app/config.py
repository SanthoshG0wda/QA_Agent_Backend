import os


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/call_qa")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
GROQ_MODEL = "llama-3.3-70b-versatile"
NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
ENABLE_NIM = os.getenv("ENABLE_NIM", "true").lower() == "true"
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
