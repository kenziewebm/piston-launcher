import os
import json
import toga
import hashlib
import requests
import threading
import lzma as l # TODO: the game manifest has {"lzma":{"url":"whatever"}} for compressed files, have to either fix that or do this
import subprocess
from datetime import datetime
from toga.style.pack import * 

class PistonLauncher(toga.App):
    async def install_wrapper(self, widget=None):
        """
        Wrapper for install_game()
        """

        # TODO: make not hardcoded. will be hard since the random string at
        # the beginning of each file is the hash of that file, and i haven't
        # found a manifest 1 level higher than this

        response = requests.get("https://piston-meta.mojang.com/v1/products/dungeons/f4c685912beb55eb2d5c9e0713fe1195164bba27/windows-x64.json")

        try:
            game_manifest = response.json()["dungeons"][0]["manifest"]["url"]
            game_version = response.json()["dungeons"][0]["version"]["name"]
        except Exception:
            dialog = toga.ErrorDialog(title="Fatal Error!", message=f"Mojang has updated the game after {datetime.now().year - 2022} years!\nI haven't expected this, so the launcher doesn't support this yet.\nMake an issue on https://github.com/kenziewebm/piston-launcher!")
            await self.dialog(dialog)
            self.app.exit()

        game_dir = self.settings.get("game_dir")

        if not os.path.exists(game_dir):
            os.mkdir(game_dir)

        with open(os.path.join(game_dir, ".version"), 'w') as f:
            f.write(game_version)

        response = requests.get(game_manifest)
        self.loop.call_soon_threadsafe(self.set_max_progress, (len(response.json()["files"].keys())))

        install_thread = threading.Thread(target=self.install_game, args=(response.json()["files"], game_dir))
        self.loop.call_soon_threadsafe(self.set_dlbox_visibility, True)
        install_thread.start()
        self.set_button_state(False)
        self.set_button_text("Installing...")
        
    def launch_game(self, game_exec):
        """
        Launch Minecraft: Dungeons
        :param game_exec: Path to game executable.
        """
        subprocess.Popen([game_exec])

    def launch_wrapper(self):
        """
        Wrapper for launch_game()
        :param game_dir: Directory path to the game files.
        """
        game_dir = self.settings.get("game_dir")
        game_exec = os.path.join(game_dir, "Dungeons.exe")
        game_thread = threading.Thread(target=self.launch_game, args=(game_exec,), daemon=True)
        game_thread.start()
        

    def install_game(self, game_manifest, game_dir):
        """
        Proceed with installation of Minecraft Dungeons
        :param game_dir: Directory path to install the game to.
        """

        self.process_json(game_manifest, game_dir)
        
        self.loop.call_soon_threadsafe(self.set_button_state, True)
        self.loop.call_soon_threadsafe(self.set_button_text, "Play")
        self.loop.call_soon_threadsafe(self.set_button_action, lambda button: self.launch_wrapper())
        self.loop.call_soon_threadsafe(self.set_dlbox_visibility, False)
        self.loop.call_soon_threadsafe(self.set_game_version, self.game_version)

    def process_json(self, json_data, base_path):
        """
        Process the JSON structure to create directories, download files, and set executables.
        :param json_data: The JSON data to process.
        :param base_path: The base directory to operate in.
        """
        for key, value in json_data.items():
            if isinstance(value, dict):
                item_type = value.get("type")

                if item_type == "directory":
                    dir_path = os.path.join(base_path, key)
                    os.makedirs(dir_path, exist_ok=True)
                    print(f"MKDIR {dir_path}")
                    self.loop.call_soon_threadsafe(self.update_progress)

                    self.process_json(json_data=value, base_path=base_path) # yay, recursion!

                elif item_type == "file":
                    downloads = value.get("downloads", {})
                    lzma = downloads.get("lzma")
                    raw = downloads.get("raw")

                    download_info = lzma if lzma and self.settings["download_raw"] is False else raw
                    if download_info:
                        file_url = download_info.get("url")
                        file_sha1 = download_info.get("sha1")
                        file_path = os.path.join(base_path, key)

                        self.download_file(file_url, file_path)

                        if file_sha1:
                            print(f"SHA1 {file_path} ", end='')
                            if self.verify_sha1(file_path, file_sha1):
                                print(" OK")
                            else:
                                print(" BAD")
                                os.remove(file_path)
                                continue

                        if lzma and self.settings["download_raw"] is False:
                            chunk_size = self.settings.get("lzma_mem_cap")
                            print(f"LZMA {file_path} ", end='')
                            tmp_path = file_path + ".tmp"
                            with l.open(file_path, 'rb') as cf:
                                with open(tmp_path, 'wb') as f:
                                    if chunk_size == 0:
                                        f.write(cf.read())
                                    else:
                                        while True:
                                            chunk = cf.read(1024 * 1024 * chunk_size)
                                            if not chunk:
                                                break
                                            f.write(chunk)
                            os.replace(tmp_path, file_path)
                            print("OK")

                        self.loop.call_soon_threadsafe(self.update_progress)

    # im pretty sure that theres a much smarter way to do this
    # than making 5 billion tiny functions, but i cant come up
    # with anything with anything better. all of these return
    # "True" so that they can work as OnCloseHandler()s for windows

    def update_progress(self):
        self.bar.value += 1
        self.items.text = f"{int(self.bar.value)}/{int(self.bar.max)}"
        return True

    def set_max_progress(self, max):
        self.bar.max = int(max)
        self.bar.value = 0
        return True

    def set_button_text(self, text):
        self.button.text = text
        return True

    def set_button_state(self, state):
        if self.keep_settings_disabled is True:
            return True
        else:
            self.button.enabled = state
            self.settings_button.enabled = state
        return True

    def set_button_action(self, action):
        self.button.on_press = action
        return True

    def set_game_version(self, text):
        self.version_label.text = "Game version: " + text
        return True

    def toggle_settings_state(self, state):
        self.keep_settings_disabled = True if state is False else False
        self.uninstall_game_button.enabled = state
        self.verify_files_button.enabled = state
        self.raw_checkbox.enabled = state
        self.lzma_slider.enabled = state
        self.game_dir_input.enabled = state
        return True


    def set_dlbox_visibility(self, state):
        self.dlbox.style.display = PACK if state is True else NONE
        self.bar.style.display = PACK if state is True else NONE
        self.items.style.display = PACK if state is True else NONE

        self.dlbox.style.visibility = VISIBLE if state is True else HIDDEN
        self.bar.style.visibility = VISIBLE if state is True else HIDDEN
        self.items.style.visibility = VISIBLE if state is True else HIDDEN

    def download_file(self, url, path):
        """
        Download a file from the given URL and save it to the specified path.
        :param url: The URL of the file to download.
        :param path: The local path to save the file.
        """
        print(f"GET {url} ", end='')
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print("OK")

    def verify_sha1(self, file_path, expected_sha1):
        """
        Verify the SHA1 checksum of a file.
        :param file_path: The path to the file to verify.
        :param expected_sha1: The expected SHA1 checksum.
        :return: True if the checksum matches, False otherwise.
        """
        sha1 = hashlib.sha1()
        with open(file_path, "rb") as file:
            while chunk := file.read(8192):
                sha1.update(chunk)
        calculated_sha1 = sha1.hexdigest()
        return expected_sha1 == calculated_sha1
    
    def open_settings_window(self, widget):

        self.set_button_state(False)

        self.settings_window = toga.Window(title="Settings", size=(500, 250), resizable=False, on_close=lambda window: self.set_button_state(True))
        settings_box = toga.Box()

        game_dir_label = toga.Label("Game Directory")
        self.game_dir_input = toga.TextInput(placeholder="Game files path", value=self.settings["game_dir"])

        self.lzma_slider_label = toga.Label("LZMA Memory Cap: " + str(int(self.settings["lzma_mem_cap"]) * 2) + " MB")
        self.lzma_slider = toga.Slider(min=0, max=1024, value=self.settings["lzma_mem_cap"], on_change=self.update_lzma_slider_text, tick_count=9)

        self.raw_checkbox = toga.Switch("Download uncompressed files", on_change=self.toggle_slider, value=self.settings["download_raw"])

        self.verify_files_button = toga.Button("Verify game installation", on_press=self.verify_files_wrapper)
        self.uninstall_game_button = toga.Button("Uninstall game", on_press=self.uninstall_game_wrapper)

        save_button = toga.Button("Save", on_press=self.save_settings)

        settings_box.add(game_dir_label)
        settings_box.add(self.game_dir_input)
        settings_box.add(self.lzma_slider_label)
        settings_box.add(self.lzma_slider)
        settings_box.add(self.raw_checkbox)
        settings_box.add(self.verify_files_button)
        settings_box.add(self.uninstall_game_button)
        settings_box.add(save_button)

        if os.path.exists(os.path.join(self.settings.get("game_dir"), ".version")) is False:
            self.verify_files_button.enabled = False
            self.uninstall_game_button.enabled = False

        self.toggle_slider(None)

        settings_box.style.direction = COLUMN
        settings_box.style.alignment = CENTER
        game_dir_label.style.padding_top = 15
        self.game_dir_input.style.padding_bottom = 15
        #self.lzma_slider.style.padding_bottom = 15
        settings_box.style.width = 400
        settings_box.style.padding_left = 50

        self.settings_window.content = settings_box
        self.settings_window.show()

    def update_lzma_slider_text(self, widget):
        if self.lzma_slider.value != 0:
            self.lzma_slider_label.text = "LZMA Memory Cap: " + str(int(self.lzma_slider.value) * 2) + " MB"
        else:
            self.lzma_slider_label.text = "LZMA Memory Cap: Uncapped"

    async def uninstall_game_wrapper(self, widget):
        confirm_dialog = toga.ConfirmDialog(title="Piston Launcher", message="Are you sure you want to uninstall Minecraft: Dungeons?")
        if await self.dialog(confirm_dialog):
            self.set_button_state(False)
            self.set_button_text("Uninstalling")
            self.set_dlbox_visibility(True)
            uninstall_thread = threading.Thread(target=self.uninstall_game)
            uninstall_thread.start()
        widget.window.close()

    def uninstall_game(self):
        game_dir = self.settings.get("game_dir")
        file_count = sum(len(files) for _, _, files in os.walk(game_dir)) # beautiful
        self.loop.call_soon_threadsafe(self.set_max_progress, file_count + 1)
        for root, dirs, files in os.walk(game_dir, topdown=False):
            for file in files:
                file_path = os.path.join(root, file)
                os.remove(file_path)
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                os.rmdir(dir_path)
            self.loop.call_soon_threadsafe(self.update_progress)
        os.rmdir(game_dir)
        self.loop.call_soon_threadsafe(self.update_progress)
        self.loop.call_soon_threadsafe(self.set_button_state, True)
        self.loop.call_soon_threadsafe(self.set_button_text, "Install")
        self.loop.call_soon_threadsafe(self.set_dlbox_visibility, False)
        self.loop.call_soon_threadsafe(self.set_button_action, self.install_wrapper)
        self.loop.call_soon_threadsafe(self.set_game_version, "Not installed                        ")

    async def verify_files_wrapper(self, widget):
        self.set_button_state(False)
        self.set_button_text("Verifying")
        self.set_dlbox_visibility(True)
        self.toggle_settings_state(False)
        index_manifest = "https://piston-meta.mojang.com/v1/products/dungeons/f4c685912beb55eb2d5c9e0713fe1195164bba27/windows-x64.json"
        response = requests.get(index_manifest)
        try:
            game_manifest = response.json()["dungeons"][0]["manifest"]["url"]
            response = requests.get(game_manifest)
            print(response.json())
        except Exception:
            dialog = toga.ErrorDialog(title="Fatal Error!", message=f"Mojang has updated the game after {datetime.now().year - 2022} years!\nI haven't expected this, so the launcher doesn't support this yet.\nMake an issue on https://github.com/kenziewebm/piston-launcher!")
            await self.dialog(dialog)
            self.app.exit()
        self.loop.call_soon_threadsafe(self.set_max_progress, (len(response.json()["files"].keys())))
        verify_thread = threading.Thread(target=self.verify_files, args=(response,))
        verify_thread.start()
        widget.window.close()

    def verify_files(self, response):
        game_manifest = response.json()["files"]
        self.process_json_verify(game_manifest, self.settings.get("game_dir"))

        self.keep_settings_disabled = False

        self.loop.call_soon_threadsafe(self.set_button_state, True)
        self.loop.call_soon_threadsafe(self.set_button_text, "Play")
        self.loop.call_soon_threadsafe(self.set_button_action, lambda button: self.launch_wrapper())
        self.loop.call_soon_threadsafe(self.set_dlbox_visibility, False)
        self.loop.call_soon_threadsafe(self.toggle_settings_state, True)

    def process_json_verify(self, json_data, base_path):
        for key, value in json_data.items():
            if isinstance(value, dict):
                item_type = value.get("type")

                if item_type == "directory":
                    dir_path = os.path.join(base_path, key)
                    os.makedirs(dir_path, exist_ok=True)
                    print(f"MKDIR {dir_path}")
                    self.loop.call_soon_threadsafe(self.update_progress)

                    self.process_json_verify(json_data=value, base_path=base_path) # yay, recursion!

                elif item_type == "file":
                    downloads = value.get("downloads", {})
                    lzma = downloads.get("lzma")
                    raw = downloads.get("raw")

                    if os.path.exists(os.path.join(base_path, key)):
                        verify = True
                        download_info = raw
                    else:
                        verify = False
                        download_info = lzma if lzma and self.settings["download_raw"] is False else raw
                    
                    if download_info:
                        file_url = download_info.get("url")
                        file_sha1 = download_info.get("sha1")
                        file_path = os.path.join(base_path, key)

                        if verify is True:
                            print(f"SHA1 {file_path}", end='')
                            if (self.verify_sha1(file_path, file_sha1)):
                                print(" OK")
                                self.loop.call_soon_threadsafe(self.update_progress)
                            else:
                                print(" BAD")
                                self.download_file(file_url, file_path)
                                self.loop.call_soon_threadsafe(self.update_progress)

                        else:
                            print(f"MISSING {file_path}")
                            self.download_file(file_url, file_path)
                            if lzma and self.settings["download_raw"] is False:
                                print(f"LZMA {file_path} ", end='')
                                chunk_size = self.settings.get("lzma_mem_cap")
                                tmp_path = file_path + ".tmp"
                                with l.open(file_path, 'rb') as cf:
                                  with open(tmp_path, 'wb') as f:
                                     if chunk_size == 0:
                                         f.write(cf.read())
                                     else:
                                          while True:
                                            chunk = cf.read(1024 * 1024 * chunk_size)
                                            if not chunk:
                                                break
                                            f.write(chunk)
                                os.replace(tmp_path, file_path)
                                print("OK")
                            self.loop.call_soon_threadsafe(self.update_progress)

    def toggle_slider(self, widget):
        if self.raw_checkbox.value == True:
            self.lzma_slider.enabled = False
        else:
            self.lzma_slider.enabled = True

    def save_settings(self, widget):
        self.settings["game_dir"] = self.game_dir_input.value
        self.settings["lzma_mem_cap"] = int(self.lzma_slider.value)
        self.settings["download_raw"] = self.raw_checkbox.value
        with open("settings.json", 'w') as f:
            f.write(json.dumps(self.settings))
        self.set_button_state(True)
        widget.window.close()

    def startup(self):

        self.keep_settings_disabled = False
        self.settings = {}
        self.game_version = None

        if os.path.exists("settings.json"):
            with open("settings.json",'r') as f:
                self.settings = json.loads(f.read())

        self.settings["game_dir"] = self.settings.get("game_dir", "dungeons")
        self.settings["lzma_mem_cap"] = self.settings.get("lzma_mem_cap", 128)
        self.settings["download_raw"] = self.settings.get("download_raw", False)
        
        with open("settings.json", 'w') as f:
            f.write(json.dumps(self.settings))

        self._impl.create_menus = lambda *x, **y: None # hide menubar

        box = toga.Box()

        self.main_window = toga.MainWindow(size=(600, 270), resizable=False)
        self.main_window.content = box
        self.main_window.show()

        label = toga.Label("Piston Launcher")
        self.button = toga.Button("Wait...", enabled=False)
        self.dlbox = toga.Box()
        self.bar = toga.ProgressBar()
        self.items = toga.Label("")

        box2 = toga.Box()
        divider = toga.Divider()
        self.settings_button = toga.Button("Settings", on_press=self.open_settings_window)
        self.version_label = toga.Label("Game version: checking...")

        box.add(label)
        box.add(self.button)
        box.add(self.dlbox)
        box.add(divider)
        box.add(box2)

        self.dlbox.add(self.bar)
        self.dlbox.add(self.items)

        box2.add(self.version_label)
        box2.add(self.settings_button)

        box.style.direction = COLUMN
        box.style.alignment = CENTER
        label.style.text_align = CENTER
        label.style.padding_bottom = 25
        self.dlbox.style.direction = ROW
        self.dlbox.style.alignment = CENTER
        self.dlbox.style.padding_bottom = 100
        box2.style.direction = ROW
        self.version_label.style.alignment = LEFT
        self.settings_button.style.alignment = RIGHT
        
        label.style.font_size = 26
        self.bar.style.width = 150
        self.button.style.width = 128
        self.items.style.padding = 5
        self.button.style.padding = 5
        self.settings_button.style.width = 64

        box2.style.width = 500
        self.version_label.style.padding_top = 5
        self.version_label.style.padding_right = 70
        self.version_label.style.font_family = "monospace"

        box.style.width = 500
        box.style.height = 270
        box.style.padding_left = 50

        if os.path.exists(os.path.join(self.settings.get("game_dir"), ".version")):
            with open(os.path.join(self.settings.get("game_dir"), ".version"), 'r') as f:
                self.game_version = f.read().strip()
                self.set_game_version(self.game_version)
            self.button.on_press = self.launch_wrapper
            self.button.text = "Play"
        else:
            self.set_game_version("Not installed                        ") # ugly hack to make it layout correctly, since the settings button
                                                                           # is just pushed back by a padding: 110px instead of float:right
                                                                           # (because i tried float:right and it didnt work)
            self.button.on_press = self.install_wrapper
            self.button.text = "Install"

        self.button.enabled = True
        self.set_dlbox_visibility(False)

if __name__ == '__main__':
    app = PistonLauncher(formal_name="Piston Launcher", app_id="xyz.kenziewebm.piston-launcher")
    app.main_loop()