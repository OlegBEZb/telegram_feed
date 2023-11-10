import datetime
import re
from copy import deepcopy
import logging

from telethon.errors import ChatWriteForbiddenError
from telethon.extensions import html
from telethon.tl.patched import Message
from telethon.tl.types import MessageActionGroupCall, MessageActionPinMessage, MessageActionGroupCallScheduled, \
    MessageMediaInvoice

from src import config
from src.common.channel import Channel
from src.common.database_utils import get_last_bot_id, save_last_bot_ids

logger = logging.getLogger(__name__)


MSG_POSTFIX_TEMPLATE = ("\n\n\n<em>Original post link: {post_link}</em>\n"
                        "<em>Forwarded and filtered by @smartfeed_bot</em>")  # powered by?
SIGNATURE_REGEX = re.compile(r"\n+@[a-z_]+\n*$")


def format_forwarded_msg_as_original(msg: Message, orig_channel: Channel, original_msg_id) -> Message:
    """
    Formats a forwarded message to appear as if it were sent from the original channel.

    Parameters
    ----------
    msg : Message
        The message to be formatted.
    orig_channel : Channel
        The original channel from which the message was forwarded.
    original_msg_id : int
        The ID of the original message in the original channel.

    Returns
    -------
    Message
        The message object after formatting as if it was sent from the original channel.

    """
    try:
        # without that copying doesn't work (serialisation issue) as _client is a complicated structure
        msg._client = None
        if msg._forward:
            msg._forward._client = None
        new_msg = deepcopy(msg)
    except:
        logger.error(f'Unable to remove clients from message\n{msg.stringify()}')
        return None

    post_link = create_post_reference_link(orig_channel, original_msg_id)

    # Remove the original channel signature and append the custom postfix.
    new_msg.message = remove_original_channel_signature(new_msg.message)
    postfix = MSG_POSTFIX_TEMPLATE.format(post_link=post_link)
    new_msg.message += postfix

    new_msg = update_entities(new_msg)

    return new_msg


def create_post_reference_link(orig_channel, original_msg_id):
    if orig_channel.is_public == True:
        post_link = f"{orig_channel.link.replace('https://t.me/', 't.me/')}/{original_msg_id}"
    elif orig_channel.is_public == False:
        post_link = f't.me/c/{orig_channel.id}/{original_msg_id}'  # TODO: replace with invite?
    else:
        post_link = 'unknown'
    return post_link


def update_entities(new_msg):
    # TODO: check as some links disappear after this step
    text, extra_entities = html.parse(new_msg.message)
    new_msg.message = text
    if new_msg.entities is None:
        new_msg.entities = extra_entities
    else:
        new_msg.entities += extra_entities

    return new_msg


def remove_original_channel_signature(message: str):
    """
    # TODO: consider moving this action to the filtering stage as well to be less dependent on copypasted material
    # replaces other channel signature at the end of the message (should be without entities)
    # but anyway MessageEntityMention remains. Is this a problem?

    Parameters
    ----------
    message : str
        The message from which to remove the signature.

    Returns
    -------
    str
        The message without the original channel signature.
    -------

    """
    # TODO: check potential bug of a removed link at the end of the post below
    #  Доклад
    #
    # @ai_newz
    #


    # TODO: extend the regex to match post signatures like this
    # Post
    #
    # 👉@computer_science_and_programming
    # TODO: extend the regex to match post signatures with hashed like this
    #  Post
    #
    #  https://t.me/+Qm9PbhU6Lf0h5wsm
    return SIGNATURE_REGEX.sub("", message)


