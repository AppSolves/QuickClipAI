import os
import warnings

import typer

from src.errors import APIKeyNotFoundError

warnings.filterwarnings("ignore", category=UserWarning)

from elevenlabs import VoiceSettings, save
from elevenlabs.client import DEFAULT_VOICE, ElevenLabs

from config.config import SessionID, SettingsManager, Singleton


@Singleton
class ElevenLabsAPI:
    def __init__(self, verbose: bool = False) -> None:
        self.__verbose__ = verbose
        self.__settings_manager__ = SettingsManager(session_id=SessionID.NONE)
        api_key = self.__settings_manager__.get(
            "elevenlabs_api_key",
            self.__settings_manager__.get("ELEVENLABS_API_KEY", None),
        )
        if not api_key:
            raise APIKeyNotFoundError("ElevenLabs")
        self.__client__ = ElevenLabs(api_key=api_key)
        del api_key
        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def output_dir(self):
        return os.path.join(self.__settings_manager__.build_dir, "audios")

    @property
    def voices(self):
        return self.__client__.voices.get_all()

    @property
    def models(self):
        return self.__client__.models.get_all()

    @property
    def verbose(self) -> bool:
        return self.__verbose__

    @verbose.setter
    def verbose(self, value: bool):
        self.__verbose__ = value

    def generate_audio(
        self,
        text: str,
        voice_id: str | None = None,
        voice_settings: VoiceSettings | None = None,
        model: str = "eleven_monolingual_v1",
        save_audio: str | None = None,
    ):
        if self.__verbose__:
            typer.echo(f"Generating audio...")
        try:
            response = self.__client__.generate(
                text=text,
                voice=voice_id or DEFAULT_VOICE,
                voice_settings=voice_settings,
                model=model,
            )
        except Exception as e:
            typer.echo(f"Error: {e}")
            return

        if save_audio:
            if not save_audio.endswith(".mp3"):
                save_audio += ".mp3"

            save(response, os.path.join(self.output_dir, save_audio))
            if self.__verbose__:
                typer.echo(f"Audio saved as: {save_audio}")
            return os.path.join(self.output_dir, save_audio)

        return response
