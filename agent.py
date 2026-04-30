import asyncio
import json
import logging
import sys
import time
import warnings

# Force UTF-8 on Windows terminals (default cp1252 breaks non-ASCII log chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# LOGGING — must be configured BEFORE any livekit imports.
# livekit sets up its own handlers during import, which makes a later
# basicConfig() call a no-op.  We attach an explicit StreamHandler so our
# friday-agent / friday-tools loggers always appear in the terminal.
# ---------------------------------------------------------------------------

_fmt = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d  %(levelname)-8s  %(name)-20s %(message)s",
    datefmt="%H:%M:%S",
)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
_sh.setLevel(logging.DEBUG)

for _log_name in ("friday-agent", "friday-tools"):
    _log = logging.getLogger(_log_name)
    _log.setLevel(logging.DEBUG)
    _log.addHandler(_sh)
    _log.propagate = False          # don't double-print via root logger

# Also pull root up to INFO so livekit framework logs remain visible
logging.getLogger().setLevel(logging.INFO)

logger = logging.getLogger("friday-agent")
logger.info("=" * 55)
logger.info("  Friday AI Agent  --  starting up")
logger.info("=" * 55)

# ---------------------------------------------------------------------------
# Windows fix: livekit's duplex_unix uses socket primitives that require the
# Selector event loop.  Python 3.8+ defaults to Proactor on Windows, which
# causes DuplexClosed crashes.  Force Selector before any async work.
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    # Deprecated in Python 3.14 but still required for livekit compatibility.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logger.info("[INIT] Windows SelectorEventLoop set (livekit compatibility).")

from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import (
    AgentSession, Agent, RoomInputOptions,
    UserInputTranscribedEvent, ConversationItemAddedEvent,
    FunctionCallEvent, FunctionToolsExecutedEvent,
    AgentStateChangedEvent, ChatMessage,
)

from livekit.plugins import google
from livekit.plugins.google.realtime.api_proto import types as google_types

from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import (
    get_weather, search_web,
    send_email, check_email_status,
    check_system_errors, clear_error_log,
)

load_dotenv()
logger.info("[INIT] Environment loaded. Waiting for Android client to connect...")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.realtime.RealtimeModel(
                model="gemini-2.5-flash-native-audio-preview-12-2025",
                voice="Aoede",
                temperature=0.7,

                # No token cap — let the model produce responses of any length.
                # Previously capped at 1024 which truncated long answers.

                # Prevent unbounded context growth over long sessions
                context_window_compression=google_types.ContextWindowCompressionConfig(
                    trigger_tokens=6000,
                    sliding_window=google_types.SlidingWindow(target_tokens=3000),
                ),

                # Transcription — required so text appears alongside voice
                input_audio_transcription=google_types.AudioTranscriptionConfig(),
                output_audio_transcription=google_types.AudioTranscriptionConfig(),
            ),
            tools=[
                get_weather,
                search_web,
                send_email,
                check_email_status,
                check_system_errors,
                clear_error_log,
            ],
        )


# ---------------------------------------------------------------------------
# Helper: publish a structured JSON packet to the LiveKit room data channel.
# The Android client listens to onDataReceived and parses these packets to
# update the chat UI, show loading spinners, etc.
# ---------------------------------------------------------------------------

