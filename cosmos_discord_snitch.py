"""
Sets up a bot to send a message to a Discord channel
whenever new evidence is available in any of the
configured consumer chains.
"""

import logging
import sys
import toml
import discord
from discord.ext import commands, tasks
from evidence_checker import EvidenceChecker

EVIDENCE_CONFIG='config-evidence.toml'
DISCORD_CONFIG='config-discord.toml'

with open(DISCORD_CONFIG, "r") as config_toml:
    config = toml.load(config_toml)

try:
    CHECK_INTERVAL=int(config['check_interval'])
    DISCORD_TOKEN=str(config['bot_token'])
    DISCORD_CHANNEL=int(config['channel_id'])
except KeyError as key_err:
    logging.critical('Key could not be found: %s', key_err)
    sys.exit()

# Turn on info logging
logging.basicConfig(
filename=None,
level=logging.INFO,
format="%(asctime)s %(levelname)s %(message)s",
datefmt="%Y-%m-%d %H:%M:%S",
)

client = discord.Client(intents=discord.Intents.default())
checker = EvidenceChecker(EVIDENCE_CONFIG)

def format_deltas(eqs: list):
    """
    Returns a code block with all the key/value pairs per dict in the list
    """
    output='```\n'
    for eq in eqs:
        output+='---\n'
        for key, value in eq.items():
            output+=f'{key}: {value}\n'
    output+='```'
    return output

@tasks.loop(seconds=CHECK_INTERVAL)
async def update_evidence():
    """
    Updates the evidence every CHECK_INTERVAL seconds.
    """
    updates = checker.get_evidence_updates()
    if updates:
        for chain in updates:
            message = f'New equivocations recorded for chain {chain["chain_id"]}:\n{format_deltas(chain["updates"])}'
            channel = client.get_channel(DISCORD_CHANNEL)
            await channel.send(message)

@client.event
async def on_ready():
    update_evidence.start()

client.run(DISCORD_TOKEN)
