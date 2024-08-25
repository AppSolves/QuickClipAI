import os

from config.config import SettingsManager, Singleton


@Singleton
class PromptManager:
    def __init__(self):
        self.reinit()

    def reinit(self):
        self.__initialized__ = False
        topics = SettingsManager().get("past_topics", [])
        for root, _, files in os.walk("prompts"):
            for file in files:
                with open(os.path.join(root, file), "r") as f:
                    prompt_name = os.path.splitext(file)[0]
                    prompt_content = (
                        f.read().format(
                            topics=topics,
                        )
                        if prompt_name == "video_idea"
                        else f.read()
                    )
                    setattr(self, prompt_name, prompt_content)
        self.__initialized__ = True

    def get_prompt(self, prompt_name: str) -> str:
        return getattr(self, prompt_name)

    def __setattr__(self, name, value):
        if hasattr(self, "__initialized__") and self.__initialized__:
            raise AttributeError(
                "'PromptManager' is a singleton and cannot be modified after initialization"
            )

        super().__setattr__(name, value)
