import json
import os
import random as rd
import shutil
import time
from datetime import datetime
from enum import Enum

import captametropolis
import ffmpeg
import moviepy.editor as mp
import pyperclip as pc
import selenium
import selenium.webdriver
from moviepy.audio.fx.volumex import volumex
from moviepy.video.fx.crop import crop
from moviepy.video.fx.resize import resize
from selenium.common.exceptions import NoSuchDriverException
from selenium.webdriver.common.by import By

from config.config import SettingsManager, Singleton


class SubtitleOptions:
    def __init__(
        self,
        font_path: str,
        font_size: int = 100,
        color: str = "white",
        stroke_color: str = "black",
        stroke_width: int = 3,
        rel_height_pos: float = 0.5,
        rel_width: float = 0.6,
        highlight_current_word: bool = True,
        highlight_color: str | list[str] = "yellow",
        shadow_strength: float = 1,
        shadow_blur: float = 0.1,
    ):
        self.fontpath = font_path
        self.fontsize = font_size
        self.color = color
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width
        self.rel_height_pos = rel_height_pos
        self.rel_width = rel_width
        self.highlight_current_word = highlight_current_word
        self.highlight_color = (
            highlight_color
            if isinstance(highlight_color, str)
            else rd.choice(highlight_color or ["yellow"])
        )
        self.shadow_strength = shadow_strength
        self.shadow_blur = shadow_blur


class BackgroundMusic:
    def __init__(
        self,
        audio_path: str | list[str] | None,
        start_sec: float = 0,
        volume_factor: float = 1,
        credits: str | None = None,
    ):
        if not audio_path:
            settings_manager = SettingsManager()
            audio_assets = os.path.join(settings_manager.assets_dir, "project", "music")
            try:
                audio_path = rd.choice(
                    [
                        os.path.join(audio_assets, audio)
                        for audio in os.listdir(audio_assets)
                    ]
                )
            except IndexError:
                raise FileNotFoundError(f"No audio files found in {audio_assets}!")

        if isinstance(audio_path, list):
            try:
                audio_path = rd.choice(audio_path)
            except IndexError:
                raise FileNotFoundError(f"No audio files found in {audio_path}!")

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio path {audio_path} does not exist!")

        self.audio_path = audio_path
        self.start_sec = start_sec
        self.clip = mp.AudioFileClip(audio_path)
        self.clip = self.clip.set_start(start_sec)
        self.clip = volumex(self.clip, volume_factor)
        self.clip = self.clip.set_duration(self.clip.duration)
        self.credits = credits

    def close(self) -> None:
        try:
            self.clip.close()
        except AttributeError:
            pass


class BensoundBackgroundMusic(BackgroundMusic):
    def __init__(self, track_name: str, start_sec: float = 0, volume_factor: float = 1):
        search_params = "".join([f"&tag[]={key}" for key in track_name.split(" ")])
        url = f"https://www.bensound.com/royalty-free-music?type=free&sort=relevance{search_params}"
        settings_manager = SettingsManager(temp=True)
        self.bensound_dir = os.path.join(settings_manager.build_dir, "bensound")
        os.makedirs(self.bensound_dir, exist_ok=True)

        try:
            options = selenium.webdriver.ChromeOptions()
            options.add_argument("--headless")
            options.add_experimental_option(
                "prefs",
                {
                    "download.default_directory": self.bensound_dir,
                },
            )
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            options.add_argument("--disable-search-engine-choice-screen")
            driver = selenium.webdriver.Chrome(options=options)
        except NoSuchDriverException as e:
            print("Please install the Chrome WebDriver to use Bensound!")
            raise e

        driver.get(url)
        driver.find_element(
            By.XPATH, "/html/body/div[5]/main/div[3]/div[4]/div[1]/button"
        ).click()
        driver.implicitly_wait(1)
        driver.find_element(
            By.XPATH, "/html/body/div[6]/div[2]/div/div[3]/div[3]/button"
        ).click()
        driver.find_element(
            By.XPATH,
            "/html/body/div[6]/div[2]/div/div[4]/div[2]/div[2]/div/div[6]/div[2]/div[3]/img",
        ).click()
        credit = pc.paste()

        while not os.listdir(self.bensound_dir):
            time.sleep(1)

        driver.quit()
        file = sorted(
            [
                os.path.join(self.bensound_dir, file)
                for file in os.listdir(self.bensound_dir)
                if file.endswith(".mp3")
            ],
            key=os.path.getctime,
        )[-1]

        super().__init__(
            audio_path=file,
            start_sec=start_sec,
            volume_factor=volume_factor,
            credits=credit,
        )

    def close(self) -> None:
        super().close()
        shutil.rmtree(self.bensound_dir, ignore_errors=True)


