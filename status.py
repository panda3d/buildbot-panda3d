__all__ = []

from buildbot.plugins import reporters
import config

irc_status = reporters.IRC(host=config.irc_host, nick=config.irc_nick,
                           channels=config.irc_channels, notify_events={
                               'exception': False,
                               'failureToSuccess': True,
                               'successToFailure': True})

webhook_status = reporters.HttpStatusPush(config.webhook_url)
