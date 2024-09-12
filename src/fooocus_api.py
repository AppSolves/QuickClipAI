import atexit
import os
import shutil
import subprocess as sp
import sys
import threading
from enum import Enum

import gradio_client as gc
import PIL.Image as Image
from rich import print as rprint

from config.config import SettingsManager, Singleton, classproperty, timeout
from src.errors import (FooocusNotFoundError, LoRaNotFoundError,
                        ModelNotFoundError)


class Model:
    def __init__(self, name: str) -> None:
        settings_manager = SettingsManager()
        path = settings_manager.get("fooocus_path", None)
        if (
            not path
            or not os.path.isfile(path["interpreter"])  # type: ignore
            or not os.path.isfile(path["script"])  # type: ignore
        ):
            raise FooocusNotFoundError()

        self.__name__ = name
        self.__checkpoints_path__ = os.path.join(
            os.path.dirname(path["script"]),  # type: ignore
            "models",
            "checkpoints",
        )

        if not self.file:
            raise ModelNotFoundError(name)

    @property
    def file(self) -> str | None:
        for file in os.listdir(self.__checkpoints_path__):
            if file.startswith(self.__name__):
                return file

        return None

    @property
    def name(self) -> str:
        return self.__name__

    @property
    def abs_path(self) -> str:
        if not self.file:
            raise ModelNotFoundError(self.__name__)
        return os.path.abspath(os.path.join(self.__checkpoints_path__, self.file))


class Refiner(Model):
    def __init__(self, name: str, weight: float = 0.5) -> None:
        super().__init__(name)
        self.__weight__ = max(0.1, min(weight, 1))

    @property
    def weight(self) -> float:
        return self.__weight__


class LoRa:
    def __init__(self, name: str, weight: float = 1) -> None:
        settings_manager = SettingsManager()
        path = settings_manager.get("fooocus_path", None)
        if (
            not path
            or not os.path.isfile(path["interpreter"])  # type: ignore
            or not os.path.isfile(path["script"])  # type: ignore
        ):
            raise FooocusNotFoundError()

        self.__name__ = name
        self.__weight__ = max(-2, min(weight, 2))
        self.__loras_path__ = os.path.join(
            os.path.dirname(path["script"]),  # type: ignore
            "models",
            "loras",
        )

        if not self.file:
            raise LoRaNotFoundError(name)

    @property
    def weight(self) -> float:
        return self.__weight__

    @property
    def file(self) -> str | None:
        for file in os.listdir(self.__loras_path__):
            if file.startswith(self.__name__):
                return file

        return None

    @property
    def name(self) -> str:
        return self.__name__

    @property
    def abs_path(self) -> str:
        if not self.file:
            raise LoRaNotFoundError(self.__name__)
        return os.path.abspath(os.path.join(self.__loras_path__, self.file))


class UpscaleMode(Enum):
    DISABLED = "Disabled"
    X_1_5 = "Upscale (1.5x)"
    X_2 = "Upscale (2x)"
    X_FAST_2 = "Upscale (Fast 2x)"


