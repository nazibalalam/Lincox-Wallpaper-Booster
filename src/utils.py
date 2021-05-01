import os
import json
import subprocess
import pathlib
import gi
import pydbus

gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", '3.0')
from gi.repository import GLib, Wnck, Gio
from PIL import Image, ImageFilter


class ActiveHandler:

    def __init__(self, on_active_changed: callable):
        session_bus = pydbus.SessionBus()
        screensaver_list = ["org.gnome.ScreenSaver",
                            "org.cinnamon.ScreenSaver",
                            "org.kde.screensaver",
                            "org.freedesktop.ScreenSaver"]
        for s in screensaver_list:
            try:
                proxy = session_bus.get(s)
                proxy.ActiveChanged.connect(on_active_changed)
            except GLib.Error:
                pass


class WindowHandler:

    def __init__(self, on_window_state_changed: callable):
        self.on_window_state_changed = on_window_state_changed
        self.screen = Wnck.Screen.get_default()
        self.screen.force_update()
        self.screen.connect("window-opened", self.window_opened, None)
        self.screen.connect("window-closed", self.eval, None)
        self.screen.connect("active-workspace-changed", self.eval, None)
        for window in self.screen.get_windows():
            window.connect("state-changed", self.eval, None)

        self.prev_state = None
       
        self.eval()

    def window_opened(self, screen, window, _):
        window.connect("state-changed", self.eval, None)

    def eval(self, *args):
        is_changed = False

        is_any_maximized, is_any_fullscreen = False, False
        for window in self.screen.get_windows():
            base_state = not Wnck.Window.is_minimized(window) and \
                         Wnck.Window.is_on_workspace(window, self.screen.get_active_workspace())
            window_name, is_maximized, is_fullscreen = window.get_name(), \
                                                       Wnck.Window.is_maximized(window) and base_state, \
                                                       Wnck.Window.is_fullscreen(window) and base_state
            if is_maximized is True:
                is_any_maximized = True
            if is_fullscreen is True:
                is_any_fullscreen = True

        cur_state = {"is_any_maximized": is_any_maximized, "is_any_fullscreen": is_any_fullscreen}
        if self.prev_state is None or self.prev_state != cur_state:
            is_changed = True
            self.prev_state = cur_state

        if is_changed:
            self.on_window_state_changed({"is_any_maximized": is_any_maximized, "is_any_fullscreen": is_any_fullscreen})
            print("WindowHandler:", cur_state)


class WindowHandlerGnome:


    def __init__(self, on_window_state_changed: callable):
        self.on_window_state_changed = on_window_state_changed
        self.gnome_shell = pydbus.SessionBus().get("org.gnome.Shell")
        self.prev_state = None
        GLib.timeout_add(500, self.eval)

    def eval(self):
        is_changed = False

        ret1, workspace = self.gnome_shell.Eval("""
                        global.workspace_manager.get_active_workspace_index()
                        """)

        ret2, maximized = self.gnome_shell.Eval(f"""
                var window_list = global.get_window_actors().find(window =>
                    window.meta_window.maximized_horizontally &
                    window.meta_window.maximized_vertically &
                    !window.meta_window.minimized &
                    window.meta_window.get_workspace().workspace_index == {workspace}
                );
                window_list
                """)

        ret3, fullscreen = self.gnome_shell.Eval(f"""
                var window_list = global.get_window_actors().find(window =>
                    window.meta_window.is_fullscreen() &
                    !window.meta_window.minimized &
                    window.meta_window.get_workspace().workspace_index == {workspace}
                );
                window_list
                """)
        if not all([ret1, ret2, ret3]):
            raise RuntimeError("Cannot communicate with Gnome Shell!")

        cur_state = {'is_any_maximized': maximized != "", 'is_any_fullscreen': fullscreen != ""}
        if self.prev_state is None or self.prev_state != cur_state:
            is_changed = True
            self.prev_state = cur_state

        if is_changed:
            self.on_window_state_changed({"is_any_maximized": maximized != "", "is_any_fullscreen": fullscreen != ""})
            print("WindowHandler:", cur_state)
        return True


class StaticWallpaperHandler:

    def __init__(self, video_path):
        self.current_video_path = video_path
        self.gso = Gio.Settings.new("org.gnome.desktop.background")
        self.ori_wallpaper_uri = self.gso.get_string("picture-uri")
        self.new_wallpaper_uri = "/tmp/hidamari.png"

    def set_static_wallpaper(self):

        subprocess.call(
            'ffmpeg -y -i "{}" -vframes 1 "{}" -loglevel quiet > /dev/null 2>&1 < /dev/null'.format(
                self.current_video_path, self.new_wallpaper_uri), shell=True)
        if os.path.isfile(self.new_wallpaper_uri):
            blur_wallpaper = Image.open(self.new_wallpaper_uri)
            blur_wallpaper.save(self.new_wallpaper_uri)
            self.gso.set_string("picture-uri", pathlib.Path(self.new_wallpaper_uri).resolve().as_uri())

    def restore_ori_wallpaper(self):
        self.gso.set_string("picture-uri", self.ori_wallpaper_uri)
        if os.path.isfile(self.new_wallpaper_uri):
            os.remove(self.new_wallpaper_uri)