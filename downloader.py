#!python3
from urllib.parse import urlparse, unquote

import appdirs
import argparse
from json import loads
from pathlib import Path
import os
from requests import session
import shutil
from distutils.dir_util import copy_tree
from threading import Thread
from tkinter import *
from tkinter import ttk, filedialog
from tempfile import gettempdir
from zipfile import ZipFile

parser = argparse.ArgumentParser(description="Download Curse modpack mods")
parser.add_argument("--manifest", help="manifest.json file from unzipped pack")
parser.add_argument("--nogui", dest="gui", action="store_false", help="Do not use gui to to select manifest")
parser.add_argument("--portable", dest="portable", action="store_true", help="Use portable cache")
args, unknown = parser.parse_known_args()

class downloadUI(ttk.Frame):
    def __init__(self):
        self.root = Tk()
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.parent = ttk.Frame(self.root)
        self.parent.grid(column=0, row=0, sticky=(N, S, E, W))
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(0, weight=1)
        ttk.Frame.__init__(self, self.parent, padding=(6,6,14,14))
        self.grid(column=0, row=0, sticky=(N, S, E, W))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self.root.title("Curse Pack Downloader")

        self.manifest_path = StringVar()
        self.multimc_path = StringVar()

        chooser_container = ttk.Frame(self)
        self.chooser_text = ttk.Label(chooser_container, text="Locate modpack zip: ")
        chooser_entry = ttk.Entry(chooser_container, textvariable=self.manifest_path)
        self.chooser_button = ttk.Button(chooser_container, text="Browse", command=self.choose_file)
        self.chooser_text.grid(column=0, row=0, sticky=W)
        chooser_entry.grid(column=1, row=0, sticky=(E,W), padx=5)
        self.chooser_button.grid(column=2, row=0, sticky=E)
        chooser_container.grid(column=0, row=0, sticky=(E,W))
        chooser_container.columnconfigure(1, weight=1)

        chooser_multimc_container = ttk.Frame(self)
        self.chooser_multimc_text = ttk.Label(chooser_container, text="Locate MultiMC instance (optional): ")
        chooser_multimc_entry = ttk.Entry(chooser_container, textvariable=self.multimc_path)
        self.chooser_multimc_button = ttk.Button(chooser_container, text="Browse", command=self.choose_multimc_path)
        self.chooser_multimc_text.grid(column=0, row=1, sticky=W)
        chooser_multimc_entry.grid(column=1, row=1, sticky=(E,W), padx=5)
        self.chooser_multimc_button.grid(column=2, row=1, sticky=E)
        chooser_multimc_container.grid(column=0, row=1, sticky=(E,W))
        chooser_multimc_container.columnconfigure(1, weight=2)
        
        download_button = ttk.Button(self, text="Start Download", command=self.go_download)
        download_button.grid(column=0, row=2, sticky=(E,W))

        self.log_text = Text(self, state="disabled", wrap="none")
        self.log_text.grid(column=0, row=3, sticky=(N,E,S,W))

    def choose_file(self):
        file_path = filedialog.askopenfilename(
                filetypes=(("Zip files", "*.zip"),),
                initialdir=os.path.expanduser("~"),
                parent=self)
        self.manifest_path.set(file_path)

    def choose_multimc_path(self):
        file_path = filedialog.askdirectory(parent=self)
        self.multimc_path.set(file_path)

    def go_download(self):
        t = Thread(target=self.go_download_background)
        t.start()

    def go_download_background(self):
        self.chooser_button.configure(state="disabled")
        do_download(self.manifest_path.get(), self.multimc_path.get())
        self.chooser_button.configure(state="enabled")

    def set_output(self, message):
        self.log_text["state"] = "normal"
        self.log_text.insert("end", message + "\n")
        self.log_text["state"] = "disabled"
        self.log_text.see(END)

    def set_manifest(self, file_name):
        self.manifest_path.set(file_name)

class headlessUI():
    def set_output(self, message):
        pass

program_gui = None

def unzip_modpack(modpack_path):
    temp_dir = Path(gettempdir()).joinpath(str(os.getpid()))

    try:
        with ZipFile(str(modpack_path), 'r') as modpack_zip_file:
            modpack_zip_file.extractall(str(temp_dir))
    except Exception as e:
        raise PermissionError("Failed to extract to temp dir")

    return temp_dir

