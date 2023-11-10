import asyncio
import os

from telethon import events, types, TelegramClient
from telethon.tl.functions.channels import CheckUsernameRequest, UpdateUsernameRequest
from telethon.tl.types import InputPeerChannel
from telethon.events import StopPropagation
from telethon.errors.rpcerrorlist import (PasswordTooFreshError, UsernameInvalidError, PasswordHashInvalidError,
                                          SessionTooFreshError, UsernamePurchaseAvailableError)

import config

import logging

from src.common.utils import list_to_str_newline
from src.common.get_project_root import get_project_root
from src.common.database_utils import (get_users, update_users, save_users, get_feeds, delete_users_channel)
from src.common.channel import Channel, get_display_name, update_channels, get_channels
from src.common.decorators import check_direct

from src.bot.admin.admin_utils import ADMIN_USER_IDS
from src.bot.bot_utils import add_to_channel, get_answer_in_conv, get_users_channel_links
from src.bot import bot_client, CLI_COMMANDS, ADMIN_COMMANDS, START_MESSAGE, ABOUT_MESSAGE, FEEDBACK_MESSAGE

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

# TODO: switch to context manager
bot_client.start(bot_token=config.bot_token)
for func, event in bot_client.list_event_handlers():
    print(func.__name__, event.Event)
logger.info('bot started')

# user_client_for_bot_cli_path = os.path.join(get_project_root(), 'src/user_client_for_bot_cli')
user_client_for_bot_cli_path = os.path.join(get_project_root(), 'src/telefeed_client')
user_client_for_bot_cli = TelegramClient(user_client_for_bot_cli_path,
                                         config.api_id,
                                         config.api_hash)  # !? has to be the same client which creates channels for private channels due to channel ID


# needed to catch all kinds of events related to bots because for some reason these events are
# not covered well with standard methods
# @bot_client.on(events.Raw)
# async def handler(update):
#     # Print all incoming updates
#     print(update.stringify())


# TODO: find the owner of a chat and assign to him? or to every admin. and every admin will be recorded and counted
#  if the user added the bot to a channel, this doesn't mean that it's this user's channel.
#  for example when we add this for user
# @bot_client.on(events.Raw(types.UpdateChannelParticipant))
# async def update_channel_participant(event):
#     logger.info('Triggered update_channel_participant')
#     # TODO: resolve creator and owner of the channel
#     channel_id = int('-100' + str(event.channel_id))  # apply utils.get_channel_id
#     users = get_users()
#     if event.new_participant:
#         if isinstance(event.new_participant,
#                       types.ChannelParticipantAdmin) and event.new_participant.user_id == config.bot_id:
#             logger.info(f"Bot is added as admin at '{channel_id}' due to {await get_display_name(bot_client, int(event.actor_id))}({event.actor_id})'s action")
#
#             users = update_user(users, event.actor_id, channel_id, add_not_remove=True)
#
#     elif event.prev_participant:
#         if isinstance(event.prev_participant,
#                       types.ChannelParticipantAdmin) and event.prev_participant.user_id == config.bot_id:
#             logger.info(f"Bot is no longer an admin at '{channel_id}' due to {await get_display_name(bot_client, int(event.actor_id))}({event.actor_id})'s action")
#
#             users = update_user(users, event.actor_id, channel_id, add_not_remove=False)
#             # TODO: remove related records from the DB (feeds, etc.)
#
#     save_users(users)


# TODO: find a proper way of escaping
@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/help_text'][0].replace('(', '\(').replace(')', '\)')))
@bot_client.on(events.CallbackQuery(data=b"/help_text"))
@bot_client.on(events.NewMessage(pattern='/help_text'))
@check_direct
async def command_help_text(event):
    sender_id = event.chat_id

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


