import configparser
import json
import logging
import os
import sys
import time
from datetime import datetime
from timeit import default_timer as timer

import discord
from discord.ext import commands

startup_begin = timer()

if not os.path.exists("./configs/config.ini"):
    print("No config file can be found in ./configs/.")
    sys.exit("No config found.")


config = configparser.ConfigParser()
config.read(os.path.abspath("./configs/config.ini"))
admin_role_names = config["Credentials"]["admin_role_names"]
bot_token = config["Credentials"]["bot_token"]
cmd_prefix = "££"  # COMMAND PREFIX IS HERE FOR EDITING PURPOSES, UNICODE WAS BEING A FUCK SO THAT'S WHY IT'S HERE
mute_role_name = config["Misc"]["mute_role_name"]
student_role_name = config["Misc"]["student_role_name"]
delete_messages_after = config["Misc"]["delete_messages_after"]
listen_channels = config["Misc"]["listen_channels"]

admin_role_list = admin_role_names.split(",")
listen_channels_list = listen_channels.split(",")

if admin_role_list[0] == "":
    print("You must specify administrative roles for this bot.")
    sys.exit("No admin roles defined.")

bot = commands.Bot(command_prefix=cmd_prefix, pm_help=True)


@bot.event
async def on_ready():
    logger.debug("Start of on_ready()")
    global warn_count_lockout

    warn_count_lockout = []
    logger.info(f"CPSBot is ready, took {timer() - bot_beginning_time:.3f}s.")


@bot.event
async def on_message(msg):

    logger.debug(str(msg.content.startswith(msg.content.split()[0])))
    logger.debug(str(msg.content.startswith(cmd_prefix)))
    logger.debug(cmd_prefix)

    if msg.guild is None:
        return

    if not msg.content.startswith(cmd_prefix):
        return

    logger.debug("Message received from {0.name}#{0.discriminator} in {1.guild}, #{1.channel.name}."
                 .format(msg.author, msg))

    author_obj = msg.author
    author_is_admin = False
    for admin_role in author_obj.roles:
        if admin_role.name in admin_role_list:
            author_is_admin = True

    if not author_is_admin:
        return

    logger.info(f'Command sent by "{msg.author.name}#{msg.author.discriminator}": "{msg.content}."')

    await bot.process_commands(msg)


