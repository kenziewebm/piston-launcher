import os
import sys
import toga
import hashlib
import requests
import threading
import subprocess
import lzma as l # TODO: the game manifest has {"lzma":{"url":"whatever"}} for compressed files, have to either fix that or do this
from sys import executable
from toga.style.pack import * 

class PistonLauncher(toga.App):
    def install_wrapper(self, game_dir):
        """
        Wrapper for install_game()
        :param button: Ignored.
        :param box: Needed to update UI while installing.
        :param game_dir: Directory path to install the game to.
        """
        with open(".game_dir", 'w') as f:
            f.write(game_dir)
        install_thread = threading.Thread(target=self.install_game, args=(game_dir,))
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
        with open(".game_dir",'r') as f:
            game_dir = f.read().strip()
        game_exec = os.path.join(game_dir, "Dungeons.exe")
        game_thread = threading.Thread(target=self.launch_game, args=(game_exec,), daemon=True)
        game_thread.start()
        

    def install_game(self, game_dir="F:\\games\\piston"):
        """
        Proceed with installation of Minecraft Dungeons
        :param game_dir: Directory path to install the game to.
        """
        base_url = "https://piston-meta.mojang.com/v1/products/dungeons"
        index_manifest = "/f4c685912beb55eb2d5c9e0713fe1195164bba27/windows-x64.json" # TODO: make not hardcoded. will be hard since the random string at
                                                                                      # the beginning of each file is the hash of that file, and i haven't
                                                                                      # found a manifest 1-level higher than this
        response = requests.get(base_url + index_manifest)

        if not os.path.exists(game_dir):
            os.mkdir(game_dir)

        game_manifest = response.json()["dungeons"][0]["manifest"]["url"] # bad!
        game_version = response.json()["dungeons"][0]["version"]["name"] # bad!

        with open(os.path.join(game_dir, ".version"), 'w') as f: # the official launcher creates this file
            f.write(game_version)

        response = requests.get(game_manifest)

        self.loop.call_soon_threadsafe(self.set_max_progress, (len(response.json()["files"].keys())))
        self.process_json(response.json()["files"], game_dir) # bad!
        
        self.loop.call_soon_threadsafe(self.set_button_state, True)
        self.loop.call_soon_threadsafe(self.set_button_text, "Play")
        self.loop.call_soon_threadsafe(self.set_button_action, lambda button: self.launch_wrapper())
        self.loop.call_soon_threadsafe(self.set_dlbox_visibility, False)

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

                    download_info = lzma if lzma else raw
                    if download_info:
                        file_url = download_info.get("url")
                        file_sha1 = download_info.get("sha1")
                        file_path = os.path.join(base_path, key)

                        self.download_file(file_url, file_path)

                        if file_sha1:
                            print(f"SHA1 {file_path} ", end='')
                            if self.verify_sha1(file_path, file_sha1):
                                print("OK")
                            else:
                                print("BAD")
                                os.remove(file_path)
                                continue

                        if lzma:
                            print(f"LZMA {file_path} ", end='')
                            tmp_path = file_path + ".tmp"
                            with l.open(file_path, 'rb') as cf:
                                with open(tmp_path, 'wb') as f:
                                    while True:
                                        chunk = cf.read(1024 * 1024) # chunked because i ran out of ram while developing
                                        if not chunk:
                                            break
                                        f.write(chunk)

                            os.replace(tmp_path, file_path)
                            print("OK")

                        self.loop.call_soon_threadsafe(self.update_progress)

    # im pretty sure that theres a much smarter way to do this
    # than making 5 billion tiny functions, but i cant come up
    # with anything with anything better

    def update_progress(self):
        self.bar.value += 1
        self.items.text = f"{self.bar.value}/{self.bar.max}"

    def set_max_progress(self, max):
        self.bar.max = max

    def set_button_text(self, text):
        self.button.text = text

    def set_button_state(self, state):
        self.button.enabled = state

    def set_button_action(self, action):
        self.button.on_press = action

    def set_dlbox_visibility(self, state):
        self.dlbox.style.visibility = HIDDEN if state is False else VISIBLE
        self.bar.style.visibility = HIDDEN if state is False else VISIBLE
        self.items.style.visibility = HIDDEN if state is False else VISIBLE

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
        return calculated_sha1 == expected_sha1
    
    def startup(self):

        self._impl.create_menus = lambda *x, **y: None # hide menubar

        box = toga.Box()

        self.main_window = toga.MainWindow()
        self.main_window.content = box
        self.main_window.show()

        label = toga.Label("Piston Launcher")
        self.button = toga.Button("Wait...", enabled=False)
        self.dlbox = toga.Box()
        self.bar = toga.ProgressBar()
        self.items = toga.Label("")

        box.add(label)
        box.add(self.button)
        box.add(self.dlbox)

        self.dlbox.add(self.bar)
        self.dlbox.add(self.items)

        self.bar.style.visibility = HIDDEN
        self.dlbox.style.visiblity = HIDDEN
        self.items.style.visibility = HIDDEN

        box.style.direction = COLUMN
        box.style.alignment = CENTER
        label.style.text_align = CENTER
        self.dlbox.style.direction = ROW
        self.dlbox.style.alignment = CENTER
        
        label.style.font_size = 26
        self.bar.style.width = 150
        self.button.style.width = 64
        self.items.style.padding = 5
        self.button.style.padding = 5

        if os.path.exists(".game_dir"):
            self.button.on_press = lambda button: self.launch_wrapper()
            self.button.text = "Play"
            self.button.enabled = True
        else:
            self.dlbox.style.visibility = VISIBLE
            self.button.on_press = lambda button: self.install_wrapper("F:\\games\\piston") # TODO: un-hardcode path before release
            self.button.text = "Install"
            self.button.enabled = True

if __name__ == '__main__':
    app = PistonLauncher(formal_name="Piston Launcher", app_id="xyz.kenziewebm.piston-launcher")
    app.main_loop()