# @bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/start'][0]))
@bot_client.on(events.CallbackQuery(data=b"/start"))
# @bot_client.on(events.CallbackQuery(pattern=b"/start"))  # works as well
# @bot_client.on(events.CallbackQuery(pattern=r"/start"))  # works as well
@bot_client.on(events.NewMessage(pattern='/start'))
@check_direct
async def command_start(event):
    sender_id = event.chat_id

    await bot_client.send_message(sender_id, START_MESSAGE)
    users = get_users()
    if sender_id not in users:  # if user hasn't used the "/start" command yet:
        users[sender_id] = []
        save_users(users)
        await command_menu(event)  # TODO: move to be used after any result - before stop propagation
        logger.info(f"New user {await get_display_name(bot_client, int(sender_id))} ({sender_id}) started the bot")
    else:
        await bot_client.send_message(sender_id, "You are already in the user list")
        logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /start")
    raise StopPropagation


# @bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/about'][0]))
@bot_client.on(events.CallbackQuery(data=b"/about"))
@bot_client.on(events.NewMessage(pattern='/about'))
@check_direct
async def command_about(event):
    sender_id = event.chat_id

    await bot_client.send_message(sender_id, f'{ABOUT_MESSAGE}\n\n{FEEDBACK_MESSAGE}')
    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /about")
    raise StopPropagation


@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/my_channels'][0]))
@bot_client.on(events.CallbackQuery(data=b"/my_channels"))
@bot_client.on(events.NewMessage(pattern='/my_channels'))
@check_direct
async def command_my_channels(event):  # callback function
    sender_id = event.chat_id

    users_channels_links = await get_users_channel_links(event)
    if users_channels_links:
        await event.reply(f"Your channels (sorted chronologically):\n{list_to_str_newline(users_channels_links)}")

    logger.debug(f"{await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /my_channels")
    raise StopPropagation


@bot_client.on(events.CallbackQuery(pattern='/channel_info'))  # with argument, pattern or data makes the difference
@bot_client.on(events.NewMessage(pattern='/channel_info'))
@check_direct
async def command_channel_info(event):
    sender_id = event.chat_id

    if isinstance(event.original_update, types.UpdateNewMessage):
        message = event.message.text
    elif isinstance(event.original_update, types.UpdateBotCallbackQuery):  # or types.UpdateBot...
        message = event.data.decode('utf-8')  # according to the doc

    try:
        # _, dst_ch_link = message.split()
        # TODO: from the user we expect only link but in general entity is recognised from different kinds of types.
        #  Private channels may be accessed only via name
        #  The same has to be applied in channel constructor.
        #  A slightly changed but correct link will trigger cache update
        parsable = message[message.startswith('/channel_info') and len('/channel_info '):]
        async with user_client_for_bot_cli:
            logger.debug(f'Trying channel_info with parsable: {parsable}')
            dst_ch = Channel(parsable, client=user_client_for_bot_cli)
    except:
        await event.reply(
            f"Was not able to process the argument. Check /help once again:\n{CLI_COMMANDS['/channel_info'][1]}")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed in command_channel_info",
            exc_info=True)
        return

    users = get_users()
    if dst_ch.id not in users[sender_id]:
        await event.reply("You are not allowed to perform this action")
        return

    feeds = get_feeds()
    reading_list = feeds[dst_ch.id]
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
@check_direct
async def command_add_to_channel(event):  # callback function
    sender_id = event.chat_id

    try:
        _, src_ch_parsable, dst_ch_parsable = event.message.text.split()
        dst_ch = Channel(parsable=dst_ch_parsable, client=bot_client)
        src_ch = Channel(parsable=src_ch_parsable, client=bot_client)
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


