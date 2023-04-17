import asyncio
import json
import os
import random
from typing import List

from telethon import TelegramClient, utils as tutils
from telethon.errors import ChannelPrivateError, FloodWaitError

from telethon.hints import EntityLike
from telethon.tl.types import InputPeerChannel, InputPeerSelf

import logging

from src.common.get_project_root import get_project_root

logger = logging.getLogger(__name__)

CHANNEL_CACHE_FILEPATH = 'src/data/channels_cache.json'
CHANNEL_RESTORE_REQUEST_PROB = 1/5000


class Channel:
    """
    Zeroly, parses input if the entity/parsable is of unknown type. For this, no API calls are performed.
    Firstly, checks cached values in smartfeed database.
    Secondly, tries to make a request and updates the values.
    Otherwise, the channel will be with missed values.
    """

    def __init__(self, parsable=None, channel_id=None, channel_name=None, channel_link=None,
                 is_public=None, restore_values=True, force_update=False, client=None):

        self._client = client
        self.parsable = parsable
        self.id = channel_id
        self.name = channel_name
        self.link = channel_link  # consider a list of links? invite vs channel?
        self.input_entity = None  # TODO: maybe initialize from input? Are there cases to pass it?
        self.is_public = is_public
        self.restore_values = restore_values
        self.force_update = force_update

        if self.parsable:
            # here entity may be already in the cache but of not known type (ID, link) so the goal here is to define
            # the entity type and decide what kind of processing is needed. Instead of parsing ourselves, we can get
            # ID with the solution from telethon:
            # "If you want to get the entity for a *cached* username, you should first `get_input_entity(username)
            # <get_input_entity>` which will use the cache), and then use `get_entity` with the result of the previous
            # call."
            try:
                if self.parsable.lstrip('-').isdigit():
                    self.parsable = int(self.parsable)
                self.input_entity = self.get_input_entity_offline(self.parsable)
                self.id = int('-100' + str(self.input_entity.channel_id))
                logger.debug(f'Inferred input entity {self.input_entity} from parsable {self.parsable}')
            except ValueError:
                # TODO: if there is nothing after parseable and we do not know what is the type of parseable, below will fail
                pass

        if restore_values:
            if not (self.id is None and self.link is None):  # here we do not do any difference for public and private
                # old values may still be useful. Example: we knew link and ID but session got lost. The session can
                # be refreshed if link is still working
                self._restore_from_cache()

            # TODO: maybe launch once in a while to refresh values if there are remaining calls for today?
            # TODO: let get_entity work with any input and extract id, link and name after?
            # TODO: optimize
            # TODO: add 'update_date' to the storage
            # no link and public=True - infer
            # no link and private=False - no infer
            # no link and unk=None - infer
            random_float = random.random()
            if random_float < CHANNEL_RESTORE_REQUEST_PROB:
                logger.info(f"Performing a random channel restoration with a probability of {CHANNEL_RESTORE_REQUEST_PROB}")
                self._restore_via_request()
            else:
                if self.force_update \
                        or self.id is None \
                        or self.name is None \
                        or (self.link is None and (self.is_public != False)):
                    self._restore_via_request()

        # if self.id is None and self.link is None:
            # raise ValueError(f'Either id or link has to be provided to specify a channel\n{self}')
            # logger.error(f'Either id or link has to be provided to specify a channel\n{self}')

        # below is not true as most of communications may be performed using ID only.
        # Private channels don't have link at all
        # if self.id is None and self.name is None and self.link is None:
        #     raise ValueError(f"not able to use {self}")

    # await self._client._get_entity_from_string(x)

    def _restore_via_request(self):
        if self._client is None:
            raise ValueError(f'TelegramClient has to be passed to perform a force update. {self.__repr__()}')

        if self.input_entity or self.parsable:  # perform request using parsable/input entity (a bit better than call everything from scratch)
            if self.input_entity:
                entity = self.input_entity
            elif self.parsable:
                entity = self.parsable

            logger.info(f'Performing a force update using entity for {self!r}')
            entity = asyncio.get_event_loop().run_until_complete(get_entity(self._client, entity))
            self.id = asyncio.get_event_loop().run_until_complete(get_channel_id(self._client, entity))
            self.link = asyncio.get_event_loop().run_until_complete(
                get_channel_link(self._client, entity))  # doesn't work without nesting
        else:  # perform the heaviest request
            if self.link is not None:
                self.link = check_channel_link_correctness(self.link)
                entity = asyncio.get_event_loop().run_until_complete(get_entity(self._client, self.link))
                self.id = asyncio.get_event_loop().run_until_complete(get_channel_id(self._client, entity))
            elif self.id is not None:
                # entity = asyncio.get_event_loop().run_until_complete(get_entity(self._client, self.id))  # TODO: do we need this here as entity is created in the same way inside get_channel_link
                # self.link = asyncio.get_event_loop().run_until_complete(get_channel_link(self._client, entity))
                self.link = asyncio.get_event_loop().run_until_complete(get_channel_link(self._client, self.id))

        if self.id is None:  # TODO: add some better solution for empty channel
            # logger.error(f'{self. __repr__()} may be not a channel but a user. Not implemented scenario. Otherwise this may be just nothing')
            pass
        else:
            self.name = asyncio.get_event_loop().run_until_complete(get_display_name(self._client, entity))

            if self.link is None:
                self.is_public = False
            else:
                self.is_public = True

            logger.info(f"Restored {self. __repr__()} via request")
            channels = get_channels(restore_values=False)
            update_channels(channels, self)

    def get_input_entity_offline(self, peer: EntityLike) -> InputPeerChannel:
        """
        It's a simplified copy of the get_input_entity function from telethon.client.users file. This is created
        to reduce the number of API calls. If input entity is not restorable from cache, the full entity will be
        requested, not a reduced version. This information will be stored in cache via call + information specific
        for smartfeed will be fetched.

        # unfortunately, this get_input_entity also performs an API call while returning a cut version of the entity.
        #     # moreover, it registers the entity in cache.
        #     # if we don't have this ID in cache, we will call the API twice - for ID and for all the fields once again

        If the entity can't be found, ``ValueError`` will be raised.

        Parameters
        ----------
        client
        peer

        Returns
        -------

        """
        from telethon.utils import get_input_peer

        # Short-circuit if the input parameter directly maps to an InputPeer
        try:
            return get_input_peer(peer)
        except TypeError:
            pass

        # Next in priority is having a peer (or its ID) cached in-memory
        try:
            # 0x2d45687 == crc32(b'Peer')
            if isinstance(peer, int) or peer.SUBCLASS_OF_ID == 0x2d45687:
                return self._client._entity_cache[peer]
        except (AttributeError, KeyError):
            pass

        # Then come known strings that take precedence
        if peer in ('me', 'self'):
            return InputPeerSelf()

        # No InputPeer, cached peer, or known string. Fetch from disk cache
        try:
            return self._client.session.get_input_entity(peer)
        except ValueError:
            pass

        raise ValueError(
            'Could not find the input entity for {} of type {}. Please read https://'
            'docs.telethon.dev/en/stable/concepts/entities.html to'
            ' find out more details.'.format(peer, type(peer).__name__)
        )

    def _restore_from_cache(self):
        """
        Fully overwrites Channel fields if there is a local match via id or link (in this priority).
        Name is not used as a source of truth as it's not unique.

        Returns
        -------

        """
        channels = get_channels(restore_values=False)

        id_match, link_match = [], []
        for ch in channels:
            if self.id is not None and ch.id == self.id:
                id_match.append(ch)
            elif self.link is not None and ch.link == self.link:  # for private channels link is None
                logger.info(f'Found cached link while not having ID passed: {ch}')
                link_match.append(ch)

        matches = id_match + link_match
        if len(matches) == 0:
            logger.error(f"{self!r} not found in cache")
        else:
            cached_channel = matches[0]
            self.id = cached_channel.id
            self.name = cached_channel.name
            self.link = cached_channel.link
            self.is_public = cached_channel.is_public  # we may not know if the channel if public knowing only fragments
            logger.log(5, f"Restored {self!r} from cache")

    def __eq__(self, other):
        """Overrides the default implementation"""
        # TODO: probably check both id, name, link fields to update potentially
        if isinstance(other, Channel):
            return (self.id == other.id) and (self.name == other.name) and (self.link == self.link)
        return False

    def __str__(self):
        # TODO: consider something more readable. To show to user?
        # return f"""Channel(id={self.id}, name="{self.name}", link="{self.link}", public={self.is_public})"""
        if self.link is not None:
            return self.link.replace('https://t.me/', '@')
        elif self.name is not None:
            return self.name
        else:
            return str(self.id)

    def __repr__(self):
        return f"""Channel(id={self.id}, name="{self.name}", link="{self.link}", public={self.is_public})"""

    def __hash__(self):
        return hash(self.id)


