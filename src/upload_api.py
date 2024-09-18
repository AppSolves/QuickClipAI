import os
import random
import random as rd
import time
from pathlib import Path

import ffmpeg
import google.auth.transport.requests
import httplib2
import pyperclip as pc
import selenium.webdriver
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from selenium.common.exceptions import (ElementNotInteractableException,
                                        NoSuchDriverException,
                                        NoSuchElementException)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config.config import SessionID, SettingsManager, Singleton, classproperty

RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
MAX_RETRIES = 10
httplib2.RETRIES = 1

@Singleton
class UploadAPI:
    def __init__(self, verbose: bool = False):
        self.__verbose__ = verbose
        self.__settings_manager__ = SettingsManager(session_id=SessionID.NONE)

    @classproperty
    def authenticated_service(cls):
        SCOPES = [
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.upload",
        ]
        settings_manager = SettingsManager(session_id=SessionID.NONE)

        credentials = None
        if settings_manager.get("youtube_auth_session", None):
            credentials = Credentials.from_authorized_user_info(
                settings_manager.get("youtube_auth_session", None)
            )

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(google.auth.transport.requests.Request())
                except Exception as e:
                    print(f"Error refreshing credentials: {e}")
                    print("Reauthenticating...\n")
                    youtube_credentials = settings_manager.get("publisher", {}).get("youtube", None)  # type: ignore
                    if not youtube_credentials:
                        raise Exception("No YouTube credentials found.")
                    flow = InstalledAppFlow.from_client_config(
                        youtube_credentials, SCOPES
                    )
                    credentials = flow.run_local_server()
            else:
                youtube_credentials = settings_manager.get("publisher", {}).get("youtube", None)  # type: ignore
                if not youtube_credentials:
                    raise Exception("No YouTube credentials found.")
                flow = InstalledAppFlow.from_client_config(
                    youtube_credentials, SCOPES
                )
                credentials = flow.run_local_server()
        
        settings_manager.set("youtube_auth_session", credentials.to_json(), encrypt=True)
        return build("youtube", "v3", credentials=credentials)

    def upload(self, session_id: str, youtube: bool, instagram: bool, tiktok: bool, thumbnail_path: Path | None = None) -> bool:
        if self.__verbose__:
            print(
                f"Uploading video to {'YouTube, ' if youtube else ''}{'Instagram, ' if instagram else ''}{'TikTok' if tiktok else ''}.".strip(", .")
            )

        def file_filter(file) -> bool:
            if not os.path.isfile(file) or not file.endswith(".mp4"):
                return False

            probe = ffmpeg.probe(file)
            if not probe:
                return False

            return probe["format"]["tags"]["episode_id"] == session_id

        file_to_upload = os.path.join(
            self.__settings_manager__.output_dir,
            tuple(
                filter(
                    lambda file: file_filter(
                        os.path.join(self.__settings_manager__.output_dir, file)
                    ),
                    os.listdir(self.__settings_manager__.output_dir),
                )
            )[0],
        )
        info = ffmpeg.probe(file_to_upload)["format"]["tags"]
        error: bool = False

        if youtube:
            video_id = None
            def resumable_upload(insert_request):
                response = None
                error = None
                retry = 0
                while response is None:
                    try:
                        if self.__verbose__:
                            print("Uploading file to YouTube...")
                        _, response = insert_request.next_chunk()
                        if response is not None:
                            if "id" in response and self.__verbose__:
                                print(
                                    "Video id '%s' was successfully uploaded."
                                    % response["id"]
                                )
                                video_id = response["id"]
                            else:
                                if self.__verbose__:
                                    print("The upload failed with an unexpected response.")
                                return False
                    except HttpError as e:
                        if e.resp.status in RETRIABLE_STATUS_CODES:
                            error = "A retriable HTTP error %d occurred:\n%s" % (
                                e.resp.status,
                                e.content,
                            )
                        else:
                            raise
                    except Exception as e:
                        error = "A retriable error occurred: %s" % e

                    if error is not None:
                        if self.__verbose__:
                            print(error)
                        retry += 1
                        if retry > MAX_RETRIES:
                            if self.__verbose__:
                                print("No longer attempting to retry.")
                            return False

                        max_sleep = 2**retry
                        sleep_seconds = random.random() * max_sleep
                        if self.__verbose__:
                            print(
                                "Sleeping %f seconds and then retrying..."
                                % sleep_seconds
                            )
                        time.sleep(sleep_seconds)

                youtube = self.authenticated_service
                try:
                    initialize_upload(youtube)
                except HttpError as e:
                    if self.__verbose__:
                        print(
                            "An HTTP error %d occurred:\n%s"
                            % (e.resp.status, e.content)
                        )

            def initialize_upload(youtube):

                tags = None
                if info.get("comment"):
                    tags = info.get("comment").replace("#", "").split(",")

                body = dict(
                    snippet=dict(
                        title=info.get("title"),
                        description=f"{info.get("description")}\n\n{info.get('album')}",
                        tags=tags,
                        categoryId=info.get("genre"),
                    ),
                    status=dict(privacyStatus="public"),
                )

                # Call the API's videos.insert method to create and upload the video.
                insert_request = youtube.videos().insert(
                    part=",".join(body.keys()),
                    body=body,
                    media_body=MediaFileUpload(
                        file_to_upload,
                         chunksize=-1, resumable=True
                    ),
                )

                resumable_upload(insert_request)

            def insert_thumbnail():
                nonlocal thumbnail_path
                if not thumbnail_path:
                    default_thumbnail_path = os.path.join(
                        self.__settings_manager__.build_dir_for_session(session_id),
                        "pictures",
                    )
                    available_thumbnails = list(
                        filter(
                            lambda file: file.endswith(".jpeg") or file.endswith(".png"),
                            os.listdir(default_thumbnail_path),
                        )
                    )
                    default_thumbnail_path = os.path.join(
                        default_thumbnail_path,
                        rd.choice(available_thumbnails),
                    ) if available_thumbnails else None
                    thumbnail_path = Path(default_thumbnail_path) if default_thumbnail_path else None

                youtube = self.authenticated_service
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail_path)),
                ).execute()

            try:
                youtube = self.authenticated_service
                initialize_upload(youtube)
                insert_thumbnail() if video_id else None
                if self.__verbose__:
                    print("Video uploaded to YouTube.")
            except Exception as e:
                print(e)
                error = True

        if instagram:
            try:
                if not thumbnail_path:
                    default_thumbnail_path = os.path.join(
                        self.__settings_manager__.build_dir_for_session(session_id),
                        "pictures",
                    )
                    available_thumbnails = list(
                        filter(
                            lambda file: file.endswith(".jpeg") or file.endswith(".png"),
                            os.listdir(default_thumbnail_path),
                        )
                    )
                    default_thumbnail_path = os.path.join(
                        default_thumbnail_path,
                        rd.choice(available_thumbnails),
                    ) if available_thumbnails else None
                    thumbnail_path = Path(default_thumbnail_path) if default_thumbnail_path else None

                options = selenium.webdriver.ChromeOptions()
                options.add_argument("--log-level=3")
                options.add_argument(f"user-data-dir={self.__settings_manager__.chrome_profile_dir}")
                options.add_experimental_option("excludeSwitches", ["enable-logging"])
                options.add_argument("--disable-search-engine-choice-screen")
                driver = selenium.webdriver.Chrome(options=options)
                driver.maximize_window()
                errors = [NoSuchElementException, ElementNotInteractableException]
                wait = WebDriverWait(driver, timeout=5, poll_frequency=.2, ignored_exceptions=errors)
            except NoSuchDriverException as e:
                print("Please install the Chrome WebDriver to upload to Instagram.")
                raise e
            
            def click_element(selector):
                wait.until(EC.presence_of_element_located(selector))
                driver.find_element(*selector).click()

            def send_keys(selector, keys):
                wait.until(EC.presence_of_element_located(selector))
                driver.find_element(*selector).send_keys(keys)
            
            try:
                driver.get("https://www.instagram.com")
                click_element((By.XPATH, "/html/body/div[1]/div/div/div[2]/div/div/div[1]/div[1]/div[2]/div/div/div/div/div[2]/div[7]/div/span/div/a/div/div[2]"))
                click_element((By.XPATH, "/html/body/div[1]/div/div/div[2]/div/div/div[1]/div[1]/div[2]/div/div/div/div/div[2]/div[7]/div/span/div/div/div/div[1]/a[1]/div[1]/div/div/div[1]/div/div/span/span"))
                send_keys((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div.xdl72j9.x1iyjqo2.xs83m0k.x15wfb8v.x3aagtl.xqbdwvv.x6ql1ns.x1cwzgcd > div.x6s0dn4.x78zum5.x5yr21d.xl56j7k.x1n2onr6.xh8yej3 > form > input"), file_to_upload)
                click_element((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div.xdl72j9.x1iyjqo2.xs83m0k.x15wfb8v.x3aagtl.xqbdwvv.x6ql1ns.x1cwzgcd > div.x6s0dn4.x78zum5.x5yr21d.xl56j7k.x1n2onr6.xh8yej3 > div > div > div > div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh.x1xmf6yo.x1emribx.x1e56ztr.x1i64zmx.x10l6tqk.x1ey2m1c.x17qophe.x1plvlek.xryxfnj.x1c4vz4f.x2lah0s.xdt5ytf.xqjyukv.x1qjc9v5.x1oa3qoh.x1nhvcw1 > div > div:nth-child(2) > div > button"))
                click_element((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div.xdl72j9.x1iyjqo2.xs83m0k.x15wfb8v.x3aagtl.xqbdwvv.x6ql1ns.x1cwzgcd > div.x6s0dn4.x78zum5.x5yr21d.xl56j7k.x1n2onr6.xh8yej3 > div > div > div > div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh.x1xmf6yo.x1emribx.x1e56ztr.x1i64zmx.x10l6tqk.x1ey2m1c.x17qophe.x1plvlek.xryxfnj.x1c4vz4f.x2lah0s.xdt5ytf.xqjyukv.x1qjc9v5.x1oa3qoh.x1nhvcw1 > div > div:nth-child(2) > div > button"))
                click_element((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div.xdl72j9.x1iyjqo2.xs83m0k.x15wfb8v.x3aagtl.xqbdwvv.x6ql1ns.x1cwzgcd > div.x6s0dn4.x78zum5.x5yr21d.xl56j7k.x1n2onr6.xh8yej3 > div > div > div > div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh.x1xmf6yo.x1emribx.x1e56ztr.x1i64zmx.x10l6tqk.x1ey2m1c.x17qophe.x1plvlek.xryxfnj.x1c4vz4f.x2lah0s.xdt5ytf.xqjyukv.x1qjc9v5.x1oa3qoh.x1nhvcw1 > div > div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh.x1y1aw1k.x1sxyh0.xwib8y2.xurb0ha.x1n2onr6.x1plvlek.xryxfnj.x1c4vz4f.x2lah0s.xdt5ytf.xqjyukv.x1qjc9v5.x1oa3qoh.x1nhvcw1 > div > div:nth-child(1) > div > div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh.x1n2onr6.x1plvlek.xryxfnj.x1iyjqo2.x2lwn1j.xeuugli.xdt5ytf.xqjyukv.x1cy8zhl.x1oa3qoh.x1nhvcw1 > span"))
                click_element((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div._ap97 > div > div > div > div._ac7b._ac7d > div > div"))
                send_keys((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div.x15wfb8v.x3aagtl.x6ql1ns.x78zum5.xdl72j9.x1iyjqo2.xs83m0k.x13vbajr.x1ue5u6n > div.xhk4uv.x26u7qi.xy80clv.x9f619.x78zum5.x1n2onr6.x1f4304s > div > div > div > div > div:nth-child(1) > div.x1qjc9v5.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x78zum5.xdt5ytf.x2lah0s.xln7xf2.xk390pu.x1hmvnq2.x11i5rnm.x1u7kmwd.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x1n2onr6.x11njtxf > div > div > form > input"), str(thumbnail_path)) if thumbnail_path else None
                click_element((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div._ap97 > div > div > div > div._ac7b._ac7d > div > div"))

                instagram_description = f"{info.get('title')}\n\n{info.get('description')}\n\n{info.get('album')}"
                description_elem = driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true']")
                description_elem.click()
                pc.copy(instagram_description)
                description_elem.send_keys(Keys.CONTROL, "v")

                click_element((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div._ap97 > div > div > div > div._ac7b._ac7d > div > div"))
                try:
                    wait = WebDriverWait(driver, timeout=30, poll_frequency=.2, ignored_exceptions=errors)
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div._ap97 > div > div > div > div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh.x10l6tqk.x1plvlek.xryxfnj.x1c4vz4f.x2lah0s.xdt5ytf.xqjyukv.x6s0dn4.x1oa3qoh.xl56j7k > div > div")))
                    wait.until_not(EC.presence_of_element_located((By.CSS_SELECTOR, "body > div.x1n2onr6.xzkaem6 > div.x9f619.x1n2onr6.x1ja2u2z > div > div.x1uvtmcs.x4k7w5x.x1h91t0o.x1beo9mf.xaigb6o.x12ejxvf.x3igimt.xarpa2k.xedcshv.x1lytzrv.x1t2pt76.x7ja8zs.x1n2onr6.x1qrby5j.x1jfb8zj > div > div > div > div > div > div > div > div._ap97 > div > div > div > div.x9f619.xjbqb8w.x78zum5.x168nmei.x13lgxp2.x5pf9jr.xo71vjh.x10l6tqk.x1plvlek.xryxfnj.x1c4vz4f.x2lah0s.xdt5ytf.xqjyukv.x6s0dn4.x1oa3qoh.xl56j7k > div > div")))
                except Exception as e:
                    print("Uploaded to Instagram.")
                    driver.quit()
            except Exception as e:
                print(e)
                error = True

        if tiktok:
            pass

        if self.__verbose__:
            print("Upload complete.") if not error else print("Upload failed.")

        return not error
