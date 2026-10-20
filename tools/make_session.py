"""Run this ONCE on your own computer to create the TG_SESSION secret.

    pip install telethon
    python tools/make_session.py

It asks for api_id, api_hash, the phone number and the login code (and the 2FA password if set).
The printed string gives full access to that Telegram account: store it only as a GitHub secret.
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("api_id: ").strip())
api_hash = input("api_hash: ").strip()
with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nTG_SESSION (SECRET - never commit or share it):\n")
    print(client.session.save())