# TODO: simplify
@bot_client.on(events.NewMessage(pattern=CLI_COMMANDS['/create_channel'][0]))
@bot_client.on(events.NewMessage(pattern='/create_channel'))
@check_direct
async def command_create_channel(event):
    sender_id = event.chat_id

    users = get_users()
    if (len(users[sender_id]) >= 5) and (sender_id not in ADMIN_USER_IDS):
        await event.reply("You are not allowed to have more than 5 channels so far")
        return

    try:
        new_channel_name = await get_answer_in_conv(event, "How would you like to title a channel "
                                                           "(name visible in the dialogs)?", timeout=300)
        new_channel_about = await get_answer_in_conv(event,
                                                     "Send me the new 'About' text. People will see this text on the "
                                                     "bot's profile page and it will be sent together with a link to "
                                                     "your bot when they share it with someone.", timeout=600)
    except asyncio.exceptions.TimeoutError:
        await command_menu(event)
        return
    except:
        logger.error('Not able to parse user\'s input during channel creation', exc_info=True)
        await command_menu(event)

    from src.bot.bot_utils import create_channel, transfer_channel_ownership
    async with user_client_for_bot_cli:
        creation_result = await create_channel(client=user_client_for_bot_cli, channel_title=new_channel_name,
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

        logger.info(f"New channel '{new_channel_name}' ({new_channel_id}) is created for {await get_display_name(bot_client, int(sender_id))} ({sender_id})")
        while True:  # TODO: reduct to some non-infinite number of attempts?
            try:
                desired_public_name = await get_answer_in_conv(
                    event,
                    "Do you want the channel to be public or private? If private, just reply to this "
                    "message with '**private**'. If you want a public channel, then you need to reply "
                    "with a desired name (so-called public link or username). "
                    "This channel name will be used in https://t.me/**your_public_name** "
                    "and @**your_public_name**",
                    timeout=300)
                if desired_public_name == 'private':
                    new_channel_link = None
                    await bot_client.send_message(sender_id, f"Congratulations! Private channel "
                                                             f"'{new_channel_name}' is created. Now you can find it "
                                                             "in the 'All Chats' Telegram folder")
                    break
                async with user_client_for_bot_cli:
                    logger.debug(f"Checking username request with new_channel_id {new_channel_id} and "
                                 f"desired_public_name {desired_public_name}")
                    try:
                        check_channel_name_result = await user_client_for_bot_cli(CheckUsernameRequest(
                            InputPeerChannel(channel_id=new_channel_id,
                                             access_hash=new_channel_access_hash), desired_public_name))
                    except UsernamePurchaseAvailableError:
                        logger.debug(f'{await get_display_name(bot_client, int(sender_id))} ({sender_id}) tried to '
                                     f"create a public channel but the name '{desired_public_name}' is non-free")
                        await bot_client.send_message(sender_id, "This channel name is available only for purchase"
                                                                 " on fragment.com. Try again")
                        continue
                    if check_channel_name_result:
                        update_response = await user_client_for_bot_cli(UpdateUsernameRequest(
                            InputPeerChannel(channel_id=new_channel_id, access_hash=new_channel_access_hash),
                            desired_public_name))
                        if not update_response:
                            raise ValueError("Was not able to make the channel public")
                        logger.debug(f'{await get_display_name(bot_client, int(sender_id))} ({sender_id}) '
                                     f"created a public channel with the name 'https://t.me/{desired_public_name}'")
                        await bot_client.send_message(sender_id, f"Congratulations! Public channel "
                                                                 f"@{desired_public_name} is created. Now you can find "
                                                                 f"it in the 'All Chats' Telegram folder")
                        new_channel_link = f'https://t.me/{desired_public_name}'
                        break
                    else:
                        logger.debug(f'{await get_display_name(bot_client, int(sender_id))} ({sender_id}) tried to '
                                     f"create a public channel but the name '{desired_public_name}' is already taken")
                        await bot_client.send_message(sender_id, "This channel name is already taken. Try again")
            except asyncio.exceptions.TimeoutError:
                await command_menu(event)
                return
            except UsernameInvalidError:
                await bot_client.send_message(sender_id, "Nobody is using this username, or the username is "
                                                         "unacceptable. If the latter, it must match "
                                                         "r\"[a-zA-Z][\w\d]{3,30}[a-zA-Z\d]\"")
            except:
                logger.error('Not able to parse user\'s input during public/private naming', exc_info=True)

        # at the end of the communication, the menu is sent anyway
        await command_menu(event)

    # TODO: make a func from it?
    async with user_client_for_bot_cli:
        try:
            new_channel_id = int('-100' + str(new_channel_id))

            # Adding bot to the channel to be able to post to it
            await user_client_for_bot_cli.edit_admin(entity=new_channel_id, user=config.bot_id, is_admin=True)
            logger.info(f"Bot is added as admin at '{new_channel_id}' automatically")
            users = update_users(users_dict=users, channel_id=new_channel_id, user=sender_id, add_not_remove=True)
            save_users(users)

            # before a successful ownership transfer, the channel is still not user's but mine
            if sender_id != config.my_id:
                await transfer_channel_ownership(client=user_client_for_bot_cli, channel_id=new_channel_id, to_user_id=sender_id)

            channels = get_channels(restore_values=False)
            if desired_public_name == 'private':
                public = False
            else:
                public = True
            new_ch = Channel(channel_link=new_channel_link, channel_name=new_channel_name, channel_id=new_channel_id,
                             is_public=public)
            update_channels(channels, new_ch)

            # TODO: drop myself from the channel ONLY if the channel is public. Otherwise history filtering is impossible

            # raise StopPropagation  # to avoid calling update_channel_participant
        except SessionTooFreshError:
            logger.error('Your session has to be older than 24 hours to perform ownership transfer')
        except PasswordHashInvalidError:
            logger.error('Password is not working', exc_info=True)
        except PasswordTooFreshError:
            logger.error('You have just refreshed the password. One week cold period is ongoing', exc_info=True)


@bot_client.on(events.NewMessage(pattern='/delete_channel'))
@check_direct
async def command_delete_channel(event):  # callback function
    sender_id = event.chat_id

    if isinstance(event.original_update, types.UpdateNewMessage):
        message = event.message.text
    elif isinstance(event.original_update, types.UpdateBotCallbackQuery):  # or types.UpdateBot...
        message = event.data.decode('utf-8')  # according to the doc

    try:
        parsable = message[message.startswith('/delete_channel') and len('/delete_channel '):]
        async with user_client_for_bot_cli:
            target_ch = Channel(parsable=parsable, client=user_client_for_bot_cli)
    except:
        await event.reply(
            f"Was not able to process the argument. Check /menu once again:\n{CLI_COMMANDS['/delete_channel'][1]}")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed in command_delete_channel",
            exc_info=True)
        return

    # TODO: open for everyone. Now only admins can perform this action. Users should be able to do this only with their channels
    if sender_id not in [config.my_id, 194124545]:
        users = get_users()
        if target_ch.id not in users[sender_id]:
            await event.reply("You are not allowed to perform this action")
            return

    try:
        await delete_users_channel(event=event, channel=target_ch, clients=[user_client_for_bot_cli, bot_client])
    except:
        await event.reply(
            "Was not able to remove channel")
        logger.error(
            f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) failed to perform /delete_channel with the following command: \"{message.text[:100]}\"",
            exc_info=True)