class OverlayType(Enum):
    VIDEO = "video"
    IMAGE = "image"


class Overlay:
    def __init__(
        self,
        overlay_path: str,
        start_sec: float,
        rel_position: tuple[float | str, float | str] = ("center", "center"),
        size: tuple[int, int] | float | None = None,
        crop_: tuple[int, int, int, int] = (0, 0, 0, 0),
        is_transparent: bool = False,
        volume_factor: float = 1,
    ):
        if not os.path.exists(overlay_path):
            raise FileNotFoundError(f"Overlay path {overlay_path} does not exist!")

        self.overlay_path = overlay_path
        self.start_sec = start_sec
        self.rel_position = (
            rel_position[0],
            (
                1 - rel_position[1]
                if isinstance(rel_position[1], float)
                else rel_position[1]
            ),
        )
        self.clip = (
            mp.VideoFileClip(overlay_path, has_mask=is_transparent)
            if self.overlay_type == OverlayType.VIDEO
            else mp.ImageClip(overlay_path, transparent=is_transparent)
        )
        self.size = size if size else (self.clip.w, self.clip.h)

        if self.overlay_type == OverlayType.VIDEO:
            audio = mp.AudioFileClip(overlay_path)
            audio = volumex(audio, volume_factor)
            self.clip = self.clip.set_audio(audio)
            self.clip = self.clip.set_duration(audio.duration)
        else:
            self.clip = self.clip.set_duration(self.clip.duration)

        self.clip = self.clip.set_position(self.rel_position, relative=True)
        self.clip = self.clip.set_start(start_sec)
        self.clip = resize(self.clip, self.size)

        if crop:
            self.clip = crop(self.clip, *crop_)

    def close(self) -> None:
        try:
            self.clip.close()
        except AttributeError:
            pass

    @property
    def overlay_type(self) -> OverlayType:
        return (
            OverlayType.VIDEO
            if any(
                overlay_type.value in self.overlay_path for overlay_type in VideoType
            )
            else OverlayType.IMAGE
        )


class VideoType(Enum):
    MP4 = "mp4"
    WEBM = "webm"
    GIF = "gif"
    OGG = "ogg"
    FLV = "flv"
    AVI = "avi"
    MOV = "mov"
    WMV = "wmv"
    MKV = "mkv"
    M4V = "m4v"
    TS = "ts"
    MPG = "mpg"
    MXF = "mxf"


class VideoCodec(Enum):
    LIBX264 = "libx264"
    MPEG4 = "mpeg4"
    RAWVIDEO = "rawvideo"
    PNG = "png"
    LIBVORBIS = "libvorbis"
    LIBVPX = "libvpx"


class AudioCodec(Enum):
    MP3 = "libmp3lame"
    OGG = "libvorbis"
    M4A = "libfdk_aac"
    WAV_16 = "pcm_s16le"
    WAV_32 = "pcm_s32le"


class AudioBitrate(Enum):
    B_32K = "32k"
    B_64K = "64k"
    B_128K = "128k"
    B_192K = "192k"
    B_256K = "256k"
    B_320K = "320k"


