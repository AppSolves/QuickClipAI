import atexit
import json
import os
import platform
import shutil
import sys
import threading
import uuid
from base64 import urlsafe_b64encode
from enum import Enum
from typing import Iterable

import ffmpeg
import typer
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv
from rich import print as rprint

from src.errors import EncryptionKeyNotFoundError


class classproperty:
    def __init__(self, func):
        self.fget = func

    def __get__(self, _, owner):
        return self.fget(owner)


def quit_function(
    fn_name,
    callback=None,
    callback_args: Iterable = (),
    exit_code: int | None = 1,
):
    # print to stderr, unbuffered in Python 2.
    typer.echo(
        "Function '{0}' took too long to finish. Aborting...".format(fn_name),
        file=sys.stderr,
    )
    sys.stderr.flush()  # Python 3 stderr is likely buffered.
    if callback is not None:
        callback(*callback_args)
    # now exit
    if exit_code is not None:
        sys.exit(exit_code)


def timeout(
    seconds: int,
    callback=None,
    callback_args: Iterable = (),
    exit_code: int | None = 1,
):
    def outer(fn):
        def inner(*args, **kwargs):
            timer = threading.Timer(
                seconds,
                quit_function,
                args=[fn.__name__, callback, callback_args, exit_code],
            )
            timer.start()
            try:
                result = fn(*args, **kwargs)
            finally:
                timer.cancel()
            return result

        return inner

    return outer


def Singleton(cls):
    __instance__ = None

    def __get_instance__(*args, **kwargs):
        nonlocal __instance__
        if __instance__ is None:
            __instance__ = cls(*args, **kwargs)
        return __instance__

    return __get_instance__


class _SessionID:
    def __init__(self, value: str | None) -> None:
        self.__value__ = value

    @property
    def value(self) -> str | None:
        return self.__value__

    def to_enum(self) -> "SessionID":
        return SessionID.explicit(self.value)  # type: ignore


class SessionID(Enum):
    TEMP = "temp"
    LAST = "last_session_id"
    NONE = None
    _EXPLICIT = "explicit"

    def __new__(cls, value: str | None) -> "SessionID":
        obj = object.__new__(cls)
        obj._value_ = value
        obj._explicit_set = False  # type: ignore
        return obj

    @classmethod
    def explicit(cls, session_id: str) -> "SessionID":
        explicit_member = cls._EXPLICIT
        explicit_member._value_ = session_id
        explicit_member._explicit_set = True  # type: ignore
        return explicit_member

    @property
    def value(self):
        if self == SessionID._EXPLICIT and not self._explicit_set:  # type: ignore
            raise ValueError("EXPLICIT session ID has not been set.")
        return self._value_

    def copy(self) -> "_SessionID":
        return _SessionID(self.value)


class Session:
    def __init__(self, session_id: _SessionID) -> None:
        self.__session_id__ = session_id
        assert self.__session_id__.value is not None
        metadata = self.__get_metadata__(
            self.__get_video_path__(self.__session_id__.value)
        )

        self.__video_owner__ = metadata.get("artist", "Unknown")
        self.__video_title__ = metadata.get("title", "Unknown")
        self.__video_description__ = metadata.get("description", "Unknown")
        try:
            self.__video_duration__ = float(
                ffmpeg.probe(self.__get_video_path__(self.__session_id__.value))
                .get("format", {})
                .get("duration", "Unknown")
            )
        except:
            self.__video_duration__ = "Unknown"
        try:
            self.__video_genre__ = int(metadata.get("genre", "Unknown"))
        except:
            self.__video_genre__ = "Unknown"
        try:
            self.__video_date__ = int(metadata.get("date", "Unknown"))
        except:
            self.__video_date__ = "Unknown"
        self.__video_tags__ = list(
            map(
                lambda tag: tag.strip(),
                metadata.get("comment", "").split(",") or [],
            )
        )
        self.__video_copyright__ = metadata.get("copyright", "Unknown")
        self.__video_credits__ = metadata.get("album", "Unknown")

    def __get_metadata__(self, video_path: str) -> dict[str, str]:
        p = ffmpeg.probe(video_path)
        metadata = p.get("format", {}).get("tags", {})

        if not metadata:
            raise ValueError("Metadata not found!")

        return json.loads(json.dumps(metadata))

    def __get_video_path__(self, session_id: str) -> str:
        def file_filter(file) -> bool:
            if not os.path.isfile(file) or not file.endswith(".mp4"):
                return False

            probe = ffmpeg.probe(file)
            if not probe:
                return False

            return probe["format"]["tags"].get("episode_id") == session_id

        try:
            file = tuple(
                filter(
                    lambda file: file_filter(os.path.join(self.__output_dir__, file)),
                    os.listdir(self.__output_dir__),
                )
            )[0]
        except IndexError:
            raise FileNotFoundError(f"No video found for session {session_id}!")
        return os.path.join(
            self.__output_dir__,
            file,
        )

    @property
    def __output_dir__(self) -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
        )

    @property
    def id(self) -> SessionID:
        return self.__session_id__.to_enum()

    @property
    def video_owner(self) -> str:
        return self.__video_owner__

    @property
    def video_title(self) -> str:
        return self.__video_title__

    @property
    def video_description(self) -> str:
        return self.__video_description__

    @property
    def video_duration(self) -> float | str:
        return self.__video_duration__

    @property
    def video_genre(self) -> int | str:
        return self.__video_genre__

    @property
    def video_date(self) -> int | str:
        return self.__video_date__

    @property
    def video_tags(self) -> list:
        return self.__video_tags__

    @property
    def video_copyright(self) -> str:
        return self.__video_copyright__

    @property
    def video_credits(self) -> str:
        return self.__video_credits__


