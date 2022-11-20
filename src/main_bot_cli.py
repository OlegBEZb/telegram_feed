import asyncio

from telethon import events, types, Button
import telethon.utils as tutils

import config

import logging

from src import bot_client, CLI_COMMANDS, ADMIN_COMMANDS, START_MESSAGE, ABOUT_MESSAGE, FEEDBACK_MESSAGE
from src.utils import check_channel_correctness, list_to_str_newline, get_channel_link, get_user_display_name
from src.bot_cli_utils import add_to_channel
from src.database_utils import get_users, update_user, save_users, get_feeds

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

import bot_menu_handlers
bot_client.start(bot_token=config.bot_token)
logger.info('bot started')


# needed to catch all kinds of events related to bots because for some reason these events are
# not covered well with standard methods
# @bot_client.on(events.Raw)
# async def handler(update):
#     # Print all incoming updates
#     print(update.stringify())


@bot_client.on(events.Raw(types.UpdateChannelParticipant))
# ChannelParticipant, ChannelParticipantSelf, ChannelParticipantCreator, ChannelParticipantAdmin, ChannelParticipantBanned, ChannelParticipantLeft
async def update_channel_participant(event):
    channel_id = int('-100' + str(event.channel_id))
    if event.new_participant:
        # TODO: decide with chat_id types: int or str
        if isinstance(event.new_participant, types.ChannelParticipantAdmin) and event.new_participant.user_id == config.bot_id:
            logger.info(f"Bot is added as admin at '{channel_id}' due to '{event.actor_id}'s action")

            users = get_users()
            users = update_user(users, event.actor_id, channel_id, add_not_remove=True)
            save_users(users)

    elif event.prev_participant:
        if isinstance(event.prev_participant, types.ChannelParticipantAdmin) and event.prev_participant.user_id == config.bot_id:
            logger.info(f"Bot is no longer an admin at '{channel_id}' due to '{event.actor_id}'s action")

            users = get_users()
            users = update_user(users, event.actor_id, channel_id, add_not_remove=False)
            save_users(users)
            # TODO: remove related records from the DB (feeds, etc.)


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
            help_text += "/help: User-friendly menu with buttons\n\n"
        help_text += cmd + ": "
        help_text += help_descr[1] + "\n\n"
    help_text += FEEDBACK_MESSAGE
    await bot_client.send_message(sender_id, help_text)
    logger.debug(f"Sent help_text to {await get_user_display_name(bot_client, int(sender_id))} ({sender_id})")


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
        await command_help_text(event)  # show the new user the help page
        logger.info(f"New user {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) started the bot")
    else:
        await bot_client.send_message(sender_id, "You are already in the user list")


@bot_client.on(events.CallbackQuery(data=b"/about"))
@bot_client.on(events.NewMessage(pattern='/about'))
async def command_about(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    await bot_client.send_message(sender_id, f'{ABOUT_MESSAGE}\n\n{FEEDBACK_MESSAGE}')
    logger.debug(f"Sent about to {await get_user_display_name(bot_client, int(sender_id))} ({sender_id})")


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
        await event.reply(f"Was not able to process the argument. Check /help once again:\n{CLI_COMMANDS['/channel_info'][1]}")
        logger.error(f"User {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) failed in command_channel_info", exc_info=True)
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
        await event.reply(f"Your reading list of {len(reading_list)} item(s) (sorted chronologically):\n{list_to_str_newline(reading_list)}")
    logger.debug(f"{await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) called /channel_info")


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
    logger.debug(f"{await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) called /my_channels")


@bot_client.on(events.NewMessage(pattern='/users'))
async def admin_command_users(event):
    if not isinstance(event.chat, types.User):
        return
    sender_id = event.chat_id
    if int(sender_id) != config.my_id:
        await event.reply("You are not allowed to perform this action")
        return
    users = get_users()
    if len(users) == 0:
        await event.reply("You don't have any yet")
    else:
        # TODO: add the number of channels per user
        user_names = [await get_user_display_name(bot_client, int(u)) for u in users]
        rows = [f"{name:.<18} ({user_id}) - {len(channels):.>5} channel(s)" for name, user_id, channels in zip(user_names, users, users.values())]
        await event.reply(f"Your {len(users)} user(s) (sorted chronologically):\n{list_to_str_newline(rows)}")


@bot_client.on(events.NewMessage)  # UpdateNewMessage
async def echo_all(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        return
    message = event.message
    cmd = message.text.split()[0]
    if cmd not in dict(CLI_COMMANDS, **ADMIN_COMMANDS) and cmd != '/help':
        # await event.reply("This is an unrecognized command. Use /help to list all available commands")
        logger.error(f"User {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) called an unrecognized command\n{message.text}", exc_info=True)


@bot_client.on(events.NewMessage(pattern='/send_all'))
async def admin_command_send_all(event):
    sender_id = event.chat_id
    if int(sender_id) != config.my_id:
        await event.reply("You are not allowed to perform this action")
        return

    message = event.message
    _, message = message.text.split("/send_all")

    users = get_users()

    async with bot_client.conversation(event.sender_id, timeout=60) as conv:
        try:
            await conv.send_message(f"Are you sure about sending this to {len(users)} user(s)?",
                                    buttons=Button.force_reply())
            msg = await conv.get_reply()
            if not msg.text:
                await event.reply("You can only set a text message!")
                return
            if msg.text != '+':
                return
            await conv.send_message('Your input is processed well', buttons=Button.clear())
        except asyncio.exceptions.TimeoutError:
            await event.reply("Timeout for adding a source channel. Press the button once again")
            logger.error(f"User ({sender_id}) faced a timeout in adding a source channel to add")
            return

    users = ["194124545"]  #, "5790168960", "249830866"]
    for user in users:
        await bot_client.send_message(int(user), message.strip())
        print('sent to', user)
    logger.debug(f"Sent a general message to users: {users}")


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
        await event.reply("Was not able to add channel. Check if your destination channel is public and the bot is added as admin")
        logger.error(f"User {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) failed to perform /add_to_channel with the following command: \"{message.text[:100]}\"", exc_info=True)


bot_client.run_until_disconnected()
