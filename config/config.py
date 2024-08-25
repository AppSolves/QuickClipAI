import json
import os


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
    def __init__(self):
        self.__config_file__ = os.path.join(self.root_dir, "config", "config.json")
        self.reinit()

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        return self.set(key, value)

    def __delitem__(self, key):
        return self.delete(key)

    def __contains__(self, key):
        return self.has(key)

    @property
    def root_dir(self) -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @property
    def immutable_keys(self) -> list:
        return []

    def reinit(self):
        try:
            with open(self.__config_file__, "r", encoding="utf-8") as f:
                self.__config__ = json.load(f)
        except:
            self.__config__ = {}

    def has(self, key, check_none: bool = False):
        if check_none:
            return key in self.__config__ and self.__config__[key] is not None
        return key in self.__config__

    def get(self, key, default=None):
        return self.__config__.get(key, default)

    def set(self, key, value):
        if key in self.immutable_keys:
            return

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
