from timeit import default_timer as timer
from discord.ext import commands
import discord
from datetime import datetime
import configparser
import asyncio
import sqlite3
import logging
import random
import time
import csv
import sys
import os


startup_begin = timer()

if not os.path.exists("./configs/config.ini"):
    print("No config file can be found in ./configs/.")
    sys.exit("No config found.")


config = configparser.ConfigParser()
config.read(os.path.abspath("./config.ini"))
admin_role_names = config["Credentials"]["admin_role_names"]
bot_token = config["Credentials"]["bot_token"]
cmd_prefix = config["Misc"]["command_prefix"]
mute_role_name = config["Misc"]["mute_role_name"]
delete_messages_after = config["Misc"]["delete_messages_after"]
listen_channels = config["Misc"]["listen_channels"]

admin_role_lists = admin_role_names.split(",")
listen_channels_list = listen_channels.split(",")

if admin_role_lists[0] == "":
    print("You must specify administrative roles for this bot.")
    sys.exit("No admin roles defined.")

bot = commands.Bot(command_prefix=cmd_prefix)


@bot.event
async def on_ready():
    logger.debug("Start of on_ready()")
    global warn_count_lockout

    warn_count_lockout = []
    logger.info(f"CPSBot is ready, took {timer() - bot_beginning_time}s.")


@bot.event
async def on_message(msg):
    if msg.guild is None:
        return

    logger.debug("Message received from {0.name}#{0.discriminator} in {1.guild}, #{1.channel.name}."
                 .format(msg.author, msg))

    author_obj = msg.author
    author_is_admin = False
    for admin_role in admin_role_lists:
        if admin_role in author_obj.roles:
            author_is_admin = True

    if not author_is_admin:
        return

    logger.info(f'Command sent by "{msg.author.name}#{msg.author.discriminator}": "{msg.content}."')

    bot.process_commands(msg)


@bot.command()
async def warn(ctx, target_user_id, search_depth, delete_found_messages, should_mute=True, *, reason: str):
    '''This command is used to warn users for breaching the rules, the bot will automatically apply the mute-role
    to the user defined by target_user_id unless instructed otherwise with: "should_mute=False" defined. Everything
    after the first three arguments: "target_user_id, search_depth and delete_found_messages" will be taken to be part
    of the "reason" argument, "reason" must ALWAYS be the final argument defined in this command and is programmatically
    optional, but it is always advised you enter a reason for warning a user.'''

    # Need to get user object for user of given ID.
    target_user = discord.utils.get(ctx.message.guild.members, id=int(target_user_id))
    if target_user is None:
        logger.info("Warn command failed: Could not find user from ID.")
        await ctx.send("")


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

if not os.path.exists("./warn_logs/"):
    os.mkdir("./warn_logs/")
    logger.info("Generated ./warn_logs/ directory.")
if not os.path.exists("./stored_user_messages/"):
    os.mkdir("./stored_user_messages/")
    logger.info("Generated ./stored_user_messages/ directory.")

bot_beginning_time = timer()
bot.run(bot_token)
