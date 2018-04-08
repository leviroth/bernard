import requests
from logging import Handler


class DiscordHandler(Handler):
    def __init__(self, webhook, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.webhook = webhook

    def emit(self, record):
        json = {'content': self.format(record)}
        try:
            requests.post(self.webhook, json=json)
        except:
            self.handleError(record)