@Singleton
class MoviepyAPI:
    def __init__(self, verbose: bool = False) -> None:
        self.__verbose__ = verbose
        self.__settings_manager__ = SettingsManager()
        os.makedirs(self.build_dir, exist_ok=True)

    @property
    def build_dir(self) -> str:
        return os.path.join(self.__settings_manager__.build_dir, "video")

    @property
    def output_dir(self) -> str:
        return self.__settings_manager__.output_dir

    def inject_metadata(
        self,
        video_path: str,
        metadata: dict[str, str | list[str]],
        verbose: bool = False,
    ) -> None:
        metadata = {
            f"metadata:g:{index}": f"{key}={value if isinstance(value, str) else ','.join(value)}"
            for index, (key, value) in enumerate(metadata.items())
        }
        if verbose:
            print(f"Metadata: {metadata}")
            print("Injecting metadata...")

        temp_video_path = os.path.join(self.build_dir, "temp_video.mp4")
        ffmpeg.input(video_path).output(
            temp_video_path,
            loglevel="info" if verbose else "quiet",
            map=0,
            c="copy",
            **metadata,
        ).run(overwrite_output=True)

        p = ffmpeg.probe(temp_video_path)
        if not p.get("format", {}).get("tags", {}).get("description"):
            raise ValueError("Metadata not injected!")

        shutil.move(temp_video_path, video_path)
        if verbose:
            print("Metadata injected!")

    def get_video_path(self, session_id: str) -> str:
        def file_filter(file) -> bool:
            if not os.path.isfile(file) or not file.endswith(".mp4"):
                return False

            probe = ffmpeg.probe(file)
            if not probe:
                return False

            return probe["format"]["tags"]["episode_id"] == session_id

        try:
            file = tuple(
                filter(
                    lambda file: file_filter(
                        os.path.join(self.__settings_manager__.output_dir, file)
                    ),
                    os.listdir(self.__settings_manager__.output_dir),
                )
            )[0]
        except IndexError:
            raise FileNotFoundError(f"No video found for session {session_id}!")
        return os.path.join(
            self.__settings_manager__.output_dir,
            file,
        )

    def get_metadata(self, video_path: str, verbose: bool = False) -> dict[str, str]:
        if verbose:
            print("Getting metadata...")

        p = ffmpeg.probe(video_path)
        metadata = p.get("format", {}).get("tags", {})

        if not metadata:
            raise ValueError("Metadata not found!")

        if verbose:
            print(f"Metadata: {json.dumps(metadata, indent=4)}")

        return json.loads(json.dumps(metadata))

    def generate_video(
        self,
        audio_paths: list[str],
        picture_paths: list[str],
        metadata: dict[str, str | list[str]],
        overlays: list[Overlay] = [],
        background_music: BackgroundMusic | None = None,
        resolution: tuple[int, int] = (1080, 1920),
        max_length: int | None = None,
        crossfade_duration: float = 1,
        output_fileext: VideoType = VideoType.MP4,
        video_codec: VideoCodec = VideoCodec.LIBX264,
        audio_codec: AudioCodec = AudioCodec.MP3,
        audio_bitrate: AudioBitrate = AudioBitrate.B_128K,
        subtitle_options: SubtitleOptions | None = None,
        fps: int = 30,
        num_threads: int = 4,
    ) -> str:
        if self.__verbose__:
            print("Generating video...")

        def picture_motion(
            picture: mp.ImageClip,
            duration: float,
            speed: float = 10,
            zoom_enabled: bool = False,
            zoom_speed: float = 0,
        ) -> mp.ImageClip:
            MIN_ZOOM = max(
                1.35,
                max(resolution[0] / picture.size[0], resolution[1] / picture.size[1]),
            )
            MAX_ZOOM = 1.75
            zoom_factor = rd.uniform(MIN_ZOOM, MAX_ZOOM) if zoom_enabled else 1
            zoom_speed = abs(zoom_speed)
            zoom_speed = (
                -zoom_speed
                if zoom_factor >= ((MAX_ZOOM + MIN_ZOOM) / 2)
                else zoom_speed
            )

            dx = rd.uniform(-1, 1)
            dy = rd.uniform(-1, 1)

            norm = (dx**2 + dy**2) ** 0.5
            dx /= norm
            dy /= norm

            def direction(t):
                if zoom_speed < 0:
                    return (0, 0)

                x_movement = dx * speed * t
                y_movement = dy * speed * t
                return (x_movement, y_movement)

            def zoom(t):
                if zoom_enabled:
                    cal_zoom = zoom_factor + zoom_speed * t
                    return min(max(MIN_ZOOM, cal_zoom), MAX_ZOOM)
                else:
                    return 1

            def position(t):
                current_zoom = zoom(t)
                picture_size = picture.size
                zoomed_width = picture_size[0] * current_zoom
                zoomed_height = picture_size[1] * current_zoom

                x_movement, y_movement = direction(t)

                # Calculate limits to prevent going beyond the frame
                x_min = min(0, resolution[0] - zoomed_width)
                x_max = 0
                y_min = min(0, resolution[1] - zoomed_height)
                y_max = 0

                # Ensure position stays within bounds
                x_pos = max(x_min, min(x_max, -x_movement))
                y_pos = max(y_min, min(y_max, -y_movement))

                return (x_pos, y_pos)

            picture = resize(picture, zoom)
            return picture.set_position(position).set_duration(duration)

        clips = []
        total_duration = 0
        for audio_path, picture_path in zip(audio_paths, picture_paths):
            audio = mp.AudioFileClip(audio_path)
            picture = mp.ImageClip(picture_path)
            picture = picture_motion(
                picture,
                audio.duration,
                speed=rd.uniform(10, 15),
                zoom_enabled=True,
                zoom_speed=rd.uniform(0.01, 0.03),
            )
            total_duration += audio.duration
            if total_duration > max_length:
                break
            clip = mp.CompositeVideoClip([picture.set_audio(audio)])
            clips.append(clip)

        if not clips:
            raise ValueError("No clips generated!")

        video = mp.concatenate_videoclips(
            [
                clip if index == 0 else clip.crossfadein(crossfade_duration)
                for index, clip in enumerate(clips)
            ],
            method="compose",
        )

        if max_length and video.duration > max_length:
            video = video.subclip(0, max_length)
        if video.w >= resolution[0] or video.h >= resolution[1]:
            video = crop(
                video,
                width=resolution[0],
                height=resolution[1],
                x_center=video.w / 2,
                y_center=video.h / 2,
            )
        if self.__verbose__:
            print("Video generated! Saving video...")
        os.makedirs(self.output_dir, exist_ok=True)
        file_title = metadata["title"].translate(str.maketrans("", "", '/\\:*?"<>|'))  # type: ignore
        temp_video_path = os.path.join(
            self.build_dir, f"{file_title}.{output_fileext.value}"
        )
        final_video_path = os.path.join(
            self.output_dir, f"{file_title}.{output_fileext.value}"
        )
        temp_audiofileext = (
            audio_codec.name.lower()
            if audio_codec not in [AudioCodec.WAV_16, AudioCodec.WAV_32]
            else "wav"
        )
        video.write_videofile(
            temp_video_path if subtitle_options is not None else final_video_path,
            codec=video_codec.value,
            audio_codec=audio_codec.value,
            audio_bitrate=audio_bitrate.value,
            verbose=self.__verbose__,
            logger=None if not self.__verbose__ else "bar",
            fps=fps,
            temp_audiofile=os.path.join(
                self.build_dir, f"temp_audio.{temp_audiofileext}"
            ),
            threads=num_threads,
        )

        if subtitle_options is not None:
            if self.__verbose__:
                print("Adding captions to video...")
            captametropolis.add_captions(
                temp_video_path,
                final_video_path,
                font_path=subtitle_options.fontpath,
                font_size=subtitle_options.fontsize,
                font_color=subtitle_options.color,
                stroke_color=subtitle_options.stroke_color,
                stroke_width=subtitle_options.stroke_width,
                rel_height_pos=subtitle_options.rel_height_pos,
                rel_width=subtitle_options.rel_width,
                line_count=1,
                highlight_current_word=subtitle_options.highlight_current_word,
                highlight_color=subtitle_options.highlight_color,
                shadow_strength=subtitle_options.shadow_strength,
                shadow_blur=subtitle_options.shadow_blur,
                temp_audiofile=os.path.join(
                    self.build_dir, f"temp_audio.{temp_audiofileext}"
                ),
                verbose=self.__verbose__,
            )

        final_video = mp.VideoFileClip(final_video_path).set_fps(fps)
        overlay_clips = [overlay.clip.set_fps(fps) for overlay in overlays]
        final_video = mp.CompositeVideoClip([final_video] + overlay_clips).set_duration(
            final_video.duration
        )
        background_music_clip = (
            [background_music.clip.subclip(0, final_video.duration)]
            if background_music
            else []
        )
        final_audio = mp.CompositeAudioClip([final_video.audio] + background_music_clip)
        final_video = final_video.set_audio(final_audio)
        final_video.write_videofile(
            temp_video_path,
            codec=video_codec.value,
            audio_codec=audio_codec.value,
            audio_bitrate=audio_bitrate.value,
            verbose=self.__verbose__,
            logger=None if not self.__verbose__ else "bar",
            fps=fps,
            temp_audiofile=os.path.join(
                self.build_dir, f"temp_audio.{temp_audiofileext}"
            ),
            threads=num_threads,
        )
        shutil.move(temp_video_path, final_video_path)

        final_video.close()
        background_music.close() if background_music else None
        for overlay in overlays:
            overlay.close()

        metadata["artist"] = metadata.get("artist", "Unknown")
        metadata["copyright"] = (
            f"Copyright © {datetime.now().year} {metadata['artist']}"
        )
        metadata["date"] = str(datetime.now().year)
        metadata["episode_id"] = SettingsManager().session_id
        if background_music and background_music.credits:
            metadata["album"] = background_music.credits
        self.inject_metadata(final_video_path, metadata, verbose=self.__verbose__)

        if self.__verbose__:
            print(
                f"{'Captions added! ' if subtitle_options is not None else ''}Final video saved as: {final_video_path}"
            )

        return final_video_path