@bot.command(name="warn")
async def warn(ctx, target_user_mention, search_depth: int, delete_found_messages: bool, should_mute: bool, *,
               reason: str):
    '''This command is used to warn users for breaching the rules, the bot will automatically apply the mute-role
    to the user defined by target_user_id unless instructed otherwise with: "should_mute=False".

    target_user_mention is a mention of the command's target
    search_depth is an integer type that tells the bot how many messages back to search every channel it can see in the server.
    delete_found_messages is a boolean (True/False) that tells the bot whether or not to delete any messages sent by the target that it finds.
    should_mute is a boolean that tells the bot whether or not it should mute the target user.
    reason is a string type that is used on audit logs where possible and is given to the target by the bot where it explains what they did wrong.'''

    warn_command_start = timer()

    # Need to get user object for user of given ID.
    target_user = await commands.MemberConverter().convert(ctx, target_user_mention)
    if target_user is None:
        logger.info("Warn command failed: Could not find user from mention.")
        await ctx.send("Command failed: could not find user by given mention.", delete_after=delete_messages_after)
        return

    if reason == "":
        reason = "No reason given."

    try:
        search_depth = int(search_depth)
        delete_found_messages = bool(delete_found_messages)
        should_mute = bool(should_mute)
    except TypeError:
        await ctx.send("Command failed: could not convert argument to correct type.")

    if not reason.endswith("."):  # Make everything look nice
        reason += "."

    # Before this command embarks on a journey of discovering all the garbage posted by the target, let's see if
    # they're meant to be muted.
    if should_mute:
        mute_role = await commands.RoleConverter().convert(ctx, mute_role_name)
        student_role = await commands.RoleConverter().convert(ctx, student_role_name)
        await target_user.add_roles(mute_role, reason=reason+f" Requested by {ctx.message.author.name}.")
        await target_user.remove_roles(student_role, reason=reason+f" Requested by {ctx.message.author.name}.")
        logger.info(f"Added mute_role to {target_user.display_name}. Requested by {ctx.message.author.name}.")

    target_message_content_list = []
    found_messages_count = 0

    async with ctx.message.channel.typing():  # Show the command invoker that the bot is doing something
        message_scrape_timer = timer()
        for channel in ctx.message.guild.text_channels:
            async for message in channel.history(limit=search_depth):
                if message.author.id == target_user.id:
                    found_messages_count += 1
                    if message.attachments:
                        message_attach_dir_list = []
                        for attachment in message.attachments:
                            attachment_filename = str(message.author.id)+"_"+attachment.filename
                            with open("./carcinogenic_pictures/"+str(message.id)+"_"+attachment_filename, "w+b") as \
                                    attachment_file:
                                try:
                                    await attachment.save(attachment_file)
                                    message_attach_dir_list.append("./carcinogenic_pictures/" + str(message.id)+"_" +
                                                                   attachment_filename)
                                except discord.NotFound:
                                    logger.info(f"Could not find file: {attachment_filename}, message was deleted.")
                                logger.debug(f"Saved file with name {attachment_filename} in ./carcinogenic_pictures/")

                        target_message_content_list.append({"id": message.id,
                                                            "timestamp": message.created_at.strftime("%Y-%m-%d_%H-%M-%S"),
                                                            "contents": message.content, "channel": message.channel.id,
                                                            "has_attachment": True,
                                                            "attachment_dir": message_attach_dir_list})
                    else:
                        target_message_content_list.append({"id": message.id,
                                                            "timestamp": message.created_at.strftime(
                                                                "%Y-%m-%d_%H-%M-%S"),
                                                            "contents": message.content, "channel": message.channel.id,
                                                            "has_attachment": False,
                                                            "attachment_dir": []})
                    if delete_found_messages:
                        await message.delete()
        logger.debug(f"Finished compiling target message history in {timer() - message_scrape_timer} seconds.")

        with open(f"./stored_user_messages/{str(target_user.id)}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json",
                  "w") as json_f:
            json.dump(target_message_content_list, json_f, indent=4)

    await ctx.send(f"User: {target_user.display_name} has been warned, found {str(found_messages_count)} messages, "
                   f"handled according to command instructions.", delete_after=delete_messages_after)

    warning_message = f'__**You have been warned by `{ctx.author.display_name}` for: "{reason}"**__\n\n'

    if delete_found_messages:
        warning_message += f'This bot found {str(found_messages_count)} messages sent by you, they have now been ' \
                           f'logged and deleted from the Discord server. '
    else:
        warning_message += f'This bot found {str(found_messages_count)} messages sent by you, they have now been ' \
                           f'logged for administrative purposes. '

    if should_mute:
        warning_message += f'You have also lost the permission to type in the {ctx.guild.name} Discord server, ' \
                           f'administrators will be in contact soon regarding when you will regain this permission.'

    warning_message += f'\n\n**DEPENDING ON THE SEVERITY OF THIS INFRACTION, YOU MAY LOSE ACCESS TO THE DISCORD ' \
                       f'SERVER AND THE OPPORTUNITY TO PARTICIPATE IN SOCIETY ACTIVITIES.**'

    await target_user.send(content=warning_message)

    logger.debug(f"Finished running warn command in {timer() - warn_command_start}s.")


# Begin logging
print("Logging startup...")
time.sleep(0.1)
if not os.path.exists("./logs/"):
    os.mkdir("./logs/")
logger = logging.getLogger("CPSBot")
logger.setLevel(logging.INFO)
logger_start_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
formatter = logging.Formatter("[{asctime}] [{levelname:}] [{threadName:}] {name}: {message}",
                              "%Y-%m-%d %H:%M:%S", style="{")
file_log = logging.FileHandler(f"./logs/CPSbot{logger_start_time}.log", encoding="utf-8", mode="w")
console_log = logging.StreamHandler()
file_log.setFormatter(formatter)
console_log.setFormatter(formatter)
logger.addHandler(file_log)
logger.addHandler(console_log)
logger.info(f"Configured base in {(timer() - startup_begin):.3f} seconds, running rest of startup.")

if not os.path.exists("./stored_user_messages/"):
    os.mkdir("./stored_user_messages/")
    logger.info("Generated ./stored_user_messages/ directory.")
if not os.path.exists("./carcinogenic_pictures/"):
    os.mkdir("./carcinogenic_pictures/")
    logger.info("Generated ./carcinogenic_pictures/ directory.")

if delete_messages_after == "":
    delete_messages_after = None
else:
    try:
        delete_messages_after = int(delete_messages_after)
    except ValueError:
        logger.error("delete_messages_after variable in config.ini can not be converted to int type.")
        sys.exit("Improper type in config option: delete_messages_after.")

bot_beginning_time = timer()
bot.run(bot_token)
