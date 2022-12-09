from telethon import events, types, Button, TelegramClient
from telethon.tl.functions.channels import CheckUsernameRequest, UpdateUsernameRequest
from telethon.tl.types import InputPeerChannel
from telethon.events import StopPropagation
from telethon.errors.rpcerrorlist import PasswordTooFreshError, UsernameInvalidError, PasswordHashInvalidError, SessionTooFreshError

import config

import logging

from src.bot import bot_client, CLI_COMMANDS, ADMIN_COMMANDS, START_MESSAGE, ABOUT_MESSAGE, FEEDBACK_MESSAGE
from src.common.utils import check_channel_link_correctness, list_to_str_newline, get_display_name
from src.bot.bot_utils import add_to_channel, get_answer_in_conv, get_users_channel_links

from src.common.database_utils import get_users, update_user, save_users, get_feeds, Channel

logging.basicConfig(
    # filename="BotClient.log",
    format='%(asctime)s %(module)s %(levelname)s: %(message)s',
    level=logging.DEBUG,
    datefmt='%a %d.%m.%Y %H:%M:%S',
    force=True)
logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logging.getLogger('telethon').setLevel(logging.WARNING)

# TODO: move to a separate file and dynamically add to the list of handlers like in
# https://github.com/Lonami/TelethonianBotExt

# do not remove import! handlers have to be initialized
from src.bot.bot_menu_handlers import command_menu
import src.bot.admin_command_handlers

bot_client.start(bot_token=config.bot_token)
for func, event in bot_client.list_event_handlers():
    print(func.__name__, event.Event)
logger.info('bot started')


# needed to catch all kinds of events related to bots because for some reason these events are
# not covered well with standard methods
# @bot_client.on(events.Raw)
# async def handler(update):
#     # Print all incoming updates
#     print(update.stringify())


@bot_client.on(events.Raw(types.UpdateChannelParticipant))
async def update_channel_participant(event):
    channel_id = int('-100' + str(event.id))  # apply utils.get_channel_id
    if event.new_participant:
        # TODO: decide with chat_id types: int or str
        if isinstance(event.new_participant,
                      types.ChannelParticipantAdmin) and event.new_participant.user_id == config.bot_id:
            logger.info(f"Bot is added as admin at '{channel_id}' due to '{event.actor_id}'s action")

            users = get_users()
            users = update_user(users, event.actor_id, channel_id, add_not_remove=True)
            save_users(users)

    elif event.prev_participant:
        if isinstance(event.prev_participant,
                      types.ChannelParticipantAdmin) and event.prev_participant.user_id == config.bot_id:
            logger.info(f"Bot is no longer an admin at '{channel_id}' due to '{event.actor_id}'s action")

            users = get_users()
            users = update_user(users, event.actor_id, channel_id, add_not_remove=False)
            save_users(users)
            # TODO: remove related records from the DB (feeds, etc.)


# TODO: find a proper way of escaping
@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/help_text'][0].replace('(', '\(').replace(')', '\)')))
@bot_client.on(events.CallbackQuery(data=b"/help_text"))
@bot_client.on(events.NewMessage(pattern='/help_text'))
async def command_help_text(event):
    sender_id = event.chat_id
    if not event.is_private:  # make a wrapper
        await event.reply(
            "Contact me in PM to get the help menu",
            buttons=[[Button.url("Click me for help!", config.bot_url)]],
        )
        return

    help_text = "The following commands are available: \n"
    for cmd, help_descr in CLI_COMMANDS.items():  # generate help text out of the commands dictionary defined at the top
        if cmd == '/help_text':
            help_text += "/menu: User-friendly menu with buttons\n\n"
        help_text += cmd + ": "
        help_text += help_descr[1] + "\n\n"
    help_text += FEEDBACK_MESSAGE
    await bot_client.send_message(sender_id, help_text)
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /help_text")
    raise StopPropagation


