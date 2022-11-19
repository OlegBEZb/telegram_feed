from telethon import TelegramClient

from src import config

bot_client = TelegramClient('bot', config.api_id, config.api_hash)

NO_ARG_CLI_COMMANDS = {
    # command: [button_name, help_descr]
    '/start': ["start", "Registers the users and sends the greetings message"],

    '/help_text': ["textual help (CLI)",
                   'Gives you information about the available commands in text.'],

    '/about': ["about", "Sends the detailed description of the project and its usage"],

    '/my_channels': ["show my channels",
                     "This command shows all your channels which fetch updates from this bot"],
}
ARG_CLI_COMMANDS = {'/channel_info': ["show channel info",
                                      (
                                          "This command shows source channels for one of your channels. "
                                          "This command requires 1 argument "
                                          "from you: link to your channel."
                                          "\nExample: /channel_info t.me/your_destination_channel")],

                    # make an n-step procedure with the first command "config bog"
                    '/add_to_channel': ["add source channel to my channel",
                                        (
                                            "This command adds a new source channel which content will be redirected to your channel."
                                            " This command requires 2 arguments from you: what channel to add and where to add. These two"
                                            " arguments are both links to telegram channels."
                                            "\nExample: /add_to_channel t.me/channel_of_interest t.me/your_destination_channel")], }

CLI_COMMANDS = dict(NO_ARG_CLI_COMMANDS, **ARG_CLI_COMMANDS)

ADMIN_COMMANDS = {
    '/users': 'Lists users',
    '/send_all': ''
}
