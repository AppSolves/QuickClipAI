import json
import os
import random as rd
import shutil
import sys
import traceback
from pathlib import Path
from typing import Annotated, Optional

import captametropolis
import typer
from rich.console import Console
from rich.table import Table

from src.cli_helpers import AliasGroup


def excepthook(type, value, tb):
    if type == KeyboardInterrupt:
        return
    traceback.print_exception(type, value, tb)


sys.excepthook = excepthook

is_verbose: bool = False
app: typer.Typer = typer.Typer(
    name="QuickClipAI",
    help=":sparkles: An [italic]awesome[/italic] [orange1]CLI tool[/orange1] to create and publish [bold cyan]beautiful[/bold cyan] YouTube Shorts/Instagram Reels/TikToks. :sparkles:",
    rich_markup_mode="rich",
    epilog="Made with [red]:red_heart:[/red]  and :muscle: by [cyan]AppSolves[/cyan] | [blue link=https://appsolves.dev]Website[/blue link] | [blue link=https://github.com/AppSolves]GitHub[/blue link]",
    cls=AliasGroup,
    context_settings={
        "help_option_names": ["-h", "--help", "-?"],
    },
)
topics_app = typer.Typer(
    name="topics",
    help="[purple]Manage[/purple] the [bold cyan]beautiful[/bold cyan] video topics. :scroll:",
    rich_markup_mode="rich",
    cls=AliasGroup,
    context_settings={
        "help_option_names": ["-h", "--help", "-?"],
    },
    rich_help_panel="Video: Information",
)
build_app = typer.Typer(
    name="build",
    help="[purple]Manage[/purple] the [bold cyan]beautiful[/bold cyan] video build. :clapper:",
    rich_markup_mode="rich",
    cls=AliasGroup,
    context_settings={
        "help_option_names": ["-h", "--help", "-?"],
    },
    rich_help_panel="Video: Management",
)
settings_app = typer.Typer(
    name="settings, config",
    help="[purple]Manage[/purple] the [bold cyan]beautiful[/bold cyan] app settings. :gear:",
    rich_markup_mode="rich",
    cls=AliasGroup,
    context_settings={
        "help_option_names": ["-h", "--help", "-?"],
    },
    rich_help_panel="Settings: Configuration",
)
app.add_typer(settings_app, name="settings", rich_help_panel="Video: Configuration")
app.add_typer(build_app, name="build", rich_help_panel="Video: Management")
app.add_typer(topics_app, name="topics", rich_help_panel="Video: Information")