@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/start'][0]))
@bot_client.on(events.CallbackQuery(data=b"/start"))
# @bot_client.on(events.CallbackQuery(pattern=b"/start"))  # works as well
# @bot_client.on(events.CallbackQuery(pattern=r"/start"))  # works as well
@bot_client.on(events.NewMessage(pattern='/start'))
async def command_start(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    await bot_client.send_message(sender_id, START_MESSAGE)
    users = get_users()
    if sender_id not in users:  # if user hasn't used the "/start" command yet:
        users[sender_id] = []
        save_users(users)
        await command_menu(event)
        logger.info(f"New user {await get_display_name(bot_client, int(sender_id))} ({sender_id}) started the bot")
    else:
        await bot_client.send_message(sender_id, "You are already in the user list")
        logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /start")
    raise StopPropagation


@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/about'][0]))
@bot_client.on(events.CallbackQuery(data=b"/about"))
@bot_client.on(events.NewMessage(pattern='/about'))
async def command_about(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    await bot_client.send_message(sender_id, f'{ABOUT_MESSAGE}\n\n{FEEDBACK_MESSAGE}')
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /about")
    raise StopPropagation


@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/my_channels'][0]))
@bot_client.on(events.CallbackQuery(data=b"/my_channels"))
@bot_client.on(events.NewMessage(pattern='/my_channels'))
async def command_my_channels(event):  # callback function
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    users_channels_links = await get_users_channel_links(event)
    if users_channels_links is not None:
        await event.reply(f"Your channels (sorted chronologically):\n{list_to_str_newline(users_channels_links)}")

    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /my_channels")
    raise StopPropagation


@bot_client.on(events.CallbackQuery(pattern='/channel_info'))  # with argument, pattern or data makes the difference
@bot_client.on(events.NewMessage(pattern='/channel_info'))
async def command_channel_info(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    if isinstance(event.original_update, types.UpdateNewMessage):
        message = event.message.text
    elif isinstance(event.original_update, types.UpdateBotCallbackQuery):  # or types.UpdateBot...
        message = event.data.decode('utf-8')  # according to the doc

    try:
        _, dst_ch_link = message.split()
        # TODO: from the user we expect only link but in general entity is recognised from different kinds of types. The same has to be applied in channel constructor. A slightli changed but correct link will trigger cache update
        # dst_ch_id = await get_channel_id(bot_client, dst_ch)
        dst_ch_link = check_channel_link_correctness(dst_ch_link)
        dst_ch = Channel(channel_link=dst_ch_link, client=bot_client)
        dst_ch_id = dst_ch.id
    except:
        await event.reply(
            f"Was not able to process the argument. Check /help once again:\n{CLI_COMMANDS['/channel_info'][1]}")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed in command_channel_info",
            exc_info=True)
        return

    users = get_users()
    if dst_ch_id not in users[sender_id]:
        await event.reply("You are not allowed to perform this action")
        return

    feeds = get_feeds()
    reading_list = feeds[dst_ch_id]
    if not reading_list:
        await event.reply("Your reading list is empty")
    else:
        reading_list_links = []
        for ch_id in reading_list:
            ch = Channel(channel_id=ch_id, client=bot_client)
            reading_list_links.append(ch.link)
        await event.reply(
            f"Your reading list of {len(reading_list)} item(s) (sorted chronologically):\n{list_to_str_newline(reading_list_links)}")
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /channel_info")


@bot_client.on(events.NewMessage(pattern='/add_to_channel'))
async def command_add_to_channel(event):  # callback function
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    # TODO: change signature of add to channel. check arguments here and pass already checked to the func
    try:
        _, src_ch_link, dst_ch_link = event.message.text.split()
        dst_ch = Channel(channel_link=dst_ch_link, client=bot_client)
        src_ch = Channel(channel_link=src_ch_link, client=bot_client)
    except:
        await event.reply(
            f"Was not able to process the argument. Check /help once again:\n{CLI_COMMANDS['/channel_info'][1]}")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed in command_channel_info",
            exc_info=True)
        return

    message = event.message
    try:
        await add_to_channel(src_ch=src_ch, dst_ch=dst_ch, sender_id=sender_id)
    except:
        await event.reply(
            "Was not able to add channel. Check if your destination channel is public and the bot is added as admin")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed to perform /add_to_channel with the following command: \"{message.text[:100]}\"",
            exc_info=True)


