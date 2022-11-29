from telethon import events, types, Button
import telethon.utils as tutils
from telethon.events import StopPropagation

import config

import logging

from src.bot import bot_client, CLI_COMMANDS, ADMIN_COMMANDS, START_MESSAGE, ABOUT_MESSAGE, FEEDBACK_MESSAGE
from src.common.utils import check_channel_correctness, list_to_str_newline, get_channel_link, get_display_name
from src.bot.bot_cli_utils import add_to_channel
from src.common.database_utils import get_users, update_user, save_users, get_feeds

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
    channel_id = int('-100' + str(event.channel_id))
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
    if str(sender_id) not in users:  # if user hasn't used the "/start" command yet:
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
        _, dst_ch = message.split()
        dst_ch = check_channel_correctness(dst_ch)
    except:
        await event.reply(
            f"Was not able to process the argument. Check /help once again:\n{CLI_COMMANDS['/channel_info'][1]}")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed in command_channel_info",
            exc_info=True)
        return

    # dst_ch_id = get_channel_id(bot, dst_ch)
    entity = await bot_client.get_input_entity(dst_ch)
    dst_ch_id = tutils.get_peer_id(entity)

    users = get_users()
    if dst_ch_id not in users[str(sender_id)]:
        await event.reply("You are not allowed to perform this action")
        return

    feeds = get_feeds()
    reading_list = feeds[dst_ch]
    if not reading_list:
        await event.reply("Your reading list is empty")
    else:
        await event.reply(
            f"Your reading list of {len(reading_list)} item(s) (sorted chronologically):\n{list_to_str_newline(reading_list)}")
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /channel_info")


@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/my_channels'][0]))
@bot_client.on(events.CallbackQuery(data=b"/my_channels"))
@bot_client.on(events.NewMessage(pattern='/my_channels'))
async def command_my_channels(event):  # callback function
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    users = get_users()
    users_channels = users[str(sender_id)]
    if len(users_channels) == 0:
        await event.reply("You haven't added the bot to any of your channels yet")
    else:
        users_channels_links = [await get_channel_link(bot_client, ch) for ch in users_channels]
        await event.reply(f"Your channels (sorted chronologically):\n{list_to_str_newline(users_channels_links)}")
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /my_channels")
    raise StopPropagation


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


@bot_client.on(events.NewMessage(pattern='/add_to_channel'))
async def command_add_to_channel(event):  # callback function
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    try:
        message = event.message
        await add_to_channel(message.text, sender_id)
    except:
        await event.reply(
            "Was not able to add channel. Check if your destination channel is public and the bot is added as admin")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed to perform /add_to_channel with the following command: \"{message.text[:100]}\"",
            exc_info=True)


bot_client.run_until_disconnected()
