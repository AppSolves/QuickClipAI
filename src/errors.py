class _CustomException(Exception):
    def __init__(self, message: str):
        self.__message__ = message
        super().__init__(self.__message__)

    @property
    def message(self):
        return self.__message__


class FooocusNotFoundError(_CustomException):
    def __init__(self):
        super().__init__(
            r"Fooocus path is not specified. Please set the path using the 'SettingsManager' class: https://github.com/AppSolves/QuickClipAI#installation-%EF%B8%8F"
        )


class ModelNotFoundError(_CustomException):
    def __init__(self, model: str):
        super().__init__(
            f"Model '{model}' not found. Please make sure the model is available in the 'models/checkpoints' directory."
        )


class LoRaNotFoundError(_CustomException):
    def __init__(self, lora: str):
        super().__init__(
            f"LoRa '{lora}' not found. Please make sure the LoRa is available in the 'models/loras' directory."
        )


class EncryptionKeyNotFoundError(_CustomException):
    def __init__(self):
        super().__init__("ENCRYPTION_KEY is not set in the environment variables.")


class APIKeyNotFoundError(_CustomException):
    def __init__(self, api_name: str):
        super().__init__(
            f"{api_name} API key not found. Make sure to set the API key in the '.env' file or using the 'SettingsManager' class."
        )


class UtilityNotFoundError(_CustomException):
    def __init__(self, utility: str):
        super().__init__(
            f"Utility '{utility}' not found. Please make sure the utility is installed. For more information view the README.md file."
        )


class BensoundDownloadError(_CustomException):
    def __init__(self, bensound_track: str):
        super().__init__(f"Failed to download Bensound track '{bensound_track}'!")
