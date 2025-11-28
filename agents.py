#%%
import getpass, os, requests
from dotenv import load_dotenv

from langchain.tools import tool
from langchain.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
FINDAT_API_KEY = os.getenv("FINDAT_API_KEY")

#%%
# Initialize the model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
)

# %%

# Define the tool
@tool(description="Get the current weather in a given location")
def get_weather(location: str) -> str:
    return "It's sunny."


# Initialize and bind (potentially multiple) tools to the model
model_with_tools = llm.bind_tools([get_weather])

# Step 1: Model generates tool calls
messages = [
    SystemMessage("You are a helpful assistant that uses tools correctly."),
    HumanMessage("What's the weather in Boston?")
]
ai_msg = model_with_tools.invoke(messages)
messages.append(ai_msg)

# Check the tool calls in the response
print(ai_msg.tool_calls)

# Step 2: Execute tools and collect results
for tool_call in ai_msg.tool_calls:
    # Execute the tool with the generated arguments
    tool_result = get_weather.invoke(tool_call)
    messages.append(tool_result)

# Step 3: Pass results back to model for final response
final_response = model_with_tools.invoke(messages)
# %%
@tool(description="Get financial data for a given ticker symbol")
def get_financials(ticker: str, period: str = 'ttm', limit: int = 30) -> dict:
    
    # add your API key to the headers
    headers = {
        "X-API-KEY": FINDAT_API_KEY
    }

    # create the URL
    url = (
        f'https://api.financialdatasets.ai/financials/'
        f'?ticker={ticker}'
        f'&period={period}'
        f'&limit={limit}'
    )

    # make API request
    response = requests.get(url, headers=headers)

    # if status code is 400, 401, 402 or 404 return error message
    if response.status_code != 200:
        return {"error": f"API error {response.status_code} - {response.text}"}

    # parse data from the response
    data = response.json()
    return data.get('financials', {})
# %%


model_with_tools = llm.bind_tools([get_financials])
# %%
# Step 1: primo giro, il modello decide se chiamare il tool
messages = [
    SystemMessage(
        "Se l'utente chiede come sta performando un'azienda o un titolo, "
        "usa SEMPRE il tool `get_financials` con il ticker corretto "
        "prima di rispondere. Non fare domande di chiarimento se il ticker è chiaro."
    ),
    HumanMessage("Come sta performando TSLA negli ultimi 12 mesi?")
]


ai_msg = model_with_tools.invoke(messages)
messages.append(ai_msg)

print("Tool calls:", ai_msg.tool_calls)

# Step 2: esegui i tool (se ce ne sono)
for tool_call in ai_msg.tool_calls:
    tool_result = get_financials.invoke(tool_call)
    messages.append(tool_result)

# Step 3: risposta finale basata sui dati reali
final_response = model_with_tools.invoke(messages)
print("RISPOSTA FINALE:\n", final_response.content)
# %%
