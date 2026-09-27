import logging
from pathlib import Path


def play_welcome():
    """Play the entry greeting without blocking the UI or affecting check-in."""
    try:
        import winsound

        sound = Path(__file__).resolve().parents[2] / "assets" / "welcome.wav"
        winsound.PlaySound(
            str(sound), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
    except (ImportError, OSError, RuntimeError):
        logging.getLogger(__name__).warning("Could not play entry greeting", exc_info=True)
