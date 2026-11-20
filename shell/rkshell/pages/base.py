"""What every window on the desktop has in common."""
from ..widgets import Screen


class Page(Screen):
    title = ""
    icon = ""

    def enter(self):
        """Called when the window opens."""

    def wants_back(self):
        """True when B has something to do inside the window; otherwise B closes it."""
        return False

    def handle(self, action):
        pass
