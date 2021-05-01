import os
import signal
import gi
import ctypes
import vlc
import sys

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from utils import  ActiveHandler, WindowHandler, WindowHandlerGnome, StaticWallpaperHandler


class VLCWidget(Gtk.DrawingArea):
  
    __gtype_name__ = "VLCWidget"

    def __init__(self, width, height):
        
        self.instance = vlc.Instance()
        Gtk.DrawingArea.__init__(self)
        self.player = self.instance.media_player_new()

        def handle_embed(*args):
            self.player.set_xwindow(self.get_window().get_xid())
            return True

        self.connect("realize", handle_embed)
        self.set_size_request(width, height)

class Monitor:

    def __init__(self, gdk_monitor: Gdk.Monitor):
        self.gdk_monitor = gdk_monitor
        
        self.__window = None
        self.__vlc_widget = None

    def initialize(self, window: Gtk.Window, vlc_widget: VLCWidget):
        self.__window = window
        self.__vlc_widget = vlc_widget

    @property
    def is_initialized(self):
        return self.__window is not None and self.__vlc_widget is not None

    @property
    def x(self):
        return self.gdk_monitor.get_geometry().x

    @property
    def y(self):
        return self.gdk_monitor.get_geometry().y

    @property
    def width(self):
        return self.gdk_monitor.get_geometry().width * self.gdk_monitor.get_scale_factor()

    @property
    def height(self):
        return self.gdk_monitor.get_geometry().height * self.gdk_monitor.get_scale_factor()

    @property
    def is_primary(self):
        return self.gdk_monitor.is_primary()

    def vlc_play(self):
        if self.is_initialized:
            self.__vlc_widget.player.play()

    def vlc_is_playing(self):
        if self.is_initialized:
            return self.__vlc_widget.player.is_playing()

    def vlc_pause(self):
        if self.is_initialized:
            self.__vlc_widget.player.pause()

    def vlc_media_new(self, *args):
        if self.is_initialized:
            return self.__vlc_widget.instance.media_new(*args)

    def vlc_set_media(self, *args):
        if self.is_initialized:
            self.__vlc_widget.player.set_media(*args)

    def vlc_audio_set_volume(self, *args):
        if self.is_initialized:
            self.__vlc_widget.player.audio_set_volume(*args)

    def vlc_get_position(self, *args):
        if self.is_initialized:
            return self.__vlc_widget.player.get_position()

    def vlc_set_position(self, *args):
        if self.is_initialized:
            self.__vlc_widget.player.set_position(*args)

    def win_move(self, *args):
        if self.is_initialized:
            self.__window.move(*args)

    def win_resize(self, *args):
        if self.is_initialized:
            self.__window.resize(*args)

    def __eq__(self, other):
        if isinstance(other, Monitor):
            return self.gdk_monitor == other.gdk_monitor
        return False

    def __del__(self):
        if self.is_initialized:
            self.__vlc_widget.player.release()
            self.__window.close()