# TODO: check that it's a link
def check_channel_link_correctness(channel_link: str) -> str:
    """
    Checks the correctness of the channel name

    :param channel_link:
    :return:
    """
    channel_link_before = channel_link
    channel_link = channel_link.replace("@", "https://t.me/")
    if channel_link.find("https://t.me/") == -1:
        channel_link = channel_link.replace("t.me/", "https://t.me/")
    if channel_link.find("https://t.me/") == -1:
        # return "error"
        raise ValueError(f"Channel of inappropriate format: {channel_link}")
    if channel_link_before != channel_link:
        logger.debug(f"Checked link: '{channel_link_before}' -> '{channel_link}'")

    return channel_link


async def get_entity(client, entity):
    # TODO: process get entity via the same func for all get_* and catch errors
    try:
        entity = await client.get_entity(entity)
        return entity
    except ChannelPrivateError:
        logger.debug(
            f'Failed to get_entity due to ChannelPrivateError')
        return None
    except FloodWaitError as e:
        logger.info(f'Got FloodWaitError cause by ResolveUsernameRequest. Have to sleep {e.seconds} seconds / {e.seconds / 60:.1f} minutes / '
                    f'{e.seconds / 60 / 60:.1f} hours')
        # time.sleep(e.seconds)
        raise
    except:
        logger.error(f'Failed to get_entity with client:\n{await client.get_me()}\nand entity of type {type(entity)}:\n{entity}', exc_info=True)
        return None
        # raise
    # TODO: catch ValueError("Could not find any entity corresponding to") for all get_*. occurs when searching by name


