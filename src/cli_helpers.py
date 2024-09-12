import re
from io import StringIO

import typer.core
from rich.console import Console
from rich.text import Text


class AliasGroup(typer.core.TyperGroup):
    _CMD_SPLIT_P = r"[,| ?\/]"

    def get_command(self, ctx, cmd_name):
        cmd_name = self._group_cmd_name(cmd_name)
        return super().get_command(ctx, cmd_name)

    def _group_cmd_name(self, default_name):
        for cmd in self.commands.values():
            if cmd.name and default_name in re.split(self._CMD_SPLIT_P, cmd.name):
                return cmd.name
        return default_name


def prettify(text_to_prettify: str) -> str:
    # Initialize a Console object
    console = Console()

    # Create a Text object with rich syntax
    text = Text.from_markup(text_to_prettify)

    # Use StringIO to capture the output
    with StringIO() as buf:
        console.file = buf  # Redirect console output to the buffer
        console.print(text)  # Use rich to render the text
        output = buf.getvalue()  # Get the rendered output as a string

    return output.strip()
