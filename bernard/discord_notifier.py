"""A logging handler that emits to a Discord webhook."""
import requests
from logging import Handler


class DiscordHandler(Handler):
    """A logging handler that emits to a Discord webhook."""

    def __init__(self, webhook, *args, **kwargs):
        """Initialize the DiscordHandler class."""
        super().__init__(*args, **kwargs)
        self.webhook = webhook

    def emit(self, record):
        """Emit record to the Discord webhook."""
        json = {'content': self.format(record)}
        try:
            requests.post(self.webhook, json=json)
        except requests.RequestException:
            self.handleError(record)