async def get_display_name(client: TelegramClient, entity):
    # TODO: replace empty to None?
    # TODO: try to call the func only from Channel - this gives a chance to restore
    # https://stackoverflow.com/questions/61456565/how-to-get-the-chat-or-group-name-of-incoming-telegram-message-using-telethon
    """
    ``client`` and ``entity`` are as documented in `get_channel_link`
    """
    # logger.debug('Getting entity in get_display_name')
    entity = await get_entity(client, entity)
    if entity is None:
        return None
    else:
        return tutils.get_display_name(entity)  # works also for users' names


async def get_channel_link(client: TelegramClient, entity):
    # TODO: vectorize
    """
        for string it makes a request, for id it only makes one there was stored access_hash in session.
        relevant chats and users are sent with events, if you don't have it in cache, it won't make a request and
        fail locally.

        :param client: works both with bot and personal clients TODO check bot
        :param entity (`str` | `int` | :tl:`Peer` | :tl:`InputPeer`):
                    If a username or invite link is given, **the library will
                    use the cache**. This means that it's possible to be using
                    a username that *changed* or an old invite link (this only
                    happens if an invite link for a small group chat is used
                    after it was upgraded to a mega-group).
                    If the username or ID from the invite link is not found in
                    the cache, it will be fetched. The same rules apply to phone
                    numbers (``'+34 123456789'``) from people in your contact list.
                    If an exact name is given, it must be in the cache too. This
                    is not reliable as different people can share the same name
                    and which entity is returned is arbitrary, and should be used
                    only for quick tests.
                    If a positive integer ID is given, the entity will be searched
                    in cached users, chats or channels, without making any call.
                    If a negative integer ID is given, the entity will be searched
                    exactly as either a chat (prefixed with ``-``) or as a channel
                    (prefixed with ``-100``).
                    If a :tl:`Peer` is given, it will be searched exactly in the
                    cache as either a user, chat or channel.
                    If the given object can be turned into an input entity directly,
                    said operation will be done.
                    Unsupported types will raise ``TypeError``.
                    If the entity can't be found, ``ValueError`` will be raised.
        :return:
        """
    logger.debug('Getting entity in get_channel_link')
    entity = await get_entity(client, entity)
    if entity is None:
        return None
    else:
        if hasattr(entity, 'username'):
            if entity.username is None:
                # logger.error(f'Channel {entity} has None .username field')
                logger.warning(f'Channel {entity.id} has None .username field')
                return None
            return f"https://t.me/{entity.username}"