class Media:
    def __init__(self, video_path, volume, rate):
        signal.signal(signal.SIGINT, self._quit)
        signal.signal(signal.SIGTERM, self._quit)
       
        signal.signal(signal.SIGSEGV, self._quit)

        self.current_video_path = video_path
        self.current_volume = volume
        self.current_rate = rate
        self.user_pause_playback = False
        self.is_any_maximized, self.is_any_fullscreen = False, False

       
        x11 = None
        for lib in ["libX11.so", "libX11.so.6"]:
            try:
                x11 = ctypes.cdll.LoadLibrary(lib)
            except OSError:
                pass
            if x11 is not None:
                x11.XInitThreads()
                break

        
        self.monitors = []
        self.monitor_detect()
        self.start_all_monitors()

        self.active_handler = ActiveHandler(self._on_active_changed)
        if os.environ["DESKTOP_SESSION"] in ["gnome", "gnome-xorg"]:
            self.window_handler = WindowHandlerGnome(self._on_window_state_changed)
        else:
            self.window_handler = WindowHandler(self._on_window_state_changed)
        self.static_wallpaper_handler = StaticWallpaperHandler(self.current_video_path)
        self.static_wallpaper_handler.set_static_wallpaper()

        if self.current_video_path == "":
            ControlPanel().run()
        elif not os.path.isfile(self.current_video_path):
            print("File not found")
            sys.exit(1)

        Gtk.main()

    def start_all_monitors(self):
        for monitor in self.monitors:
            if monitor.is_initialized:
                continue
            
            vlc_widget = VLCWidget(monitor.width, monitor.height)
            media = vlc_widget.instance.media_new(self.current_video_path)
            
            media.add_option("input-repeat=65535")

            if not monitor.is_primary:
                media.add_option("no-audio")

            vlc_widget.player.set_media(media)
            vlc_widget.player.video_set_mouse_input(False)
            vlc_widget.player.video_set_key_input(False)
            vlc_widget.player.audio_set_volume(self.current_volume)
            vlc_widget.player.set_rate(self.current_rate)

            
            window = Gtk.Window()
            window.add(vlc_widget)
            window.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
            window.set_size_request(monitor.width, monitor.height)
            window.move(monitor.x, monitor.y)

            window.show_all()

            monitor.initialize(window, vlc_widget)

    def set_volume(self, volume):
        for monitor in self.monitors:
            if monitor.is_primary:
                monitor.vlc_audio_set_volume(volume)

    def pause_playback(self):
        for monitor in self.monitors:
            monitor.vlc_pause()

    def start_playback(self):
        if not self.user_pause_playback:
            for monitor in self.monitors:
                monitor.vlc_play()

    def _quit(self, *args):
        self.static_wallpaper_handler.restore_ori_wallpaper()
        del self.monitors
        Gtk.main_quit()

    def monitor_detect(self):
        display = Gdk.Display.get_default()
        screen = display.get_default_screen()

        for i in range(display.get_n_monitors()):
            monitor = Monitor(display.get_monitor(i))
            if monitor not in self.monitors:
                self.monitors.append(monitor)

        screen.connect("size-changed", self._on_size_changed)
        display.connect("monitor-added", self._on_monitor_added)
        display.connect("monitor-removed", self._on_monitor_removed)

    def monitor_sync(self):
        primary = 0
        for i, monitor in enumerate(self.monitors):
            if monitor.is_primary:
                primary = i
                break
        for monitor in self.monitors:
           
            monitor.vlc_play()
            monitor.vlc_set_position(self.monitors[primary].vlc_get_position())
            monitor.vlc_play() if self.monitors[primary].vlc_is_playing() else monitor.vlc_pause()

    def _on_size_changed(self, *args):
        print("size-changed")
        for monitor in self.monitors:
            monitor.win_resize(monitor.width, monitor.height)
            monitor.win_move(monitor.x, monitor.y)
            print(monitor.x, monitor.y, monitor.width, monitor.height)

    def _on_monitor_added(self, _, gdk_monitor, *args):
        print("monitor-added")
        new_monitor = Monitor(gdk_monitor)
        self.monitors.append(new_monitor)
        self.start_all_monitors()
        self.monitor_sync()

    def _on_monitor_removed(self, _, gdk_monitor, *args):
        print("monitor-removed")
        self.monitors.remove(Monitor(gdk_monitor))

    def _on_active_changed(self, active):
        if active:
            self.pause_playback()
        else:
            if self.is_any_maximized or self.is_any_fullscreen:
                self.pause_playback()
            else:
                self.start_playback()

    def _on_window_state_changed(self, state):
        self.is_any_maximized, self.is_any_fullscreen = state["is_any_maximized"], state["is_any_fullscreen"]
        if self.is_any_maximized or self.is_any_fullscreen:
            self.pause_playback()
        else:
            self.start_playback()