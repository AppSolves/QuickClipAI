import os

from config.config import SessionID, SettingsManager, Singleton


@Singleton
class PromptManager:
    def __init__(self):
        self.__settings_manager__ = SettingsManager(session_id=SessionID.NONE)
        self.__prompts_dir__ = os.path.join(
            self.__settings_manager__.root_dir,
            "prompts",
        )
        self.reinit()

    def reinit(self):
        self.__initialized__ = False
        topics = self.__settings_manager__.get("past_topics", [])
        for root, _, files in os.walk(self.__prompts_dir__):
            for file in files:
                with open(os.path.join(root, file), "r") as f:
                    prompt_name = os.path.splitext(file)[0]
                    content = f.read()
                    prompt = (
                        content.format(
                            topics=topics,
                        )
                        if r"{topics}" in content
                        else content
                    )
                    setattr(self, prompt_name, prompt)
        self.__initialized__ = True

    def get_prompt(self, prompt_name: str) -> str:
        return getattr(self, prompt_name)

    def __setattr__(self, name, value):
        if hasattr(self, "__initialized__") and self.__initialized__:
            raise AttributeError(
                "'PromptManager' is a singleton and cannot be modified after initialization"
            )

        super().__setattr__(name, value)