async def get_channel_id(client: TelegramClient, entity) -> int:
    # TODO: add get_user_id func?
    """
        ``client`` and ``entity`` are as documented in `get_channel_link`
        """
    # works with channel link, name, integer ID (with and without -100).
    # doesn't work with str ID
    # only for user API
    if isinstance(entity, str) and entity.lstrip('-').isdigit():
        entity = int(entity)
    logger.debug('Getting input entity in get_channel_id')
    entity = await client.get_input_entity(entity)
    return int('-100' + str(entity.channel_id))


def save_channels(channels_list: List[Channel]):
    root = get_project_root()
    path = os.path.join(root, CHANNEL_CACHE_FILEPATH)

    with open(path, 'w') as f:
        json.dump({str(ch.id): {"username": ch.name, "invite_link": ch.link, 'is_public': ch.is_public} for ch in
                   channels_list}, f)
        logger.debug('saved channels cache')


def update_channels(channels_list: List[Channel], target_ch: Channel, add_not_remove=True):
    """


    Parameters
    ----------
    channels_list
    target_ch
    add_not_remove

    Returns
    -------

    """
    # TODO: simplify logic
    if add_not_remove:
        if target_ch not in channels_list:  # firstly, check by full match
            if target_ch.id in [ch.id for ch in channels_list]:
                old_ch = [ch for ch in channels_list if ch.id == target_ch.id][0]
                channels_list.remove(old_ch)
                channels_list.append(target_ch)
                logger.info(
                    f'Cached {target_ch}\ninstead of outdated {old_ch}\nNow have {len(channels_list)} channels cached')
            else:
                channels_list.append(target_ch)
                logger.info(
                    f'Cached a new {target_ch}. Now have {len(channels_list)} channels cached')
            save_channels(channels_list)
        else:
            logger.log(7, f'Tried to cache already cached {target_ch}')
    else:
        channels_list = [c for c in channels_list if c != target_ch]
        save_channels(channels_list)

    return channels_list


def get_channels(restore_values=True):
    """
    get_entity is a shortcut for GetUsers or in your case GetChannels, it takes a list of InputChannel,
    the id goes to channel_id, but access_hash is what matters. if can't be found in session; request won't be sent.

    You need to have the access_hash stored by yourself if you must delete session file, you can also pass
    get_entity(inputChannel(id, hash)) to skip session check

    :return:
    """
    root = get_project_root()
    path = os.path.join(root, CHANNEL_CACHE_FILEPATH)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            # "id" : {"username": username, "invite_link": invite_link}.
            data = {int(ch_id): v for ch_id, v in json.load(f).items()}  # a la deserializer
    else:
        return None

    channels = [Channel(channel_id=ch_id, channel_name=v['username'], channel_link=v['invite_link'],
                        is_public=v['is_public'], restore_values=restore_values) for ch_id, v in data.items()]
    return channels
