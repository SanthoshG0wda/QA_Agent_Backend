import os


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/call_qa")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
GROQ_MODEL = "llama-3.3-70b-versatile"
NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Performance flags
FAST_MODE = os.getenv("FAST_MODE", "true").lower() == "true"
GPU_ACCELERATION = os.getenv("GPU_ACCELERATION", "true").lower() == "true"