# @bot_client.on(events.NewMessage(pattern='/create_channel'))
async def command_create_channel(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    users = get_users()
    if len(users[sender_id]) > 5:
        await event.reply("You are not allowed to have more than 5 channels so far")
        return

    try:
        new_channel_name = await get_answer_in_conv(event, "How would you like to title a channel (name visible in the dialogs)?", timeout=300)
        new_channel_about = await get_answer_in_conv(event,
                                                     "Send me the new 'About' text. People will see this text on the "
                                                     "bot's profile page and it will be sent together with a link to "
                                                     "your bot when they share it with someone.", timeout=600)
    except:
        logger.error('Not able to parse user\'s input during channel creation', exc_info=True)
        await command_menu(event)

    from src.bot.bot_utils import create_channel, transfer_channel_ownership
    user_client = TelegramClient('telefeed_client', config.api_id, config.api_hash)
    async with user_client:
        creation_result = await create_channel(client=user_client, channel_title=new_channel_name,
                                               about=new_channel_about, supergroup=False)  # ask about supergroup?

    if creation_result.chats is None:
        logger.error('Did not create a channel')
        bot_client.send_message(sender_id, "Was not able to create a channel")
        await command_menu(event)
        return
    else:
        # https://stackoverflow.com/questions/52160946/telethon-how-to-create-a-public-private-channel
        new_channel_id = creation_result.chats[0].id
        new_channel_access_hash = creation_result.chats[0].access_hash

        logger.info(f"New channel {new_channel_name} ({new_channel_id}) is created for {await get_display_name(bot_client, int(sender_id))} ({sender_id})")
        while True:
            try:
                desired_public_name = await get_answer_in_conv(event,
                                                               "Do you want the channel to be public or private? If private, just reply to this "
                                                               "message with 'private'. If you want a public channel, then you need to reply "
                                                               "with a desired name. This channel name will be used in https://t.me/**your_public_name** "
                                                               "and @**your_public_name**", timeout=300)
                if desired_public_name == 'private':
                    break
                async with user_client:
                    check_channel_name_result = await user_client(CheckUsernameRequest(
                        InputPeerChannel(channel_id=new_channel_id,
                                         access_hash=new_channel_access_hash), desired_public_name))
                    if check_channel_name_result:
                        update_response = await user_client(UpdateUsernameRequest(
                            InputPeerChannel(channel_id=new_channel_id,
                                             access_hash=new_channel_access_hash), desired_public_name))
                        logger.debug(f'{await get_display_name(bot_client, int(sender_id))} ({sender_id}) '
                                     f"created a public channel with the name 'https://t.me/{desired_public_name}'")
                        await bot_client.send_message(sender_id, f"Congratulations! Public channel "
                                                                 f"@{desired_public_name} is created")
                        break
                    else:
                        logger.debug(f'{await get_display_name(bot_client, int(sender_id))} ({sender_id}) tried to '
                                     f"create a public channel but the name '{desired_public_name}' is already taken")
                        await bot_client.send_message(sender_id, "This channel name is already taken. Try again")
            except UsernameInvalidError:
                bot_client.send_message(sender_id, """Nobody is using this username, or the username is unacceptable. If the latter, it must match r"[a-zA-Z][\w\d]{3,30}[a-zA-Z\d]"
                """)
            except:
                logger.error('Not able to parse user\'s input during channel creation', exc_info=True)

    async with user_client:
        try:
            await transfer_channel_ownership(client=user_client, channel_id=new_channel_id, to_user_id=sender_id)
            # before a successful ownership transfer, the channel is still not user's but mine
            users = update_user(users, sender_id, new_channel_id, add_not_remove=True)
            save_users(users)
        except SessionTooFreshError:
            logger.error('Your session has to be older than 24 hours to perform ownership transfer')
        except PasswordHashInvalidError:
            logger.error('Password is not working', exc_info=True)
        except PasswordTooFreshError:
            logger.error('You have just refreshed the password. One week cold period is ongoing', exc_info=True)


@bot_client.on(events.NewMessage)  # UpdateNewMessage
async def echo_all(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        return
    message = event.message
    cmd = message.text.split()[0]
    if cmd not in dict(CLI_COMMANDS, **ADMIN_COMMANDS) and cmd != '/help':
        # await event.reply("This is an unrecognized command. Use /help to list all available commands")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) called an unrecognized command\n{message.text}",
            exc_info=True)


bot_client.run_until_disconnected()
