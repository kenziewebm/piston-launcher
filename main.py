import os
import toga
import lzma as l # TODO: the game manifest has {"lzma":{"url":"whatever"}} for compressed files, have to either fix that or do this
import hashlib
import requests
import threading
from toga.style.pack import * 

def install_wrapper(button, box):
    install_thread = threading.Thread(target=install_game, args=(box.children[2],))
    install_thread.start()

def install_game(box, game_dir="F:\\games\\piston"):
    """
    Proceed with installation of Minecraft Dungeons
    :param game_dir: Directory path to install the game to.
    """
    base_url = "https://piston-meta.mojang.com/v1/products/dungeons"
    index_manifest = "/f4c685912beb55eb2d5c9e0713fe1195164bba27/windows-x64.json" # TODO: make not hardcoded
    response = requests.get(base_url + index_manifest)

    if not os.path.exists(game_dir):
        os.mkdir(game_dir)

    game_manifest = response.json()["dungeons"][0]["manifest"]["url"] # bad!
    response = requests.get(game_manifest)

    print(len(response.json()["files"].keys()))

    process_json(box, response.json()["files"], game_dir) # bad!
    box.children[0].max = len(response.json()["files"].keys()) - 1 # -1 because of the empty "" directory

def process_json(box, json_data, base_path):
    """
    Process the JSON structure to create directories, download files, and set executables.
    :param json_data: The JSON data to process.
    :param base_path: The base directory to operate in.
    """
    for key, value in json_data.items():
        if isinstance(value, dict):
            item_type = value.get("type")

            if item_type == "directory":
                # Create a directory
                dir_path = os.path.join(base_path, key)
                os.makedirs(dir_path, exist_ok=True)
                print(f"MKDIR {dir_path}")

                # Recursively process its children
                process_json(box, value, dir_path)

            elif item_type == "file":
                downloads = value.get("downloads", {})
                lzma = downloads.get("lzma")
                raw = downloads.get("raw")

                # Determine the URL and file size
                download_info = lzma if lzma else raw
                if download_info:
                    file_url = download_info.get("url")
                    file_sha1 = download_info.get("sha1")
                    file_path = os.path.join(base_path, key)

                    # Download the file
                    download_file(file_url, file_path)

                    # Verify the SHA1 checksum
                    if file_sha1:
                        print(f"SHA1 {file_path} ", end='')
                        if verify_sha1(file_path, file_sha1):
                            print("OK")
                        else:
                            print("BAD")
                            os.remove(file_path)
                            continue

                    # decompress if LZMA
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

                    box.children[0].value = box.children[0].value + 1
                    box.children[1].text = f"{box.children[0].value} / {box.children[0].max}"

def download_file(url, path):
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


def verify_sha1(file_path, expected_sha1):
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

# these next 2 exist because thread safety
# or something idrk

def build(app):
    box = toga.Box()

    label = toga.Label("Piston Launcher")
    button = toga.Button("Install", on_press=lambda button: install_wrapper(button, box))
    dlbox = toga.Box()
    bar = toga.ProgressBar()
    items = toga.Label("")

    box.add(label)
    box.add(button)
    box.add(dlbox)

    dlbox.add(bar)
    dlbox.add(items)

    # we got CSS in Python before GTA 6
    label.style.font_size = 26
    label.style.text_align = CENTER
    button.style.width = 64
    button.style.padding = 5
    box.style.direction = COLUMN
    box.style.alignment = CENTER
    dlbox.style.direction = ROW
    dlbox.style.alignment = CENTER
    items.style.padding = 5
    bar.style.width = 150

    return box


def main():
    return toga.App("Piston Launcher", "xyz.kenziewebm.piston-launcher", startup=build, home_page="https://github.com/kenziewebm/piston-launcher")


if __name__ == "__main__":
    main().main_loop()