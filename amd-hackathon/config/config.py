from agent_framework.openai import OpenAIChatCompletionClient

def create_client():
    
    client = OpenAIChatCompletionClient(
    model="Qwen/Qwen2.5-VL-7B-Instruct",
    api_key="EMPTY",
    base_url="http://localhost:8000/v1")

    return client
