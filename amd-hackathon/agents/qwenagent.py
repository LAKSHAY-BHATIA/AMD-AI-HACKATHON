from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework import Agent, tool  # FIX: Import the tool decorator
from typing import Annotated
from pydantic import Field
import asyncio



# FIX: Add the @tool decorator so the agent detects its JSON schema
# FIX: Explicitly pass name and description keys inside the decorator 
# This forces the DevUI discovery system to find and map the tool canvas
@tool(
    name="get_weather", 
    description="Retrieves weather information for any location"
)
def get_weather(
    location: Annotated[str, Field(description="The city and state, e.g. San Francisco, CA")]
) -> str:
    """Get weather for a location."""
    return f"Weather in {location}: 72F and sunny"



agent = Agent(
    name="QwenAgent",
    instructions="""
You are a helpful AI assistant.
You help with coding, AI, manufacturing analytics,
telemetry analysis and defect detection.
""",
    client=OpenAIChatCompletionClient(
        model="Qwen/Qwen2.5-VL-7B-Instruct",
        api_key="EMPTY",
        base_url="http://localhost:8000/v1",
    ),
    tools=[get_weather]
   
    
)


# Launch DevUI
#serve(entities=[agent], auto_open=True)
# Opens browser to http://localhost:8080