@Singleton
class SettingsManager:
    def __init__(self, session_id: SessionID, verbose: bool = False) -> None:
        self.__verbose__ = verbose
        self.__config_file__ = os.path.join(self.root_dir, "config", "config.json")
        self.reinit()

        self.__session_id__ = session_id.value or uuid.uuid4().hex
        self.__session_id__ = (
            (self.last_session_id or self.__session_id__)
            if self.__session_id__ == "last_session_id"
            else self.__session_id__
        )
        os.makedirs(self.build_dir, exist_ok=True)

        def __save_session_id__():
            if self.__session_id__ != "temp":
                self.set("last_session_id", self.__session_id__)

        atexit.register(__save_session_id__)

    def get_metadata(self, video_path: str, verbose: bool = False) -> dict[str, str]:
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if verbose:
            typer.echo("Getting metadata...")

        p = ffmpeg.probe(video_path)
        metadata = p.get("format", {}).get("tags", {})

        if not metadata:
            raise ValueError("Metadata not found!")

        if verbose:
            typer.echo(f"Metadata: {json.dumps(metadata, indent=4)}")

        return json.loads(json.dumps(metadata))

    def get_video_path(self, session_id: str, quiet: bool = False) -> str | None:
        def file_filter(file) -> bool:
            if not os.path.isfile(file) or not file.endswith(".mp4"):
                return False

            probe = ffmpeg.probe(file)
            if not probe:
                return False

            return probe["format"]["tags"].get("episode_id") == session_id

        try:
            file = tuple(
                filter(
                    lambda file: file_filter(os.path.join(self.output_dir, file)),
                    os.listdir(self.output_dir),
                )
            )[0]
            return os.path.join(
                self.output_dir,
                file,
            )
        except IndexError:
            if not quiet:
                raise FileNotFoundError(f"No video found for session {session_id}!")
            else:
                return None

    def session_exists(self, session_id: SessionID) -> bool:
        if session_id == SessionID.LAST:
            session_id_str = self.last_session_id
        else:
            session_id_str = session_id.value

        return (
            os.path.exists(self.build_dir_for_session(session_id_str))
            if session_id_str
            else False
        )

    def get_sessions(self) -> list[Session]:
        past_topics = self.get("past_topics", {}) or {}
        assert isinstance(past_topics, dict)

        def get_session_id(id: str) -> _SessionID:
            return SessionID.explicit(id).copy()

        return [
            Session(get_session_id(session_id)) for session_id in past_topics.keys()
        ]

    @property
    def config(self) -> dict:
        return self.__config__

    @property
    def session_id(self) -> str:
        return self.__session_id__

    @property
    def last_session_id(self) -> str | None:
        return self.get("last_session_id")

    @property
    def verbose(self) -> bool:
        return self.__verbose__

    @verbose.setter
    def verbose(self, value: bool):
        self.__verbose__ = value

    def reinit(self):
        load_dotenv()
        try:
            with open(self.__config_file__, "r", encoding="utf-8") as f:
                self.__config__ = json.load(f)
        except:
            self.__config__ = {}

    def clean_build_dir(self):
        try:
            shutil.rmtree(self.build_dir)
            if self.__verbose__:
                typer.echo(f"Directory '{self.build_dir}' cleaned")
        except FileNotFoundError:
            rprint(f"[red]Error[/red]: Directory '{self.build_dir}' not found")
        os.makedirs(self.build_dir, exist_ok=True)

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        return self.set(key, value)

    def __delitem__(self, key):
        return self.delete(key)

    def __contains__(self, key):
        return self.has(key)

    @classproperty
    def encryption_enabled(cls) -> bool:
        return os.environ.get("ENCRYPTION_KEY", None) is not None

    @classproperty
    def __fernet_key__(cls) -> bytes:
        if not cls.encryption_enabled:
            raise EncryptionKeyNotFoundError()

        encryption_key = os.environ["ENCRYPTION_KEY"].encode()
        salt = b"4EL\xefE\xad\xb9\xc4\x9b\x8d:\x86\x95Sg\x99"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        key = kdf.derive(encryption_key)
        del encryption_key, salt, kdf
        return urlsafe_b64encode(key)

    @classproperty
    def root_dir(cls) -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @property
    def build_dir(self) -> str:
        return os.path.join(
            self.root_dir,
            "build",
            self.__session_id__,
        )

    @classproperty
    def chrome_profile_dir(cls) -> str:
        user_home = os.path.expanduser("~")

        if platform.system() == "Windows":
            profile_path = os.path.join(
                user_home, "AppData", "Local", "Google", "Chrome", "User Data"
            )
        elif platform.system() == "Darwin":
            profile_path = os.path.join(
                user_home, "Library", "Application Support", "Google", "Chrome"
            )
        elif platform.system() == "Linux":
            profile_path = os.path.join(user_home, ".config", "google-chrome")
        else:
            raise OSError("Unsupported operating system")

        if not os.path.isdir(os.path.join(profile_path, "Default")):
            raise FileNotFoundError(f"Profile directory not found: {profile_path}")

        return profile_path

    def build_dir_for_session(self, session_id: str) -> str:
        return os.path.join(
            self.root_dir,
            "build",
            session_id,
        )

    @classproperty
    def output_dir(cls) -> str:
        return os.path.join(cls.root_dir, "output")

    @classproperty
    def assets_dir(cls) -> str:
        return os.path.join(cls.root_dir, "assets")

    @classproperty
    def config_dir(cls) -> str:
        return os.path.join(cls.root_dir, "config")

    @property
    def immutable_keys(self) -> list:
        return []

    def has(self, key, check_none: bool = False):
        if key in self.__config__:
            return not (check_none and self.__config__[key] is None)

        if key in os.environ:
            return not (check_none and os.environ[key] is None)

        return False

    def get(self, key, default=None):
        if not self.has(key):
            return default

        if key in self.__config__:
            value = self.__config__[key]
        else:
            value = os.environ[key]

        if (
            value is not None
            and self.encryption_enabled
            and isinstance(value, str)
            and value.startswith("gAAAAA")
        ):
            try:
                value = json.loads(self.decrypt(value, ignore_errors=False))
            except:
                value = self.decrypt(value, ignore_errors=False)

        return value

    def set(self, key, value, encrypt: bool = False):
        if key in self.immutable_keys:
            return

        if encrypt:
            if (
                isinstance(value, str)
                or isinstance(value, bytes)
                or isinstance(value, list)
                or isinstance(value, dict)
            ):
                if isinstance(value, (list, dict)):
                    value = json.dumps(value)
                else:
                    value = str(value)

                value = self.encrypt(value, ignore_errors=False)
            else:
                raise ValueError("Cannot encrypt this type of value")

        self.__config__[key] = value
        try:
            with open(self.__config_file__, "w", encoding="utf-8") as f:
                json.dump(self.__config__, f, indent=4)
        except:
            pass

    def delete(self, key):
        if key in self.immutable_keys:
            return

        if self.has(key):
            del self.__config__[key]
            try:
                with open(self.__config_file__, "w", encoding="utf-8") as f:
                    json.dump(self.__config__, f, indent=4)
            except:
                pass

    def encrypt(self, value: str, ignore_errors: bool = True) -> str:
        if ignore_errors and (not self.encryption_enabled or not value):
            return value

        f = Fernet(self.__fernet_key__)
        value = f.encrypt(value.encode()).decode()
        del f
        return value

    def decrypt(self, value: str, ignore_errors: bool = True) -> str:
        if ignore_errors and (not self.encryption_enabled or not value):
            return value

        f = Fernet(self.__fernet_key__)
        value = f.decrypt(value.encode()).decode()
        del f
        return value
