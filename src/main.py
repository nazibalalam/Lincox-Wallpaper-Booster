import argparse
import os

# Make sure that X11 is the backend. This makes sure Wayland reverts to XWayland.
os.environ['GDK_BACKEND'] = "x11"

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    #group = parser.add_mutually_exclusive_group(required=False)
    parser.add_argument(
        "-p",
        "--path",
        type=str,
        help="Path to the wallpaper video",
    )
    parser.add_argument(
        "-v",
        '--volume',
        type=int,
        help="Amount of Sound (if any) to be played in the wallpaper",
    )
    parser.add_argument(
        "-r",
        "--rate",
        type=int,
        help="Playback Speed of the wallpaper"
    )
    
    args = parser.parse_args()

    from media import Media

    if args.path and os.path.exists(args.path):
        if args.volume:
            Media(args.path, args.volume, 1)
        if args.rate:
            Media(args.path, 100, args.rate)
    else:
        parser.print_help()