async def _publish(room: rtc.Room, payload: dict) -> None:
    """Send a JSON data packet to all participants in the room."""
    try:
        data = json.dumps(payload).encode("utf-8")
        await room.local_participant.publish_data(data, reliable=True)
    except Exception as e:
        logger.warning(f"publish_data failed: {e}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def entrypoint(ctx: agents.JobContext):
    logger.info(f"Starting agent for room: {ctx.room.name}")

    logger.info("Connecting to room...")
    await ctx.connect()
    logger.info(f"Connected to room: {ctx.room.name}")

    session = AgentSession()

    # -----------------------------------------------------------------------
    # EVENT HANDLERS — transcript + status events sent to Android via data channel
    # -----------------------------------------------------------------------

    @session.on("user_input_transcribed")
    def on_user_transcript(event: UserInputTranscribedEvent):
        """
        Real-time transcription — two packet types sent to Android:

        • 'transcript_interim'  (is_final=False)
            Fired word-by-word as the user speaks. Android updates the
            live textbox in real time so each word appears as it's said.

        • 'chat_message' / role='user'  (is_final=True)
            Fired once the utterance is fully recognised. Android commits
            the final text to the chat history.
        """
        text = event.transcript.strip()
        if not text:
            return

        if not event.is_final:
            # ── Interim: word appears in textbox immediately ──────────────
            asyncio.ensure_future(_publish(ctx.room, {
                "type":      "transcript_interim",
                "text":      text,
                "timestamp": int(time.time() * 1000),
            }))
        else:
            # ── Final: commit to chat history ─────────────────────────────
            logger.info(f"[USER     ] {text}")
            asyncio.ensure_future(_publish(ctx.room, {
                "type":      "chat_message",
                "role":      "user",
                "text":      text,
                "timestamp": int(time.time() * 1000),
            }))

    @session.on("agent_state_changed")
    def on_agent_state(event: AgentStateChangedEvent):
        """
        Publish agent state changes so Android can show/hide the loading indicator.
        States: 'initializing' | 'listening' | 'thinking' | 'speaking'
        """
        logger.info(f"[STATE   ] {event.old_state} → {event.new_state}")
        asyncio.ensure_future(_publish(ctx.room, {
            "type": "agent_state",
            "state": str(event.new_state),
            "timestamp": int(time.time() * 1000),
        }))

    @session.on("function_call")
    def on_tool_start(event: FunctionCallEvent):
        """
        Publish a 'tool_start' event the moment a tool is invoked.
        Android can show 'Friday is searching...' / 'Friday is checking weather...'
        as soon as this arrives — before the tool result comes back.
        """
        tool_name = event.item.name
        logger.info(f"[TOOL▶   ] {tool_name} called")
        asyncio.ensure_future(_publish(ctx.room, {
            "type": "tool_start",
            "tool": tool_name,
            "message": _tool_message(tool_name),
            "timestamp": int(time.time() * 1000),
        }))

    @session.on("function_tools_executed")
    def on_tool_done(event: FunctionToolsExecutedEvent):
        """
        Publish a 'tool_done' event after all tools in this turn have returned.
        Android hides the loading indicator and waits for the assistant reply.
        """
        tool_names = [fc.name for fc in event.function_calls]
        logger.info(f"[TOOL✓   ] {', '.join(tool_names)} completed")
        asyncio.ensure_future(_publish(ctx.room, {
            "type": "tool_done",
            "tools": tool_names,
            "timestamp": int(time.time() * 1000),
        }))

    @session.on("conversation_item_added")
    def on_conversation_item(event: ConversationItemAddedEvent):
        """Publish every completed assistant reply as a chat message."""
        item = event.item
        if isinstance(item, ChatMessage):
            text = item.text_content
            role = item.role.value if hasattr(item.role, "value") else str(item.role)
            if text and text.strip():
                logger.info(f"[{role.upper():9}] {text[:150]}")
                if role == "assistant":
                    asyncio.ensure_future(_publish(ctx.room, {
                        "type": "chat_message",
                        "role": "assistant",
                        "text": text.strip(),
                        "timestamp": int(time.time() * 1000),
                    }))

    # -----------------------------------------------------------------------

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            video_enabled=False,
            # noise_cancellation removed — saves ~280 MB RAM on Railway free tier
        ),
    )

    logger.info("Session started. Generating opening reply...")
    await session.generate_reply(instructions=SESSION_INSTRUCTION)


def _tool_message(tool_name: str) -> str:
    """Human-readable status message to show on Android while tool is running."""
    return {
        "get_weather":        "Checking weather conditions...",
        "search_web":         "Searching the web for you...",
        "send_email":         "Preparing to send email...",
        "check_email_status": "Diagnosing email issue...",
        "check_system_errors":"Fetching system error log...",
        "clear_error_log":    "Clearing error log...",
    }.get(tool_name, "Working on it...")


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))