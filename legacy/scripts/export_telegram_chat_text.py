#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from telethon import TelegramClient, errors
    from telethon.tl.types import Channel, Chat, User
    from telethon.tl.types import PeerChannel, PeerChat, PeerUser
except ImportError:  # pragma: no cover - dependency is optional at repo level
    TelegramClient = None
    errors = None
    Channel = Chat = User = None
    PeerChannel = PeerChat = PeerUser = None


DEFAULT_SESSION = "telegram_takeout"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "generated" / "telegram_exports"


@dataclass
class ExportStats:
    scanned: int = 0
    written: int = 0
    skipped_empty: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export text messages from a Telegram chat through MTProto takeout. "
            "The first launch is interactive and will ask for your login code."
        )
    )
    parser.add_argument(
        "--chat",
        required=False,
        help="Chat identifier: username, invite link, phone, numeric id, or exact dialog title.",
    )
    parser.add_argument(
        "--api-id",
        type=int,
        default=int(os.environ["TG_API_ID"]) if os.environ.get("TG_API_ID") else None,
        help="Telegram API ID. Defaults to TG_API_ID from the environment.",
    )
    parser.add_argument(
        "--api-hash",
        default=os.environ.get("TG_API_HASH"),
        help="Telegram API hash. Defaults to TG_API_HASH from the environment.",
    )
    parser.add_argument(
        "--session",
        default=DEFAULT_SESSION,
        help=(
            "Telethon session file name or path. Defaults to "
            f"'{DEFAULT_SESSION}' in the current working directory."
        ),
    )
    parser.add_argument(
        "--output",
        help=(
            "Output file path. Defaults to generated/telegram_exports/<chat>.jsonl "
            "inside this repo."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["jsonl", "txt"],
        default="jsonl",
        help="Output format. JSONL keeps metadata; TXT is easier to read.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of messages to export. Defaults to all messages.",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Export from oldest to newest. By default exports newest to oldest.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Keep service or media-only messages even when they have no text body.",
    )
    parser.add_argument(
        "--no-takeout",
        action="store_true",
        help="Export through a normal MTProto session instead of takeout.",
    )
    parser.add_argument(
        "--list-chats",
        action="store_true",
        help="List available dialogs with their ids and exit.",
    )
    return parser.parse_args()


def require_dependencies() -> None:
    if TelegramClient is not None:
        return
    print(
        "Telethon is not installed. Install it first:\n"
        "  python3 -m pip install telethon",
        file=sys.stderr,
    )
    raise SystemExit(1)


def build_output_path(chat: str, output: str | None, fmt: str) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", chat).strip("._") or "chat"
    return (DEFAULT_OUTPUT_DIR / f"{slug}.{fmt}").resolve()


def dialog_label(entity: Any) -> str:
    return getattr(entity, "title", None) or getattr(entity, "username", None) or getattr(
        entity, "first_name", None
    ) or "unknown"


def dialog_kind(entity: Any) -> str:
    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Channel):
        return "channel" if getattr(entity, "broadcast", False) else "supergroup"
    if isinstance(entity, Chat):
        return "group"
    return type(entity).__name__


def candidate_numeric_ids(entity: Any) -> set[int]:
    raw_id = getattr(entity, "id", None)
    if raw_id is None:
        return set()

    ids = {int(raw_id)}
    if isinstance(entity, Channel):
        ids.add(int(f"-100{raw_id}"))
    elif isinstance(entity, Chat):
        ids.add(-int(raw_id))
    return ids


async def resolve_entity(client: Any, chat_ref: str) -> Any:
    normalized = chat_ref.strip()
    if re.fullmatch(r"-?\d+", normalized):
        wanted_id = int(normalized)
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if wanted_id in candidate_numeric_ids(entity):
                return entity
        raise ValueError(f'Cannot find any dialog matching numeric id "{chat_ref}"')

    return await client.get_entity(chat_ref)


async def list_chats(client: Any) -> int:
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        username = getattr(entity, "username", None) or ""
        title = dialog.name or dialog_label(entity)
        ids = ", ".join(str(value) for value in sorted(candidate_numeric_ids(entity)))
        print(f"{dialog_kind(entity)}\t{ids}\t{username}\t{title}")
    return 0


def peer_to_dict(peer: Any | None) -> dict[str, Any] | None:
    if peer is None:
        return None
    if isinstance(peer, PeerUser):
        return {"type": "user", "id": peer.user_id}
    if isinstance(peer, PeerChat):
        return {"type": "chat", "id": peer.chat_id}
    if isinstance(peer, PeerChannel):
        return {"type": "channel", "id": peer.channel_id}
    return {"type": type(peer).__name__, "id": None}


