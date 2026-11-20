"""What every page across the top has in common."""
from ..widgets import Screen


class Page(Screen):
    title = ""

    def enter(self):
        """Called when the page becomes the one shown."""

    def handle(self, action):
        pass