class Resolution(Enum):
    RES_704x1408 = ((704, 1408), (1, 2))
    RES_704x1344 = ((704, 1344), (11, 21))
    RES_768x1344 = ((768, 1344), (4, 7))
    RES_768x1280 = ((768, 1280), (3, 5))
    RES_832x1216 = ((832, 1216), (13, 19))
    RES_832x1152 = ((832, 1152), (13, 18))
    RES_896x1152 = ((896, 1152), (7, 9))
    RES_896x1088 = ((896, 1088), (14, 17))
    RES_960x1088 = ((960, 1088), (15, 17))
    RES_960x1024 = ((960, 1024), (15, 16))
    RES_1024x1024 = ((1024, 1024), (1, 1))
    RES_1024x960 = ((1024, 960), (16, 15))
    RES_1088x960 = ((1088, 960), (17, 15))
    RES_1088x896 = ((1088, 896), (17, 14))
    RES_1152x896 = ((1152, 896), (9, 7))
    RES_1152x832 = ((1152, 832), (18, 13))
    RES_1216x832 = ((1216, 832), (19, 13))
    RES_1280x768 = ((1280, 768), (5, 3))
    RES_1344x768 = ((1344, 768), (7, 4))
    RES_1344x704 = ((1344, 704), (21, 11))
    RES_1408x704 = ((1408, 704), (2, 1))
    RES_1472x704 = ((1472, 704), (23, 11))
    RES_1536x640 = ((1536, 640), (12, 5))
    RES_1600x640 = ((1600, 640), (5, 2))
    RES_1664x576 = ((1664, 576), (26, 9))
    RES_1728x576 = ((1728, 576), (3, 1))
    CLIP_ONLY_RES_1920x1080 = ((1920, 1080), (16, 9))
    CLIP_ONLY_RES_1080x1920 = ((1080, 1920), (9, 16))

    def __str__(self) -> str:
        return f"{self.value[0][0]}×{self.value[0][1]} | {self.value[1][0]}:{self.value[1][1]}"
    
class ImageType(Enum):
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"

