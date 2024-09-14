import json
import os
import random as rd
import sys
import traceback
from pathlib import Path
from typing import Annotated, Optional

import typer

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
    name="generate, build, new",
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
    g4f_api = G4FAPI(verbose=is_verbose)
    elevenlabs_api = ElevenLabsAPI(verbose=is_verbose)
    fooocus_api = FooocusAPI(verbose=is_verbose)
    prompt_manager = PromptManager()
    moviepy_api = MoviepyAPI(verbose=is_verbose)

    video_text_paragraphs = g4f_api.get_response(
        Message(MessageSender.USER, prompt_manager.get_prompt("video_idea")),
        save_response="voiceover.txt",
    ).content  # type: ignore
    video_text_paragraphs = tuple(
        map(str.strip, [pg for pg in video_text_paragraphs.split("\n") if pg])
    )

    for index, paragraph in enumerate(video_text_paragraphs):
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
        fooocus_api.generate_picture(
            prompt,
            image_type=ImageType.JPEG,
            resolution=Resolution.RES_768x1344,
            model=Model("juggernautXL_v8Rundiffusion"),
            lora_1=LoRa("sd_xl_offset_example-lora_1.0", weight=0.1),
            upscale_mode=UpscaleMode.X_1_5,
            save_picture=str(index),
        )

    video_info = g4f_api.get_response(
        Message(MessageSender.USER, prompt_manager.get_prompt("video_info")),
        save_response=f"video_info.txt",
    ).content  # type: ignore
    video_title, video_description, video_hashtags = tuple(
        map(
            lambda string: (
                tuple(map(str.strip, string.split(",")))
                if "#" in string
                else string.strip()
            ),
            [info for info in video_info.split("\n") if info],
        )
    )

    background_musics = [
        BackgroundMusic(
            r"D:\Hobbys\YouTube\CurioBurstz\Assets\background_music_1.mp3",
            volume_factor=0.1,
            credits="\nSong: Sappheiros - Lights (Vlog No Copyright Music)\nMusic promoted by Vlog No Copyright Music.\nVideo Link: https://youtu.be/kzeQK45StRo\n",
        ),
        BackgroundMusic(
            r"D:\Hobbys\YouTube\CurioBurstz\Assets\background_music_2.mp3",
            volume_factor=0.1,
            credits="\nSong: Chill Day - LAKEY INSPIRED\nLink: https://soundcloud.com/lakeyinspired/chill-day\nLicense: Creative Commons Attribution-ShareAlike 3.0\nLicense Link: https://creativecommons.org/licenses/by-sa/3.0/\n",
        ),
        BensoundBackgroundMusic(
            "the lounge",
            volume_factor=0.2,
        ),
    ]
    background_music = rd.choice(background_musics)
    moviepy_api.generate_video(
        audio_paths=[
            os.path.join(elevenlabs_api.output_dir, audio)
            for audio in os.listdir(elevenlabs_api.output_dir)
        ],
        picture_paths=[
            os.path.join(fooocus_api.output_dir, picture)
            for picture in os.listdir(fooocus_api.output_dir)
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
    past_topics = settings_manager.get("past_topics", []) or []
    if video_title not in past_topics:  # type: ignore
        past_topics.append(video_title)  # type: ignore
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
    moviepy_api = MoviepyAPI(verbose=is_verbose)

    with open(
        os.path.join(settings_manager.build_dir, "responses", "video_info.txt"),
        "r",
        encoding="utf-8",
    ) as f:
        video_info = [line for line in f.readlines() if line.strip()]
    video_title, video_description, video_hashtags = tuple(
        map(
            lambda string: (
                tuple(map(str.strip, string.split(",")))
                if "#" in string
                else string.strip()
            ),
            video_info,
        )
    )

    background_musics = [
        BackgroundMusic(
            r"D:\Hobbys\YouTube\CurioBurstz\Assets\background_music_1.mp3",
            volume_factor=0.1,
            credits="\nSong: Sappheiros - Lights (Vlog No Copyright Music)\nMusic promoted by Vlog No Copyright Music.\nVideo Link: https://youtu.be/kzeQK45StRo\n",
        ),
        BackgroundMusic(
            r"D:\Hobbys\YouTube\CurioBurstz\Assets\background_music_2.mp3",
            volume_factor=0.1,
            credits="\nSong: Chill Day - LAKEY INSPIRED\nLink: https://soundcloud.com/lakeyinspired/chill-day\nLicense: Creative Commons Attribution-ShareAlike 3.0\nLicense Link: https://creativecommons.org/licenses/by-sa/3.0/\n",
        ),
        BensoundBackgroundMusic(
            "the lounge",
            volume_factor=0.3,
        ),
    ]
    background_music = rd.choice(background_musics)
    moviepy_api.generate_video(
        audio_paths=[
            os.path.join(elevenlabs_api.output_dir, audio)
            for audio in os.listdir(elevenlabs_api.output_dir)
        ],
        picture_paths=[
            os.path.join(fooocus_api.output_dir, picture)
            for picture in os.listdir(fooocus_api.output_dir)
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
    past_topics = settings_manager.get("past_topics", []) or []
    if video_title not in past_topics:  # type: ignore
        past_topics.append(video_title)  # type: ignore
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
    rich_help_panel="Video: Configuration",
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
    moviepy_api = MoviepyAPI(verbose=is_verbose)
    video_path = moviepy_api.get_video_path(session_id)
    metadata = moviepy_api.get_metadata(video_path)
    typer.echo(json.dumps(metadata, indent=4))


@app.command(
    name="list, show",
    help="[purple]List[/purple] the [bold cyan]beautiful[/bold cyan] video topics. :scroll:",
    rich_help_panel="Video: Management",
)
def list_topics():
    settings_manager = SettingsManager(session_id=SessionID.TEMP, verbose=is_verbose)
    past_topics = settings_manager.get("past_topics", []) or []
    for index, topic in enumerate(past_topics):
        typer.echo(f"{index + 1}. {topic}")


@app.command(
    name="hashtags",
    help="[purple]Generate[/purple] [bold cyan]beautiful[/bold cyan] video hashtags from comma separated keywords. :hash:",
    rich_help_panel="Video: Configuration",
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
    hashtags = tuple(map(lambda keyword: f"#{keyword}", keywords.split(",")))
    typer.echo(f'\n{" ".join(hashtags)}')


if __name__ == "__main__":
    app()
