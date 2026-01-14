# Telegram Service Monitor Bot

## Overview
A Telegram bot that monitors the health status of multiple services and updates a dashboard message in a Telegram channel.

## Project Structure
- `bot.py` - Main bot script using Pyrogram library
- `requirements.txt` - Python dependencies

## Dependencies
- **pyrogram** - Telegram MTProto API client
- **tgcrypto** - Cryptography library for Pyrogram performance
- **aiohttp** - Async HTTP client for service health checks

## Environment Variables Required
The following secrets need to be configured:
- `API_ID` - Telegram API ID (from my.telegram.org)
- `API_HASH` - Telegram API Hash (from my.telegram.org)
- `BOT_TOKEN` - Bot token from @BotFather
- `CHANNEL_ID` - Telegram channel ID for the dashboard message
- `MESSAGE_ID` - ID of the message to update with status

## Configuration
The `SERVICES` dictionary in `bot.py` defines the services to monitor. Each entry is:
```python
"Service Name": "https://service.example.com/health"
```

## Running the Bot
Run with `python bot.py`. The bot will:
1. Connect to Telegram using the provided credentials
2. Check all configured service health endpoints every 30 seconds
3. Update the dashboard message in the specified channel

## Recent Changes
- 2026-01-14: Initial import and Replit environment setup
- Updated to use environment variables for credentials
- Fixed requirements.txt to list actual dependencies (pyrogram instead of aiogram)