def do_download(modpack, multimc):
    if multimc != "":
        multimc_path = Path(multimc)
        if False == os.path.isfile(str(multimc_path.joinpath("patches/net.minecraftforge.json"))):
            program_gui.set_output("Error: Could not find forge in instance")
            return
    else:
        multimc_path = Path(modpack).parent

    modpack_path = Path(modpack)
    target_dir_path = multimc_path

    try:
        program_gui.set_output("Unzipping download..")
        content_path = unzip_modpack(modpack_path)
    except PermissionError:
        program_gui.set_output("Error: unzipping modpack to temp directory failed. Try again?")
        return

    manifest_text = content_path.joinpath("manifest.json").open().read()
    manifest_text = manifest_text.replace('\r', '').replace('\n', '')

    manifest_json = loads(manifest_text)

    minecraft_path = Path(target_dir_path, "minecraft")
    override_path = minecraft_path

    program_gui.set_output("Copying overrides..")
    copy_tree(str(content_path.joinpath(manifest_json["overrides"])),
              str(minecraft_path))

    downloader_dirs = appdirs.AppDirs(appname="cursePackDownloader", appauthor="portablejim")
    cache_path = Path(downloader_dirs.user_cache_dir, "curseCache")

    # Attempt to set proper portable data directory if asked for
    if args.portable:
        if '__file__' in globals():
            cache_path = Path(os.path.dirname(os.path.realpath(__file__)), "CPD_data")
        else:
            print("Portable data dir not supported for interpreter environment")
            exit(2)

    if not cache_path.exists():
        cache_path.mkdir(parents=True)

    if not minecraft_path.exists():
        minecraft_path.mkdir()
        mods_path = minecraft_path / "mods"
        if not mods_path.exists():
            mods_path.mkdir()

    sess = session()

    i = 1
    iLen = len(manifest_json['files'])

    print("%d files to download" % (iLen))
    program_gui.set_output("%d files to download" % (iLen))

    for dependency in manifest_json['files']:
        dep_cache_dir = cache_path / str(dependency['projectID']) / str(dependency['fileID'])
        if dep_cache_dir.is_dir():
            # File is cached
            dep_files = [f for f in dep_cache_dir.iterdir()]
            if len(dep_files) >= 1:
                dep_file = dep_files[0]
                target_file = minecraft_path / "mods" / dep_file.name
                shutil.copyfile(str(dep_file), str(target_file))
                program_gui.set_output("[%d/%d] %s (cached)" % (i, iLen, target_file.name))

                i += 1

                # Cache access is successful,
                # Don't download the file
                continue

        # File is not cached and needs to be downloaded
        project_response = sess.get("http://minecraft.curseforge.com/mc-mods/%s" % (dependency['projectID']), stream=True)
        project_response.url = project_response.url.replace('?cookieTest=1', '')
        file_response = sess.get("%s/files/%s/download" % (project_response.url, dependency['fileID']), stream=True)
        while file_response.is_redirect:
            source = file_response
            file_response = sess.get(source, stream=True)
        file_path = Path(file_response.url)
        file_name = unquote(file_path.name)
        print("[%d/%d] %s" % (i, iLen, file_name))
        program_gui.set_output("[%d/%d] %s" % (i, iLen, file_name))
        with open(str(minecraft_path / "mods" / file_name), "wb") as mod:
            mod.write(file_response.content)

        # Try to add file to cache.
        if not dep_cache_dir.exists():
            dep_cache_dir.mkdir(parents=True)
            with open(str(dep_cache_dir / file_name), "wb") as mod:
                mod.write(file_response.content)

        i += 1

    # This is not available in curse-only packs
    if 'directDownload' in manifest_json:
        i = 1
        i_len = len(manifest_json['directDownload'])
        program_gui.set_output("%d additional files to download." % i_len)
        for download_entry in manifest_json['directDownload']:
            if "url" not in download_entry or "file_name" not in download_entry:
                program_gui.set_output("[%d/%d] <Error>" % (i, i_len))
                i += 1
                continue
            source_url = urlparse(download_entry['url'])
            download_cache_children = Path(source_url.path).parent.relative_to('/')
            download_cache_dir = cache_path / "directdownloads" / download_cache_children
            cache_target = Path(download_cache_dir / download_entry['file_name'])
            if cache_target.exists():
                # Cached
                target_file = minecraft_path / "mods" / cache_target.name
                shutil.copyfile(str(cache_target), str(target_file))

                i += 1

                # Cache access is successful,
                # Don't download the file
                continue
            # File is not cached and needs to be downloaded
            file_response = sess.get(source_url, stream=True)
            while file_response.is_redirect:
                source = file_response
                file_response = sess.get(source, stream=True)
            program_gui.set_output("[%d/%d] %s" % (i, i_len, download_entry['file_name']))
            with open(str(minecraft_path / "mods" / download_entry['file_name']), "wb") as mod:
                mod.write(file_response.content)

            i += 1

    shutil.rmtree(str(content_path), ignore_errors=True)
    program_gui.set_output("Done!")
    return

if args.gui:
    program_gui = downloadUI()
    if args.manifest is not None:
        program_gui.set_manifest(args.manifest)
    program_gui.root.mainloop()
else:
    program_gui = headlessUI()
    do_download(args.manifest)


