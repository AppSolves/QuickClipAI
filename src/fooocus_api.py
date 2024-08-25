import gradio_client as gc


class FooocusAPI:
    def __init__(self) -> None:
        self.__client__ = gc.Client("http://127.0.0.1:7865/", serialize=False)

    def generate_picture(self, prompt: str):
        result = self.__client__.predict(
            prompt,
            fn_index=40,
        )
        print(result)
        result = self.__client__.predict(fn_index=41)
        print(result)


FooocusAPI().generate_picture("A picture of a cat")
