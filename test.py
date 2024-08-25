from g4f.client import Client

from src.prompt_manager import PromptManager

client = Client()
prompt_manager = PromptManager()


def get_response(messages: list[dict[str, str]]):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,  # type: ignore
    )
    return response.choices[0].message  # type: ignore


messages: list[dict[str, str]] = [{"role": "user", "content": prompt_manager.video_idea}]  # type: ignore
response = get_response(messages)
video_idea = response.content
messages.append(response)  # type: ignore

messages.append({"role": "user", "content": prompt_manager.picture_generation})  # type: ignore
response = get_response(messages)
picture_generation = response.content
messages.append(response)  # type: ignore