@bot_client.on(events.NewMessage)  # UpdateNewMessage
async def echo_all(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        return
    message = event.message
    if len(message.text) > 0:
        cmd = message.text.split()[0]
        if cmd not in dict(CLI_COMMANDS, **ADMIN_COMMANDS) and cmd != '/help':
            # await event.reply("This is an unrecognized command. Use /help to list all available commands")
            if sender_id not in [config.my_id, 194124545]:
                logger.error(
                    f"User {await get_display_name(bot_client, int(sender_id))} ({sender_id}) called an unrecognized command\n{message.text}",
                    exc_info=True)



from src.bot.admin.admin_command_handlers import send_stats
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import tzlocal
from apscheduler.triggers.cron import CronTrigger
logging.getLogger('apscheduler').setLevel(logging.INFO)
scheduler = AsyncIOScheduler(misfire_grace_time=3599, coalesce='latest', timezone=str(tzlocal.get_localzone()))  # job is allowed to be 1 hour late and if was missed for several days, will be launched once
if not scheduler.running:  # Clause suggested by @CyrilleMODIANO
    scheduler.start()
scheduler.add_job(func=send_stats, trigger=CronTrigger(minute='0', hour='23', timezone=str(tzlocal.get_localzone())))
# from apscheduler.triggers.combining import OrTrigger
# trigger = OrTrigger([
#    CronTrigger(hour='7', minute='30-59'),
#    CronTrigger(hour='8-22', minute='*/2'),
#    CronTrigger(hour='23', minute='0-30')
# ])

bot_client.run_until_disconnected()
