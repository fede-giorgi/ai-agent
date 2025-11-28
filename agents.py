#%%
import getpass
import os

from dotenv import load_dotenv

load_dotenv()

api_key_1 = os.getenv("GOOGLE_API_KEY")
api_key_2 = os.getenv("FINDAT_API_KEY")

print(api_key_1, api_key_2)

#%%
if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("AIzaSyAe--aShl7UNp7BCjCp6s7Chyjm_bhFbY4")

#%%
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # other params...
)

messages = [
    (
        "system",
        "You are a helpful assistant that translates English to French. Translate the user sentence.",
    ),
    ("human", "I love programming."),
]
ai_msg = llm.invoke(messages)
ai_msg
# %%
