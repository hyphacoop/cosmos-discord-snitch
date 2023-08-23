# cosmos-discord-snitch

A Discord bot that messages a channel when new evidence is found in a Cosmos consumer chain.

![We're all trying to find the guy who did this meme gif](images/whodidthis.webp)

## Features

- The consensus address is used to retrieve the validator moniker from the provider chain.
- All evidence data is saved to a local JSON file.

## Requirements

- python 3.10+
- A Cosmos binary that supports evidence queries using the `--node` flag (e.g. `strided`)
- A binary for each of the consumer chains to parse consensus addresses.

## Installation

1. Install Python dependencies:
   
```
cosmos-discord-snitch$ python -m venv .env
cosmos-discord-snitch$ source .env/bin/activate
cosmos-discord-snitch$ pip install -r requirements.txt
```

2. Create a Discord bot
3. Invite the bot to the relevant channel
4. Add the bot token and channel ID to `config-discord.toml`
5. Enter the API and RPC endpoints for the chains you want to monitor in `config-evidence.toml`

## How to Use

- Run `python cosmos_discord_snitch`, or
- modify `cosmos-discord-snitch.service` and install the service.