@app.callback()
def main(
    verbose: Annotated[
        bool,
        typer.Option(
            ...,
            "--verbose",
            "-v",
            help="Specify whether or not to enable [purple]verbose[/purple] output. :loud_sound:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = False,
):
    global is_verbose
    is_verbose = verbose


from config.config import SessionID, SettingsManager
from src.elevenlabs_api import ElevenLabsAPI
from src.fooocus_api import FooocusAPI, ImageType, LoRa, Model, Resolution, UpscaleMode
from src.g4f_api import G4FAPI, Message, MessageSender
from src.moviepy_api import (
    BackgroundMusic,
    BensoundBackgroundMusic,
    MoviepyAPI,
    Overlay,
    SubtitleOptions,
)
from src.prompt_manager import PromptManager
from src.upload_api import UploadAPI


@app.command(
    name="generate, new",
    help="[purple]Create[/purple] a [italic]new[/italic] [bold cyan]beautiful[/bold cyan] video. :clapper:",
    rich_help_panel="Video: Management",
)
def generate(
    temporary: Annotated[
        bool,
        typer.Option(
            ...,
            "--temporary",
            "-t",
            help="Specify whether or not to enable [purple]temporary[/purple] mode. :wastebasket:",
            rich_help_panel="Options: Configuration",
        ),
    ] = False,
    owner: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--owner",
            "-o",
            help="Specify the [purple]owner[/purple] of the video. :bust_in_silhouette:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
    voice_id: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--voice-id",
            "-vid",
            help="Specify the [purple]voice ID[/purple] to use for the voiceover. :microphone:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ] = None,
    genre: Annotated[
        int,
        typer.Option(
            ...,
            "--genre",
            "-g",
            help="Specify the [purple]genre[/purple] of the video. :musical_note:",
            rich_help_panel="Options: Customization",
        ),
    ] = 28,
    num_threads: Annotated[
        int,
        typer.Option(
            ...,
            "--num-threads",
            "-nt",
            help="Specify the [purple]number of threads[/purple] to use for video generation. :thread:",
            show_default=True,
            rich_help_panel="Options: Configuration",
        ),
    ] = 4,
):
    settings_manager = SettingsManager(
        session_id=SessionID.TEMP if temporary else SessionID.NONE,
        verbose=is_verbose,
    )
    typer.echo(f"Session UID: {settings_manager.session_id}")
    g4f_api = G4FAPI(verbose=is_verbose, model="gpt-4o-mini")
    elevenlabs_api = ElevenLabsAPI(verbose=is_verbose)
    fooocus_api = FooocusAPI(verbose=is_verbose)
    prompt_manager = PromptManager()
    moviepy_api = MoviepyAPI(verbose=is_verbose)

    video_text_paragraphs = g4f_api.get_response(
        Message(MessageSender.USER, prompt_manager.get_prompt("video_idea")),
        save_response="voiceover.txt",
    ).content  # type: ignore
    video_text_paragraphs = tuple(
        map(
            str.strip,
            [pg.replace("*", "") for pg in video_text_paragraphs.split("\n") if pg],
        )
    )

    for index, paragraph in enumerate(video_text_paragraphs):
        if is_verbose:
            typer.echo(f"{index + 1}. {paragraph}")
        elevenlabs_api.generate_audio(
            paragraph,
            voice_id=voice_id,
            save_audio=str(index),
        )

    fooocus_prompts = g4f_api.get_response(
        Message(MessageSender.USER, prompt_manager.get_prompt("picture_generation")),
        save_response="pictureprompts.txt",
    ).content  # type: ignore
    fooocus_prompts = tuple(
        map(str.strip, [prompt for prompt in fooocus_prompts.split("\n") if prompt])
    )

    for index, prompt in enumerate(fooocus_prompts):
        is_last = index == len(fooocus_prompts) - 1
        if is_verbose:
            typer.echo(f"{index + 1}. {prompt}")
        fooocus_api.generate_picture(
            prompt,
            image_type=ImageType.JPEG,
            resolution=Resolution.RES_768x1344,
            model=Model("juggernautXL_v8Rundiffusion"),
            lora_1=LoRa("sd_xl_offset_example-lora_1.0", weight=0.1),
            upscale_mode=UpscaleMode.X_1_5,
            save_picture="thumbnail" if is_last else str(index),
        )

    video_info = g4f_api.get_response(
        Message(MessageSender.USER, prompt_manager.get_prompt("video_info")),
        save_response="video_info.txt",
    ).content  # type: ignore
    video_title, video_description, video_hashtags = tuple(
        map(
            lambda info: (
                tuple(
                    map(
                        lambda tag: tag.strip().replace("#", ""),
                        info[1].split(","),
                    )
                )
                if info[0] == 2
                else info[1].strip()
            ),
            enumerate([info for info in video_info.split("\n") if info]),
        )
    )

    background_musics = [
        lambda: BackgroundMusic(
            r"D:\Hobbys\YouTube\CurioBurstz\Assets\background_music_1.mp3",
            volume_factor=0.1,
            credits="\nSong: Sappheiros - Lights (Vlog No Copyright Music)\nMusic promoted by Vlog No Copyright Music.\nVideo Link: https://youtu.be/kzeQK45StRo\n",
        ),
        lambda: BackgroundMusic(
            r"D:\Hobbys\YouTube\CurioBurstz\Assets\background_music_2.mp3",
            volume_factor=0.1,
            credits="\nSong: Chill Day - LAKEY INSPIRED\nLink: https://soundcloud.com/lakeyinspired/chill-day\nLicense: Creative Commons Attribution-ShareAlike 3.0\nLicense Link: https://creativecommons.org/licenses/by-sa/3.0/\n",
        ),
        lambda: BensoundBackgroundMusic(
            "the lounge",
            volume_factor=0.2,
        ),
    ]
    background_music = rd.choice(background_musics)()
    moviepy_api.generate_video(
        audio_paths=[
            os.path.join(elevenlabs_api.output_dir, audio)
            for audio in os.listdir(elevenlabs_api.output_dir)
        ],
        picture_paths=[
            os.path.join(fooocus_api.output_dir, picture)
            for picture in os.listdir(fooocus_api.output_dir)
            if not picture.startswith("thumbnail")
        ],
        background_music=background_music,
        overlays=[
            Overlay(
                r"D:\Hobbys\YouTube\CurioBurstz\Allgemein\Subscribe-Popup.mov",
                start_sec=25,
                size=0.5,
                rel_position=("center", "top"),
                is_transparent=True,
                volume_factor=0.4,
            )
        ],
        metadata={
            "artist": owner,
            "title": video_title,
            "description": video_description,  # type: ignore
            "comment": list(video_hashtags),
            "genre": str(genre),
        },
        max_length=59,
        num_threads=num_threads,
        subtitle_options=SubtitleOptions(
            highlight_color=["yellow", "cyan"],
            font_path=os.path.join(
                settings_manager.assets_dir,
                "project",
                "fonts",
                "TheBoldFont.ttf",
            ),
            font_size=90,
            stroke_width=10,
            rel_height_pos=0.3,
        ),
    )
    past_topics = settings_manager.get("past_topics", {}) or {}
    if video_title not in past_topics:  # type: ignore
        past_topics[settings_manager.session_id] = video_title  # type: ignore
        settings_manager.set("past_topics", past_topics)


@app.command(
    name="regenerate, rebuild, continue, resume",
    help="[purple]Form[/purple] a [italic]new[/italic] [bold cyan]beautiful[/bold cyan] video out of the current build assets. :clapper:",
    rich_help_panel="Video: Management",
)
def regenerate(
    session_id: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--session-id",
            "-sid",
            help="Specify the build's [purple]session ID[/purple] to use for the video regeneration (set to 'temp' for temporary mode). :id:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
    owner: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--owner",
            "-o",
            help="Specify the [purple]owner[/purple] of the video. :bust_in_silhouette:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
    genre: Annotated[
        int,
        typer.Option(
            ...,
            "--genre",
            "-g",
            help="Specify the [purple]genre[/purple] of the video. :musical_note:",
            rich_help_panel="Options: Customization",
        ),
    ] = 28,
    num_threads: Annotated[
        int,
        typer.Option(
            ...,
            "--num-threads",
            "-nt",
            help="Specify the [purple]number of threads[/purple] to use for video generation. :thread:",
            show_default=True,
            rich_help_panel="Options: Configuration",
        ),
    ] = 4,
):
    settings_manager = SettingsManager(
        session_id=(
            (SessionID.TEMP if session_id == "temp" else SessionID.explicit(session_id))
            if session_id
            else SessionID.LAST
        ),
        verbose=is_verbose,
    )
    typer.echo(f"Session UID: {settings_manager.session_id}")
    elevenlabs_api = ElevenLabsAPI(verbose=is_verbose)
    fooocus_api = FooocusAPI(verbose=is_verbose)
    moviepy_api = MoviepyAPI(verbose=is_verbose)  #

    video_path = settings_manager.get_video_path(
        settings_manager.session_id, quiet=True
    )
    if video_path:
        os.remove(video_path)

    if not os.path.isfile(
        os.path.join(settings_manager.build_dir, "responses", "video_info.txt")
    ) or not (
        os.path.isfile(
            os.path.join(settings_manager.build_dir, "responses", "pictureprompts.txt")
        )
        and os.listdir(fooocus_api.output_dir)
    ):
        try:
            with open(
                os.path.join(settings_manager.build_dir, "responses", "voiceover.txt"),
                "r",
                encoding="utf-8",
            ) as f:
                voiceover = "\n".join([line for line in f.readlines() if line.strip()])
        except FileNotFoundError:
            if not os.listdir(elevenlabs_api.output_dir):
                typer.echo("No voiceover found.")
                raise typer.Exit(code=1)

            voiceover = ""
            with open(
                os.path.join(settings_manager.build_dir, "responses", "voiceover.txt"),
                "w",
                encoding="utf-8",
            ) as f:
                for audio in os.listdir(elevenlabs_api.output_dir):
                    segments = captametropolis.transcriber.transcribe_locally(
                        os.path.join(elevenlabs_api.output_dir, audio)
                    )
                    for segment in segments:
                        f.write(segment["text"] + "\n")  # type: ignore
                        voiceover += segment["text"] + "\n"  # type: ignore

        voiceover = voiceover.strip().replace("*", "")
        g4f_api = G4FAPI(verbose=is_verbose, model="gpt-4o-mini")
        prompt_manager = PromptManager()
        g4f_api.add_message(
            Message(MessageSender.USER, prompt_manager.get_prompt("video_idea")),
        )
        g4f_api.add_message(Message(MessageSender.ASSISTANT, voiceover))
        if is_verbose:
            typer.echo(voiceover)
        if not os.path.isfile(
            os.path.join(settings_manager.build_dir, "responses", "pictureprompts.txt")
        ) or not os.listdir(fooocus_api.output_dir):
            fooocus_prompts = g4f_api.get_response(
                Message(
                    MessageSender.USER, prompt_manager.get_prompt("picture_generation")
                ),
                save_response="pictureprompts.txt",
            ).content  # type: ignore
            fooocus_prompts = tuple(
                map(
                    str.strip,
                    [prompt for prompt in fooocus_prompts.split("\n") if prompt],
                )
            )

            for index, prompt in enumerate(fooocus_prompts):
                is_last = index == len(fooocus_prompts) - 1
                if is_verbose:
                    typer.echo(f"{index + 1}. {prompt}")
                fooocus_api.generate_picture(
                    prompt,
                    image_type=ImageType.JPEG,
                    resolution=Resolution.RES_768x1344,
                    model=Model("juggernautXL_v8Rundiffusion"),
                    lora_1=LoRa("sd_xl_offset_example-lora_1.0", weight=0.1),
                    upscale_mode=UpscaleMode.X_1_5,
                    save_picture="thumbnail" if is_last else str(index),
                )
        video_info = g4f_api.get_response(
            Message(MessageSender.USER, prompt_manager.get_prompt("video_info")),
            save_response="video_info.txt",
        ).content  # type: ignore

        video_title, video_description, video_hashtags = tuple(
            map(
                lambda info: (
                    tuple(
                        map(
                            lambda tag: tag.strip().replace("#", ""),
                            info[1].split(","),
                        )
                    )
                    if info[0] == 2
                    else info[1].strip()
                ),
                enumerate([info for info in video_info.split("\n") if info]),
            )
        )
    else:
        with open(
            os.path.join(settings_manager.build_dir, "responses", "video_info.txt"),
            "r",
            encoding="utf-8",
        ) as f:
            video_info = [line for line in f.readlines() if line.strip()]
        video_title, video_description, video_hashtags = tuple(
            map(
                lambda info: (
                    tuple(
                        map(
                            lambda tag: tag.strip().replace("#", ""),
                            info[1].split(","),
                        )
                    )
                    if info[0] == 2
                    else info[1].strip()
                ),
                enumerate(video_info),
            )
        )

    if not os.listdir(elevenlabs_api.output_dir):
        with open(
            os.path.join(settings_manager.build_dir, "responses", "voiceover.txt"),
            "r",
            encoding="utf-8",
        ) as f:
            voiceover = "\n".join([line for line in f.readlines() if line.strip()])
        voiceover = voiceover.strip().replace("*", "")
        for index, paragraph in enumerate(voiceover.split("\n")):
            if is_verbose:
                typer.echo(f"{index + 1}. {paragraph}")
            elevenlabs_api.generate_audio(
                paragraph,
                voice_id=None,
                save_audio=str(index),
            )

    background_musics = [
        lambda: BackgroundMusic(
            r"D:\Hobbys\YouTube\CurioBurstz\Assets\background_music_1.mp3",
            volume_factor=0.1,
            credits="\nSong: Sappheiros - Lights (Vlog No Copyright Music)\nMusic promoted by Vlog No Copyright Music.\nVideo Link: https://youtu.be/kzeQK45StRo\n",
        ),
        lambda: BackgroundMusic(
            r"D:\Hobbys\YouTube\CurioBurstz\Assets\background_music_2.mp3",
            volume_factor=0.1,
            credits="\nSong: Chill Day - LAKEY INSPIRED\nLink: https://soundcloud.com/lakeyinspired/chill-day\nLicense: Creative Commons Attribution-ShareAlike 3.0\nLicense Link: https://creativecommons.org/licenses/by-sa/3.0/\n",
        ),
        lambda: BensoundBackgroundMusic(
            "the lounge",
            volume_factor=0.3,
        ),
    ]
    background_music = rd.choice(background_musics)()
    moviepy_api.generate_video(
        audio_paths=[
            os.path.join(elevenlabs_api.output_dir, audio)
            for audio in os.listdir(elevenlabs_api.output_dir)
        ],
        picture_paths=[
            os.path.join(fooocus_api.output_dir, picture)
            for picture in os.listdir(fooocus_api.output_dir)
            if not picture.startswith("thumbnail")
        ],
        background_music=background_music,
        overlays=[
            Overlay(
                r"D:\Hobbys\YouTube\CurioBurstz\Allgemein\Subscribe-Popup.mov",
                start_sec=25,
                size=0.5,
                rel_position=("center", "top"),
                is_transparent=True,
                volume_factor=0.4,
            )
        ],
        metadata={
            "artist": owner,
            "title": video_title,
            "description": video_description,  # type: ignore
            "comment": list(video_hashtags),
            "genre": str(genre),
        },
        max_length=59,
        num_threads=num_threads,
        subtitle_options=SubtitleOptions(
            highlight_color=["yellow", "cyan"],
            font_path=os.path.join(
                settings_manager.assets_dir,
                "project",
                "fonts",
                "TheBoldFont.ttf",
            ),
            font_size=90,
            stroke_width=10,
            rel_height_pos=0.3,
        ),
    )
    past_topics = settings_manager.get("past_topics", {}) or {}
    if video_title not in past_topics:  # type: ignore
        past_topics[settings_manager.session_id] = video_title  # type: ignore
        settings_manager.set("past_topics", past_topics)


@app.command(
    name="upload, publish",
    help="[purple]Publish[/purple] the [bold cyan]beautiful[/bold cyan] video. :rocket:",
    rich_help_panel="Video: Management",
)
def upload(
    session_id: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--session-id",
            "-sid",
            help="Specify the video's [purple]session ID[/purple] to use for the video upload (set to 'temp' for temporary mode). :id:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
    youtube: Annotated[
        bool,
        typer.Option(
            ...,
            "--youtube/--no-youtube",
            "-y/-ny",
            help="Specify whether or not to upload to [purple]YouTube[/purple]. :tv:",
            rich_help_panel="Options: Platform",
        ),
    ] = True,
    instagram: Annotated[
        bool,
        typer.Option(
            ...,
            "--instagram/--no-instagram",
            "-i/-ni",
            help="Specify whether or not to upload to [purple]Instagram[/purple]. :camera:",
            rich_help_panel="Options: Platform",
        ),
    ] = True,
    tiktok: Annotated[
        bool,
        typer.Option(
            ...,
            "--tiktok/--no-tiktok",
            "-t/-nt",
            help="Specify whether or not to upload to [purple]TikTok[/purple]. :musical_note:",
            rich_help_panel="Options: Platform",
        ),
    ] = True,
    thumbnail_path: Annotated[
        Optional[Path],
        typer.Option(
            ...,
            "--thumbnail-path",
            "-tp",
            help="Specify the [purple]thumbnail path[/purple] to use for the video. :frame_photo:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
):
    if not youtube and not instagram and not tiktok:
        typer.echo("Please select at least one platform to upload the video.")
        raise typer.Exit(code=1)

    if thumbnail_path is not None and not thumbnail_path.exists():
        typer.echo("The thumbnail path does not exist.")
        raise typer.Exit(code=1)

    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    upload_api = UploadAPI(verbose=is_verbose)
    session_id = session_id or settings_manager.last_session_id
    if not session_id or not settings_manager.session_exists(
        SessionID.explicit(session_id)
    ):
        typer.echo(
            "No session ID found. Please provide a session ID to upload the video."
        )
        raise typer.Exit(code=1)
    typer.echo(f"Session UID: {session_id}")
    result = upload_api.upload(session_id, youtube, instagram, tiktok, thumbnail_path)
    if not result:
        typer.echo("Failed to upload the video.")
        raise typer.Exit(code=1)
    typer.echo("Video uploaded successfully.")


@app.command(
    name="inspect, info, metadata",
    help="[purple]View[/purple] the [bold cyan]beautiful video's[/bold cyan] metadata. :gear:",
    rich_help_panel="Video: Information",
)
def inspect(
    session_id: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--session-id",
            "-sid",
            help="Specify the video's [purple]session ID[/purple] to use for the video inspection (set to 'temp' for temporary mode). :id:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    session_id = session_id or settings_manager.last_session_id
    if not session_id or not settings_manager.session_exists(
        SessionID.explicit(session_id)
    ):
        typer.echo(
            "No session ID found. Please provide a session ID to inspect the video."
        )
        raise typer.Exit(code=1)
    typer.echo(f"Session UID: {session_id}")
    video_path = settings_manager.get_video_path(session_id)
    metadata = settings_manager.get_metadata(video_path or "")
    typer.echo(json.dumps(metadata, indent=4))


@topics_app.command(
    name="list",
    help="[purple]List[/purple] the [bold cyan]beautiful[/bold cyan] video topics. :scroll:",
    rich_help_panel="Video: Information",
)
def list_topics(
    filter_keywords: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--filter-keywords",
            "-fk",
            help="Specify the [purple]keywords (comma separated)[/purple] to filter the video topics. :hash:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ] = None,
    enforce: Annotated[
        bool,
        typer.Option(
            ...,
            "--all/--any",
            help="Specify whether to [purple]enforce[/purple] all or any of the filter keywords. :hash:",
            rich_help_panel="Options: Customization",
        ),
    ] = False,
):
    topic_filter = (
        tuple(
            [
                keyword.strip()
                for keyword in filter_keywords.strip().replace("#", "").split(",")
                if keyword
            ]
        )
        if filter_keywords
        else None
    )
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    past_topics = list(settings_manager.get("past_topics", {}).values() or [])  # type: ignore
    filter_method = all if enforce else any
    for index, topic in enumerate(past_topics):
        if topic_filter:
            if filter_method(
                keyword.lower() in topic.lower() for keyword in topic_filter
            ):
                typer.echo(f"{index + 1}. {topic}")
        else:
            typer.echo(f"{index + 1}. {topic}")

    if not past_topics:
        typer.echo("No video topics found.")
        raise typer.Exit(code=1)


@topics_app.command(
    name="delete, remove",
    help="[purple]Delete[/purple] the [bold cyan]beautiful[/bold cyan] video topic. :wastebasket:",
    rich_help_panel="Video: Management",
)
def delete_topic(
    topic_index: Annotated[
        int,
        typer.Argument(
            ...,
            help="Specify the [purple]index[/purple] of the video topic to delete (starting with 0). :1234:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ],
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    past_topics = settings_manager.get("past_topics", {}) or {}
    assert isinstance(past_topics, dict)
    if not past_topics:
        typer.echo("No video topics found.")
        raise typer.Exit(code=1)
    if not 0 <= topic_index < len(past_topics):
        typer.echo("Invalid topic index.")
        raise typer.Exit(code=1)
    topic = past_topics.pop(list(past_topics.keys())[topic_index])
    settings_manager.set("past_topics", past_topics)
    typer.echo(f"Deleted video topic: {topic}")


@build_app.command(
    name="open, explore",
    help="[purple]Open[/purple] the [bold cyan]beautiful[/bold cyan] video build directory. :file_folder:",
    rich_help_panel="Video: Management",
)
def open_build_dir(
    session_id: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--session-id",
            "-sid",
            help="Specify the video's [purple]session ID[/purple] to open the build directory. :id:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
    sub_path: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--sub-path",
            "-sp",
            help="Specify the [purple]sub path[/purple] to open within the build directory (e.g. 'pictures/0.jpeg'). :file_folder:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ] = None,
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    session_id = session_id or settings_manager.last_session_id
    if not session_id or not settings_manager.session_exists(
        SessionID.explicit(session_id)
    ):
        typer.echo(
            "No session ID found. Please provide a session ID to open the build directory."
        )
        raise typer.Exit(code=1)
    typer.echo(f"Session UID: {session_id}")
    path_to_open = settings_manager.build_dir_for_session(session_id)
    if sub_path and os.path.exists(os.path.join(path_to_open, sub_path)):
        path_to_open = os.path.join(path_to_open, sub_path)
    os.system(f'start "" "{path_to_open}"')


@build_app.command(
    name="list, ls",
    help="[purple]List[/purple] the [bold cyan]beautiful[/bold cyan] video build directory. :scroll:",
    rich_help_panel="Video: Information",
)
def list_build_dir(
    session_id: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--session-id",
            "-sid",
            help="Specify the video's [purple]session ID[/purple] to list the build directory. :id:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    session_id = session_id or settings_manager.last_session_id
    if not session_id or not settings_manager.session_exists(
        SessionID.explicit(session_id)
    ):
        typer.echo(
            "No session ID found. Please provide a session ID to list the build directory."
        )
        raise typer.Exit(code=1)
    typer.echo(f"Session UID: {session_id}")
    path_to_list = settings_manager.build_dir_for_session(session_id)
    if not os.path.exists(path_to_list):
        typer.echo("No build directory found.")
        raise typer.Exit(code=1)

    if os.name == "nt":
        os.system(f'tree "{path_to_list}" /F')
    else:
        os.system(f'ls -R "{path_to_list}"')


@build_app.command(
    name="delete, remove",
    help="[purple]Delete[/purple] the [bold cyan]beautiful[/bold cyan] video build directory. :wastebasket:",
    rich_help_panel="Video: Management",
)
def delete_build_dir(
    session_id: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--session-id",
            "-sid",
            help="Specify the video's [purple]session ID[/purple] to delete the build directory. :id:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
    sub_path: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--sub-path",
            "-sp",
            help="Specify the [purple]sub path[/purple] to delete within the build directory (e.g. 'pictures/0.jpeg'). :file_folder:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ] = None,
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    session_id = session_id or settings_manager.last_session_id
    if not session_id or not settings_manager.session_exists(
        SessionID.explicit(session_id)
    ):
        typer.echo(
            "No session ID found. Please provide a session ID to delete the build directory."
        )
        raise typer.Exit(code=1)
    typer.echo(f"Session UID: {session_id}")
    path_to_delete = settings_manager.build_dir_for_session(session_id)
    if sub_path and os.path.exists(os.path.join(path_to_delete, sub_path)):
        path_to_delete = os.path.join(path_to_delete, sub_path)
    if os.path.exists(path_to_delete):
        if os.path.isfile(path_to_delete):
            os.remove(path_to_delete)
        else:
            shutil.rmtree(path_to_delete)
    typer.echo("Deleted video build directory.")


@build_app.command(
    name="sessions",
    help="[purple]List[/purple] the [bold cyan]beautiful[/bold cyan] video sessions. :scroll:",
    rich_help_panel="Video: Information",
)
def sessions(
    ids_only: Annotated[
        bool,
        typer.Option(
            ...,
            "--ids-only",
            "-io",
            help="Specify whether or not to show only the session IDs. :id:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ] = False,
    last_only: Annotated[
        bool,
        typer.Option(
            ...,
            "--last-only",
            "-lo",
            help="Specify whether or not to show only the last session ID. :id:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ] = False,
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    sessions = settings_manager.get_sessions()
    typer.echo(
        f"Total Sessions: {len(sessions)}\n" if not last_only else "Last Session:\n"
    )

    if ids_only:
        if last_only:
            typer.echo(settings_manager.last_session_id)
            return

        for index, session in enumerate(sessions):
            typer.echo(f"{index + 1}. {session.id.value}")
        return

    console = Console()
    table = Table(title="Video Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Owner", style="green")
    table.add_column("Created At", style="white")
    table.add_column("Duration (in s)", style="magenta")
    table.add_column("Title", style="yellow")
    table.add_column("Description", style="blue")
    table.add_column("Hashtags", style="red")
    table.add_column("Genre", style="purple")
    table.add_column("Copyright", style="orange1")
    table.add_column("Credits", style="cyan")
    for session in sessions:
        if last_only and session.id.value != settings_manager.last_session_id:
            continue

        table.add_row(
            session.id.value,
            session.video_owner,
            str(session.video_date),
            str(session.video_duration),
            session.video_title,
            session.video_description,
            ",".join(session.video_tags),
            str(session.video_genre),
            session.video_copyright,
            session.video_credits.strip(),
        )
    console.print(table)


@app.command(
    name="hashtags",
    help="[purple]Generate[/purple] [bold cyan]beautiful[/bold cyan] video hashtags from comma separated keywords. :hash:",
    rich_help_panel="Video: Information",
)
def hashtags(
    keywords: Annotated[
        str,
        typer.Argument(
            ...,
            help="Specify the [italic]comma separated[/italic] [purple]keywords[/purple] to generate hashtags from. :hash:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ],
):
    upload_api = UploadAPI(verbose=is_verbose)
    hashtags = upload_api.generate_hashtags(keywords.split(","))
    typer.echo(f'\n{" ".join(hashtags)}')


@app.command(
    name="show, play, preview",
    help="[purple]Show[/purple] the [bold cyan]beautiful[/bold cyan] video. :tv:",
    rich_help_panel="Video: Preview",
)
def show(
    session_id: Annotated[
        Optional[str],
        typer.Option(
            ...,
            "--session-id",
            "-sid",
            help="Specify the video's [purple]session ID[/purple] to show the video. :id:",
            show_default=False,
            rich_help_panel="Options: Configuration",
        ),
    ] = None,
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    session_id = session_id or settings_manager.last_session_id
    if not session_id or not settings_manager.session_exists(
        SessionID.explicit(session_id)
    ):
        typer.echo(
            "No session ID found. Please provide a session ID to show the video."
        )
        raise typer.Exit(code=1)
    typer.echo(f"Session UID: {session_id}")
    video_path = settings_manager.get_video_path(session_id)
    os.system(f'start "" "{video_path}"')


@settings_app.command(
    name="show, display",
    help="[purple]Show[/purple] the [bold cyan]beautiful[/bold cyan] app settings. :gear:",
    rich_help_panel="Settings: Information",
)
def show_settings():
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    typer.echo("Settings:\n")
    typer.echo(json.dumps(settings_manager.config, indent=4))


@settings_app.command(
    name="set",
    help="[purple]Set[/purple] the [bold cyan]beautiful[/bold cyan] app settings. :gear:",
    rich_help_panel="Settings: Configuration",
)
def set_settings(
    key: Annotated[
        str,
        typer.Argument(
            ...,
            help="Specify the [purple]key[/purple] to set the value for. :key:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ],
    value: Annotated[
        str,
        typer.Argument(
            ...,
            help="Specify the [purple]value[/purple] to set for the key. :1234:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ],
    encrypt: Annotated[
        bool,
        typer.Option(
            ...,
            "--encrypt",
            "-e",
            help="Specify whether or not to encrypt the value. :lock:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ] = False,
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    settings_manager.set(key=key, value=value, encrypt=encrypt)
    if is_verbose:
        typer.echo(f"Set key '{key}' to value '{value}'.")


@settings_app.command(
    name="delete, remove",
    help="[purple]Delete[/purple] the [bold cyan]beautiful[/bold cyan] app settings. :wastebasket:",
    rich_help_panel="Settings: Configuration",
)
def delete_settings(
    key: Annotated[
        str,
        typer.Argument(
            ...,
            help="Specify the [purple]key[/purple] to delete the value for. :key:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ],
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    settings_manager.delete(key=key)
    if is_verbose:
        typer.echo(f"Deleted key '{key}'.")


@settings_app.command(
    name="get",
    help="[purple]Get[/purple] the [bold cyan]beautiful[/bold cyan] app settings. :gear:",
    rich_help_panel="Settings: Information",
)
def get_settings(
    key: Annotated[
        str,
        typer.Argument(
            ...,
            help="Specify the [purple]key[/purple] to get the value for. :key:",
            show_default=False,
            rich_help_panel="Options: Customization",
        ),
    ],
):
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    value = settings_manager.get(key=key)
    typer.echo(f"Value for key '{key}': {value}")


if __name__ == "__main__":
    app()