def message_text(message: Any) -> str:
    text = (message.raw_text or "").strip()
    if text:
        return text
    if message.action:
        return f"[service] {type(message.action).__name__}"
    return ""


def message_record(chat_label: str, message: Any) -> dict[str, Any]:
    return {
        "chat": chat_label,
        "message_id": message.id,
        "date": message.date.isoformat() if message.date else None,
        "edit_date": message.edit_date.isoformat() if message.edit_date else None,
        "sender_id": message.sender_id,
        "peer_id": peer_to_dict(message.peer_id),
        "reply_to_msg_id": getattr(message.reply_to, "reply_to_msg_id", None),
        "forwards": message.forwards,
        "views": message.views,
        "post_author": message.post_author,
        "text": message_text(message),
    }


def format_txt_line(record: dict[str, Any]) -> str:
    raw_date = record.get("date")
    if raw_date:
        dt = datetime.fromisoformat(raw_date)
        date_label = dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_label = "unknown-date"
    sender_label = f"sender#{record['sender_id']}" if record.get("sender_id") else "unknown-sender"
    text = record.get("text") or ""
    return f"[{date_label}] {sender_label}: {text}"


async def export_chat(args: argparse.Namespace) -> int:
    output_path = build_output_path(args.chat, args.output, args.format)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(args.session, args.api_id, args.api_hash)
    await client.start()

    try:
        if args.list_chats:
            return await list_chats(client)

        takeout_id = client.session.takeout_id
        if takeout_id is not None and not isinstance(takeout_id, int):
            print(
                f"Found invalid unfinished takeout marker {takeout_id!r}; clearing it locally.",
                file=sys.stderr,
            )
            client.session.takeout_id = None
            client.session.save()
        elif takeout_id is not None:
            print(
                f"Found unfinished takeout session {takeout_id}; closing it first.",
                file=sys.stderr,
            )
            await client.end_takeout(success=False)

        entity = await resolve_entity(client, args.chat)
        chat_label = getattr(entity, "title", None) or getattr(entity, "username", None) or args.chat

        if args.no_takeout:
            stats = await write_export(
                message_source=client,
                entity=entity,
                chat_label=chat_label,
                output_path=output_path,
                fmt=args.format,
                limit=args.limit,
                reverse=args.reverse,
                include_empty=args.include_empty,
            )
        else:
            try:
                takeout_cm = client.takeout(
                    finalize=True,
                    contacts=False,
                    users=True,
                    chats=True,
                    megagroups=True,
                    channels=True,
                    files=False,
                )
                async with takeout_cm as takeout:
                    stats = await write_export(
                        message_source=takeout,
                        entity=entity,
                        chat_label=chat_label,
                        output_path=output_path,
                        fmt=args.format,
                        limit=args.limit,
                        reverse=args.reverse,
                        include_empty=args.include_empty,
                    )
            except errors.TakeoutInitDelayError as exc:
                print(
                    (
                        "Telegram delayed takeout initialization for this account. "
                        f"Try again after about {exc.seconds} seconds, or rerun with --no-takeout."
                    ),
                    file=sys.stderr,
                )
                return 2
    finally:
        await client.disconnect()

    print(f"Saved {stats.written} messages to {output_path}")
    if stats.skipped_empty:
        print(f"Skipped {stats.skipped_empty} empty/service-only messages")
    print(f"Scanned {stats.scanned} total messages")
    return 0


async def write_export(
    *,
    message_source: Any,
    entity: Any,
    chat_label: str,
    output_path: Path,
    fmt: str,
    limit: int | None,
    reverse: bool,
    include_empty: bool,
) -> ExportStats:
    stats = ExportStats()

    with output_path.open("w", encoding="utf-8") as handle:
        async for message in message_source.iter_messages(entity, limit=limit, reverse=reverse, wait_time=0):
            stats.scanned += 1
            record = message_record(chat_label, message)
            if not record["text"] and not include_empty:
                stats.skipped_empty += 1
                continue

            if fmt == "jsonl":
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            else:
                handle.write(format_txt_line(record) + "\n")
            stats.written += 1

    return stats


def main() -> int:
    args = parse_args()
    require_dependencies()

    if not args.list_chats and not args.chat:
        print("Pass --chat or use --list-chats.", file=sys.stderr)
        return 1

    if not args.api_id or not args.api_hash:
        print(
            "Both API credentials are required. Set TG_API_ID and TG_API_HASH, "
            "or pass --api-id and --api-hash explicitly.",
            file=sys.stderr,
        )
        return 1

    return asyncio.run(export_chat(args))


if __name__ == "__main__":
    raise SystemExit(main())
