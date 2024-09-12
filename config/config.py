import atexit
import json
import os
import shutil
import sys
import threading
import uuid
from base64 import urlsafe_b64encode
from typing import Iterable

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
    print(
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


@Singleton
class SettingsManager:
    def __init__(self, temp: bool = False, verbose: bool = False) -> None:
        self.__session_id__ = "temp" if temp else uuid.uuid4().hex
        self.__verbose__ = verbose
        self.__config_file__ = os.path.join(self.root_dir, "config", "config.json")
        os.makedirs(self.build_dir, exist_ok=True)
        self.reinit()

        def __save_session_id__():
            if self.__session_id__ != "temp":
                self.set("last_session_id", self.__session_id__)

        atexit.register(__save_session_id__)

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
                print(f"Directory '{self.build_dir}' cleaned")
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