@Singleton
class FooocusAPI:
    def __init__(
        self,
        verbose: bool = False,
    ) -> None:
        atexit.register(self.__dispose__, exit_code=None)
        self.__verbose__ = verbose
        try:
            self.__process__ = sp.Popen(
                self.__fooocus_cmd__,
                stdout=sp.PIPE,
                stderr=sp.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            raise FooocusNotFoundError()
        except Exception as e:
            rprint(f"[red]Error[/red]: {e}")
            self.__dispose__(exit_code=1)

        timeout(
            30,
            callback=self.__dispose__,
            exit_code=1,
        )(self.__wait_for_startup__)()

        def print_logs(fooocus_logs):
            ignore_lines = [
                "UserWarning: TypedStorage is deprecated",
                "%",
                "return self.fget.__get__(instance, owner)()",
            ]
            for line in fooocus_logs:
                if (
                    not line
                    or line.strip() == ""
                    or any(ignore_line in line for ignore_line in ignore_lines)
                    or not self.__verbose__
                ):
                    continue

                rprint(f"[cyan bold]FOOOCUS[/cyan bold]: {line}", end="")

        threading.Thread(
            target=print_logs, args=(self.fooocus_logs,), daemon=True
        ).start()

        try:
            self.__client__ = gc.Client(
                "http://127.0.0.1:7865/",
                serialize=False,
                verbose=self.__verbose__,
            )
            self.__client__.predict(fn_index=35)  # ???
            self.__client__.predict(fn_index=34)  # ???
            self.__client__.predict(
                "Inpaint or Outpaint (default)", fn_index=56
            )  # Set mode
            self.__client__.predict(
                "Inpaint or Outpaint (default)", fn_index=57
            )  # Set mode
            self.__client__.predict(
                "Inpaint or Outpaint (default)", fn_index=58
            )  # Set mode
            self.__client__.predict(
                "Inpaint or Outpaint (default)", fn_index=59
            )  # Set mode
            self.__client__.predict(None, fn_index=32)  # Aspect ratios
        except Exception as e:
            rprint(f"[red]Error[/red]: {e}")
            rprint(
                "[red]Error[/red]: Fooocus is not running. Can't establish a connection to the Fooocus server."
            )
            self.__dispose__(exit_code=1)

        self.__placeholder_img__ = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQImWNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def output_dir(self) -> str:
        settings_manager = SettingsManager()
        return os.path.join(settings_manager.build_dir, "pictures")

    @classproperty
    def fooocus_path(cls) -> dict[str, str] | None:
        settings_manager = SettingsManager()
        path = settings_manager.get("fooocus_path", None)
        return path  # type: ignore

    @property
    def fooocus_logs(self):
        if self.__process__:
            if self.__process__.stdout:
                for line in iter(self.__process__.stdout.readline, ""):
                    yield line
            if self.__process__.stderr:
                for line in iter(self.__process__.stderr.readline, ""):
                    yield line

    @property
    def verbose(self) -> bool:
        return self.__verbose__

    @verbose.setter
    def verbose(self, value: bool):
        self.__verbose__ = value

    def __wait_for_startup__(self) -> None:
        if not self.__process__:
            rprint(
                "[red]Error[/red]: Fooocus is not running. Can't establish a connection to the Fooocus server."
            )
            self.__dispose__(exit_code=1)

        for line in self.fooocus_logs:
            if "App started successful" in line:
                if self.__verbose__:
                    print("Fooocus has started successfully!")
                break

    @property
    def __fooocus_cmd__(self) -> list[str]:
        path = self.fooocus_path
        if (
            not path
            or not os.path.isfile(path["interpreter"])
            or not os.path.isfile(path["script"])
        ):
            raise FooocusNotFoundError()
        return [
            path["interpreter"],
            "-s",
            "-u",
            path["script"],
            "--disable-analytics",
            "--disable-in-browser",
            "--always-high-vram",
        ]

    def view_endpoints(self) -> None:
        if self.__verbose__:
            print("Gathering Fooocus endpoints...")
        self.__client__.view_api(all_endpoints=True)

    def __dispose__(self, exit_code: int | None = 0) -> None:
        if self.__process__:
            if self.__verbose__:
                print("Terminating Fooocus process...")

            self.__process__.terminate()

            try:
                self.__process__.wait(timeout=5)
            except sp.TimeoutExpired:
                if self.__verbose__:
                    print("Fooocus did not terminate in time, killing it...")

                self.__process__.kill()

            if self.__process__.poll() is None:
                if self.__verbose__:
                    print("Fooocus process is still running, forcefully killing it...")
                self.__process__.kill()

            if self.__process__.stdout:
                self.__process__.stdout.close()
            if self.__process__.stderr:
                self.__process__.stderr.close()

            self.__process__ = None

            if self.__verbose__:
                print("Fooocus process terminated and resources cleaned up.")

        if exit_code is not None:
            sys.exit(exit_code)

    def crop_picture(
        self,
        picture: str,
        resolution: Resolution,
        image_type: ImageType = ImageType.JPEG,
        save_picture: str | None = None,
    ) -> str | None | Image.Image:
        if not os.path.isfile(picture):
            return None

        if self.__verbose__:
            print(f"Clipping picture to {str(resolution).split("|")[0].strip()} resolution...")

        img = Image.open(picture)
        width, height = img.size
        new_width, new_height = resolution.value[0]

        if new_width > width or new_height > height:
            raise ValueError("New resolution is larger than the original picture!")

        left = (width - new_width) / 2
        top = (height - new_height) / 2
        right = (width + new_width) / 2
        bottom = (height + new_height) / 2

        img = img.crop((left, top, right, bottom))

        if self.__verbose__:
            print("Picture clipped!")
        
        if save_picture:
            if not save_picture.endswith(f".{image_type.value}"):
                save_picture += f".{image_type.value}"
            img.save(os.path.join(self.output_dir, save_picture), image_type.value)
            if self.__verbose__:
                print(f"Picture saved as: {save_picture}")
            return os.path.join(self.output_dir, save_picture)
        
        return img

    def generate_picture(
        self,
        prompt: str,
        model: Model,
        lora_1: LoRa,
        refiner: Refiner | None = None,
        resolution: Resolution = Resolution.RES_896x1152,
        image_type: ImageType = ImageType.JPEG,
        upscale_mode: UpscaleMode = UpscaleMode.DISABLED,
        save_picture: str | None = None,
    ) -> bool | str:
        if self.__verbose__:
            print(f"Setting Fooocus params...")
        self.__client__.predict(True, fn_index=53)  # Advanced: True
        self.__client__.predict(fn_index=65)  # ???
        self.__client__.predict(True, "0", fn_index=66)  # Random: True, Seed: 0
        self.__client__.predict(
            False,
            prompt,
            "unrealistic, saturated, high contrast, big nose, painting, drawing, sketch, cartoon, anime, manga, render, CG, 3d, watermark, signature, label",
            [
                "Fooocus V2",
                "Fooocus Photograph",
                "Fooocus Negative",
                "Fooocus Sharp",
                "Fooocus Masterpiece",
                "Fooocus Enhance",
                "Fooocus Cinematic",
            ],
            "Quality",
            f'{str(resolution).split("|")[0].strip()} <span style="color: grey;"> | {str(resolution).split("|")[1].strip()}</span>',
            1,
            image_type.value,
            "0",
            False,
            6,
            3,
            model.file,
            refiner.file if refiner else "None",
            refiner.weight if refiner else 0.5,
            True,
            lora_1.file if lora_1 else "None",
            lora_1.weight if lora_1 else 1,
            True,
            "None",
            1,
            True,
            "None",
            1,
            True,
            "None",
            1,
            True,
            "None",
            1,
            False,
            "uov",
            "Disabled",
            self.__placeholder_img__,
            [],
            self.__placeholder_img__,
            "",
            self.__placeholder_img__,
            False,
            False,
            False,
            False,
            1.5,
            0.8,
            0.3,
            7,
            2,
            "dpmpp_2m_sde_gpu",
            "karras",
            "Default (model)",
            -1,
            -1,
            -1,
            -1,
            -1,
            -1,
            False,
            False,
            False,
            False,
            64,
            128,
            "joint",
            0.25,
            False,
            1.01,
            1.02,
            0.99,
            0.95,
            False,
            False,
            "v2.6",
            1,
            0.618,
            False,
            False,
            0,
            False,
            False,
            "fooocus",
            self.__placeholder_img__,
            0.5,
            0.6,
            "ImagePrompt",
            self.__placeholder_img__,
            0.5,
            0.6,
            "ImagePrompt",
            self.__placeholder_img__,
            0.5,
            0.6,
            "ImagePrompt",
            self.__placeholder_img__,
            0.5,
            0.6,
            "ImagePrompt",
            False,
            0,
            False,
            None,
            False if upscale_mode == UpscaleMode.DISABLED else True,
            upscale_mode.value,
            "Before First Enhancement",
            "Original Prompts",
            False,
            "",
            "",
            "",
            "sam",
            "full",
            "vit_b",
            0.25,
            0.3,
            0,
            False,
            "v2.6",
            1,
            0.618,
            0,
            False,
            False,
            "",
            "",
            "",
            "sam",
            "full",
            "vit_b",
            0.25,
            0.3,
            0,
            False,
            "v2.6",
            1,
            0.618,
            0,
            False,
            False,
            "",
            "",
            "",
            "sam",
            "full",
            "vit_b",
            0.25,
            0.3,
            0,
            False,
            "v2.6",
            1,
            0.618,
            0,
            False,
            fn_index=67,
        )
        if self.__verbose__:
            print("Generating picture...")
        result = self.__client__.predict(fn_index=68)[3]["value"]  # Generate picture
        result = result[0] if upscale_mode == UpscaleMode.DISABLED else result[1]
        if self.__verbose__:
            print(f"Picture generated! Result: {result}")
        for i in range(69, 73):
            self.__client__.predict(fn_index=i)  # ???
        if not result["is_file"]:
            return False

        if save_picture:
            if not save_picture.endswith(f".{image_type.value}"):
                save_picture += f".{image_type.value}"

            shutil.copy(
                result["name"],
                os.path.join(self.output_dir, save_picture),
            )
            if self.__verbose__:
                print(f"Picture saved as: {save_picture}")
            return os.path.join(self.output_dir, save_picture)

        return result["name"]