async def ensure_media_access(msg, user_client, bot_client, orig_channel_id):
    """
    Ensures that media can be accessed by forwarding the message to a bot and syncing the last message ID.

    Parameters
    ----------
    msg : Message
        The message containing the media.
    user_client : telethon.TelegramClient
        The user client instance.
    bot_client : telethon.TelegramClient
        The bot client instance.
    orig_channel_id : int
        The ID of the original channel.

    Returns
    -------
    Message
        The message object after ensuring media access.

    """
    async def sync_bot_last_msg_id():
        # logger.error('Bot chat with the user is out of sync. Syncing')

        now = datetime.datetime.now(datetime.timezone.utc)
        diff_seconds = 999999
        tolerance = 10
        last_msg = None

        last_expected_id = get_last_bot_id()
        last_actual_id = last_expected_id
        while diff_seconds > 60 or tolerance > 0:
            last_expected_id += 1
            tolerance -= 1

            bot_from_user_msg = await bot_client.get_messages(config.my_id, ids=last_expected_id)  # in debug mode failed with 'NoneType' object has no attribute 'my_id'
            if bot_from_user_msg:
                # print(i, bot_from_user_msg.date)
                # print(bot_from_user_msg)
                last_actual_id = last_expected_id
                last_msg = bot_from_user_msg
                diff_seconds = (now - last_msg.date).seconds

                # we always check 10 next messages after the existing one
                tolerance = 10


        if last_actual_id % 5 == 0:
            logger.info(f'Last id and UTC date in the bot chat: {last_actual_id}, {last_msg.date}')
        save_last_bot_ids(last_actual_id)
        return last_msg, last_actual_id

    if msg.media is not None:
        async with user_client:
            bot_entity = await user_client.get_input_entity(config.bot_id)
            await user_client.forward_messages(entity=bot_entity, messages=msg, from_peer=orig_channel_id)
        async with bot_client:
            # bot_last_id = get_last_bot_id() + 1  # as we have just sent another one
            # msg = await bot_client.get_messages(config.my_id, ids=bot_last_id)
            # if msg:
            #     save_last_bot_ids(bot_last_id)
            # else:
            #     msg, last_actual_id = await sync_bot_last_msg_id()  # it's a force sync of the bot chat
            msg, last_actual_id = await sync_bot_last_msg_id()  # for debugging
    return msg


async def msg_is_action(msg, client, from_peer, peer_to_forward_to):
    try:
        async with client:
            # TODO: check if regular messages have action. Looks like not
            if isinstance(msg.action, (MessageActionGroupCall, MessageActionGroupCall)):
                if msg.action.duration is None:
                    logger.info(f"{from_peer!r} started a call")
                    await client.send_message(peer_to_forward_to, f"{from_peer} started a call")
                else:
                    logger.info(f"{from_peer} ended a call")
                    await client.send_message(peer_to_forward_to, f"{from_peer} ended a call")
                return True
            if isinstance(msg.action, MessageActionPinMessage):
                logger.info(f"{from_peer!r} pinned a message")
                await client.send_message(peer_to_forward_to, f"{from_peer} pinned a message")
                return True
            if isinstance(msg.action, MessageActionGroupCallScheduled):
                logger.info(f"{from_peer!r} scheduled a group call")
                await client.send_message(peer_to_forward_to, f"{from_peer} scheduled a group call at {msg.action.schedule_date} UTC")
                return True
            return False
    except ChatWriteForbiddenError:
        logger.error(f"{await client.get_me()} can't forward from {from_peer!r} to {peer_to_forward_to} "
                     f"(caused by ForwardMessagesRequest)")  # add the owner as well


async def msg_is_invoice(msg, client, from_peer, peer_to_forward_to):
    try:
        async with client:
            if isinstance(msg.invoice, MessageMediaInvoice):
                logger.info(f"{from_peer!r} posten an invoice")
                await client.send_message(peer_to_forward_to, f"{from_peer} requests money with the following title: "
                                                              f"{msg.invoice.title}")
                return True
            return False
    except ChatWriteForbiddenError:
        logger.error(f"{await client.get_me()} can't forward from {from_peer!r} to {peer_to_forward_to} "
                     f"(caused by ForwardMessagesRequest)")  # add the owner as well
