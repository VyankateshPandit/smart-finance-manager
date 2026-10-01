import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("GEMINI_API") or os.getenv("GEMINI_API_KEY")

if not key:
    print("Error: GEMINI_API key is not set in .env")
    exit(1)

print(f"Querying ModelService with API Key (length: {len(key)})...\n")

# 1. Query using new google-genai SDK
try:
    from google import genai
    client = genai.Client(api_key=key)
    print("================================================================")
    print("           AVAILABLE MODELS & SUPPORTED METHODS (Google GenAI)  ")
    print("================================================================\n")
    
    for m in client.models.list():
        name = getattr(m, "name", str(m))
        display_name = getattr(m, "display_name", "")
        methods = (
            getattr(m, "supported_generation_methods", None)
            or getattr(m, "supported_actions", None)
            or []
        )
        print(f"Model ID     : {name}")
        if display_name:
            print(f"Display Name : {display_name}")
        if methods:
            print(f"Methods      : {', '.join(methods)}")
        print("-" * 64)

except Exception as e:
    print(f"google-genai client.models.list() notice: {e}\n")
    # 2. Fallback to legacy SDK
    try:
        import google.generativeai as legacy_genai
        legacy_genai.configure(api_key=key)
        print("================================================================")
        print("           AVAILABLE MODELS (Legacy Google GenerativeAI)        ")
        print("================================================================\n")
        
        for m in legacy_genai.list_models():
            print(f"Model ID     : {m.name}")
            print(f"Display Name : {m.display_name}")
            print(f"Methods      : {', '.join(m.supported_generation_methods)}")
            print("-" * 64)
    except Exception as ex:
        print(f"Failed to fetch models: {ex}")
