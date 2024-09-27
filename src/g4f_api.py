import atexit
import os
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning)

from enum import Enum

import g4f.debug
import g4f.Provider as Provider
from g4f.client import Client
from g4f.cookies import read_cookie_files, set_cookies_dir
from g4f.errors import MissingAuthError, RateLimitError
from g4f.requests.raise_for_status import CloudflareError

from config.config import SessionID, SettingsManager, Singleton


class MessageSender(Enum):
    USER = 0
    ASSISTANT = 1


class Message:
    def __init__(self, sender: MessageSender, content: str) -> None:
        self.__sender__ = sender
        self.__content__ = content

    @property
    def sender(self) -> MessageSender:
        return self.__sender__

    @property
    def content(self) -> str:
        return self.__content__

    def to_dict(self) -> dict[str, str]:
        return {"role": self.__sender__.name.lower(), "content": self.__content__}

    @classmethod
    def from_dict(cls, message: dict[str, str]) -> "Message":
        return cls(
            MessageSender[message["role"].upper()],
            message["content"],
        )

    def __dict__(self) -> dict[str, str]:
        return self.to_dict()


@Singleton
class G4FAPI:
    def __init__(
        self,
        model: str = "gpt-4o",
        backup_model: str = "gpt-4o-mini",
        provider: Provider.ProviderType | None = Provider.OpenaiChat,
        verbose: bool = False,
    ) -> None:
        g4f.debug.logging = verbose
        self.__verbose__ = verbose
        self.__settings_manager__ = SettingsManager(session_id=SessionID.NONE)
        cookies_dir = os.path.join(
            self.__settings_manager__.root_dir, "config", "har_and_cookies"
        )
        os.makedirs(cookies_dir, exist_ok=True)
        self.__decrypt_cookies__(cookies_dir)
        set_cookies_dir(cookies_dir)
        read_cookie_files(cookies_dir)
        atexit.register(self.__encrypt_cookies__, cookies_dir)

        self.__provider__ = provider
        self.__client__ = Client(provider=self.__provider__)  # type: ignore
        self.__model__ = model
        self.__backup_model__ = backup_model
        self.__using_backup_model__ = False
        self.__messages__: list[dict[str, str]] = []

    def __decrypt_cookies__(self, cookies_dir: str) -> None:
        for file in os.listdir(cookies_dir):
            if file.endswith(".har"):
                with open(os.path.join(cookies_dir, file), "r", encoding="utf-8") as f:
                    content = f.read()
                if not content.startswith("encrypted:"):
                    continue
                content = self.__settings_manager__.decrypt(content[10:])
                with open(os.path.join(cookies_dir, file), "w", encoding="utf-8") as f:
                    f.write(content)

    def __encrypt_cookies__(self, cookies_dir: str) -> None:
        for file in os.listdir(cookies_dir):
            if file.endswith(".har"):
                with open(os.path.join(cookies_dir, file), "r", encoding="utf-8") as f:
                    content = f.read()
                if content.startswith("encrypted:"):
                    continue
                content = self.__settings_manager__.encrypt(content)
                with open(os.path.join(cookies_dir, file), "w", encoding="utf-8") as f:
                    f.write(f"encrypted:{content}")

    @property
    def verbose(self) -> bool:
        return self.__verbose__

    @verbose.setter
    def verbose(self, verbose: bool) -> None:
        self.__verbose__ = verbose
        g4f.debug.logging = verbose

    @property
    def model(self) -> str:
        return self.__model__

    @model.setter
    def model(self, model: str) -> None:
        self.__model__ = model

    @property
    def backup_model(self) -> str:
        return self.__backup_model__

    @backup_model.setter
    def backup_model(self, backup_model: str) -> None:
        self.__backup_model__ = backup_model

    @property
    def using_backup_model(self) -> bool:
        return self.__using_backup_model__

    @using_backup_model.setter
    def using_backup_model(self, using_backup_model: bool) -> None:
        self.__using_backup_model__ = using_backup_model

    @property
    def provider(self) -> Provider.ProviderType | None:
        return self.__provider__

    @provider.setter
    def provider(self, provider: Provider.ProviderType | None) -> None:
        self.__provider__ = provider

    @property
    def messages(self, as_dict: bool = False) -> list[Message] | list[dict[str, str]]:
        return (
            self.__messages__
            if as_dict
            else [Message.from_dict(message) for message in self.__messages__]
        )
    
    def add_message(self, message: Message) -> None:
        self.__messages__.append(message.to_dict())

    def clear_messages(self) -> None:
        self.__messages__ = []

    def get_response(self, message: Message, as_str: bool = False, retries: int = 0, save_response: str | None = None) -> Message | str:
        if not message.sender == MessageSender.USER:
            raise ValueError("The first message must be from the user")

        model = (
            self.__model__ if not self.__using_backup_model__ else self.__backup_model__
        )

        self.__messages__.append(message.to_dict())
        try:
            if self.__verbose__:
                print(
                    f"Sending message (Model: {model} | Provider: {"Auto" if not self.__provider__ else self.__provider__.__name__})..."
                )
            response = (
                self.__client__.chat.completions.create(
                    model=model,
                    messages=self.__messages__,  # type: ignore
                    provider=self.__provider__, # type: ignore
                )
                .choices[0]  # type: ignore
                .message.content
            )
        except MissingAuthError as e:
            if retries > 3:
                raise e

            self.__messages__.pop()
            if self.__verbose__:
                print(f"Missing authentication for provider {self.__provider__.__name__}. Retrying with automatic provider...") # type: ignore
            self.__provider__ = None
            return self.get_response(message, as_str, retries + 1)
        except RateLimitError as e:
            if retries > 3:
                raise e

            self.__messages__.pop()
            if self.__using_backup_model__:
                self.__using_backup_model__ = False
                raise e
            if self.__verbose__:
                print(
                    f"Rate limit for model {model} reached. Retrying with backup model {self.__backup_model__}..."
                )
            self.__using_backup_model__ = True
            return self.get_response(message, as_str, retries + 1)
        except CloudflareError as e:
            if retries > 3:
                raise e

            self.__messages__.pop()
            if self.__verbose__:
                if self.__provider__:
                    print(
                        f"Cloudflare detected when using provider {self.__provider__.__name__}. Retrying with automatic provider..." # type: ignore
                    )
                else:
                    print(
                        "Cloudflare detected. Retrying with automatic provider..."
                    )
            self.__provider__ = None
            return self.get_response(message, as_str, retries + 1)
        except Exception as e:
            self.__messages__.pop()
            raise e

        self.__messages__.append(Message(MessageSender.ASSISTANT, response).to_dict())  # type: ignore
        if save_response and isinstance(response, str):
            if not save_response.endswith(".txt"):
                save_response += ".txt"
            os.makedirs(os.path.join(
                self.__settings_manager__.build_dir, "responses"
            ), exist_ok=True)
            with open(os.path.join(
                self.__settings_manager__.build_dir, "responses", save_response
            ), "w", encoding="utf-8") as f:
                f.write(response)
        if self.__verbose__:
            print("Received response from provider.")
        return response if as_str else Message(MessageSender.ASSISTANT, response)  # type: ignore
