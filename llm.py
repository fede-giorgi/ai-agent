#%%
import os
import logging
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Silence the warning from langchain_google_genai
logging.getLogger("langchain_google_genai").setLevel(logging.ERROR)

load_dotenv()

def get_llm():
    """Initialize and return the Google Generative AI model."""
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=2,
    )