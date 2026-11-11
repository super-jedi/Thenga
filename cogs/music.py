import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import yt_dlp
import functools
from typing import Optional, Dict, Any, List
from collections import deque

# Suppress noise about console
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'cachedir': False,
    'skip_download': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    },
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class Track:
    def __init__(self, data: dict, requester: discord.Member):
        self.data = data
        self.requester = requester
        self.title = data.get('title', 'Unknown Title')
        self.webpage_url = data.get('webpage_url') or data.get('original_url') or data.get('url', '')
        stream_url = data.get('url', '')
        if not stream_url and 'formats' in data:
            audio_formats = [f for f in data['formats'] if f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or not f.get('vcodec'))]
            if audio_formats:
                stream_url = audio_formats[-1].get('url', '')
            elif data['formats']:
                stream_url = data['formats'][-1].get('url', '')
        self.stream_url = stream_url
        self.thumbnail = data.get('thumbnail', '')
        self.duration = data.get('duration', 0)
        self.uploader = data.get('uploader') or data.get('channel', 'Unknown Artist')

    @property
    def formatted_duration(self) -> str:
        if not self.duration:
            return "Live Stream"
        mins, secs = divmod(self.duration, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

class GuildPlayer:
    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.queue: deque[Track] = deque()
        self.current: Optional[Track] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.volume: float = 0.8
        self.loop_mode: str = "off" # "off", "song", "queue"
        self.next_event = asyncio.Event()
        self.audio_task: Optional[asyncio.Task] = None
        self.idle_timer: Optional[asyncio.TimerHandle] = None

    async def player_loop(self):
        await self.bot.wait_until_ready()
        while True:
            self.next_event.clear()

            if not self.voice_client or not self.voice_client.is_connected():
                break

            if self.loop_mode == "song" and self.current:
                track = self.current
            else:
                if not self.queue:
                    self.current = None
                    try:
                        # Wait up to 300 seconds (5 mins) for a new song before disconnecting
                        await asyncio.wait_for(self.next_event.wait(), timeout=300.0)
                    except asyncio.TimeoutError:
                        if self.voice_client and self.voice_client.is_connected():
                            await self.voice_client.disconnect()
                        break
                    continue
                track = self.queue.popleft()
                if self.loop_mode == "queue" and self.current:
                    self.queue.append(self.current)
                self.current = track

            try:
                # Refresh stream URL if needed
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(
                    None,
                    functools.partial(ytdl.extract_info, track.webpage_url, download=False)
                )
                stream_url = data.get('url')
                if not stream_url and 'formats' in data:
                    audio_formats = [f for f in data['formats'] if f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or not f.get('vcodec'))]
                    if audio_formats:
                        stream_url = audio_formats[-1].get('url')
                    elif data['formats']:
                        stream_url = data['formats'][-1].get('url')
                if not stream_url:
                    stream_url = track.stream_url

                source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
                transformed_source = discord.PCMVolumeTransformer(source, volume=self.volume)

                def after_playing(err):
                    if err:
                        print(f"Player error in guild {self.guild_id}: {err}")
                    self.bot.loop.call_soon_threadsafe(self.next_event.set)

                self.voice_client.play(transformed_source, after=after_playing)
            except Exception as e:
                print(f"Error starting playback in guild {self.guild_id}: {e}")
                self.next_event.set()

            await self.next_event.wait()

    def start(self, voice_client: discord.VoiceClient):
        self.voice_client = voice_client
        if not self.audio_task or self.audio_task.done():
            self.audio_task = self.bot.loop.create_task(self.player_loop())

    def stop(self):
        self.queue.clear()
        self.current = None
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        if self.audio_task and not self.audio_task.done():
            self.audio_task.cancel()

class Music(commands.Cog):
    """Thenga High-Fidelity YouTube & YouTube Music Player"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: Dict[int, GuildPlayer] = {}

    def get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer(self.bot, guild_id)
        return self.players[guild_id]

    async def _ensure_voice(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "❌ You must be connected to a voice channel to use music commands.",
                ephemeral=True
            )
            return None

        channel = interaction.user.voice.channel
        voice_client: Optional[discord.VoiceClient] = interaction.guild.voice_client

        if not voice_client:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        return voice_client

    @app_commands.command(name="play", description="Play or enqueue a song from YouTube or YouTube Music")
    @app_commands.describe(query="Song title, artist, or YouTube URL")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        voice_client = await self._ensure_voice(interaction)
        if not voice_client:
            return

        player = self.get_player(interaction.guild_id)
        player.start(voice_client)

        loop = asyncio.get_event_loop()
        try:
            # Check if query is URL or search query
            search_query = query if query.startswith(('http://', 'https://')) else f"ytsearch:{query}"
            data = await loop.run_in_executor(
                None,
                functools.partial(ytdl.extract_info, search_query, download=False)
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ Failed to extract audio: `{e}`")
            return

        if 'entries' in data:
            if not data['entries']:
                await interaction.followup.send("❌ No matching tracks found on YouTube.")
                return
            data = data['entries'][0]

        track = Track(data, interaction.user)
        player.queue.append(track)

        # Build Rich Discord Embed
        embed = discord.Embed(
            title="🎵 Track Queued",
            description=f"[{track.title}]({track.webpage_url})",
            color=0x22c55e # Emerald green accent
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embed.add_field(name="Duration", value=track.formatted_duration, inline=True)
        embed.add_field(name="Channel", value=track.uploader, inline=True)
        embed.add_field(name="Position in Queue", value=str(len(player.queue) if player.current else 1), inline=True)
        embed.set_footer(
            text=f"Requested by {interaction.user.display_name} • Thenga Music",
            icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
        )

        await interaction.followup.send(embed=embed)

        # If idle, wake up the player
        if not player.voice_client.is_playing() and not player.voice_client.is_paused():
            player.next_event.set()

    @app_commands.command(name="pause", description="Pause current music playback")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        vc.pause()
        await interaction.response.send_message("⏸️ Playback paused.")

    @app_commands.command(name="resume", description="Resume paused music playback")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_paused():
            await interaction.response.send_message("❌ Playback is not paused.", ephemeral=True)
            return

        vc.resume()
        await interaction.response.send_message("▶️ Playback resumed.")

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await interaction.response.send_message("❌ Nothing is currently playing to skip.", ephemeral=True)
            return

        player = self.get_player(interaction.guild_id)
        current_title = player.current.title if player.current else "track"
        vc.stop() # triggers player_loop after callback
        await interaction.response.send_message(f"⏭️ Skipped **{current_title}**.")

    @app_commands.command(name="stop", description="Stop music playback, clear queue, and leave voice channel")
    async def stop(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        player.stop()

        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()

        await interaction.response.send_message("⏹️ Playback stopped, queue cleared, and disconnected.")

    @app_commands.command(name="queue", description="Show the current music playback queue")
    async def show_queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)

        if not player.current and not player.queue:
            await interaction.response.send_message("📭 The queue is currently empty.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎶 Thenga Music Queue",
            color=0x10b981
        )

        if player.current:
            embed.add_field(
                name="▶️ Now Playing",
                value=f"[{player.current.title}]({player.current.webpage_url}) (`{player.current.formatted_duration}`) - Req by {player.current.requester.mention}",
                inline=False
            )

        if player.queue:
            queue_str = ""
            for idx, track in enumerate(list(player.queue)[:10], start=1):
                queue_str += f"`{idx}.` [{track.title}]({track.webpage_url}) (`{track.formatted_duration}`) - {track.requester.display_name}\n"
            if len(player.queue) > 10:
                queue_str += f"\n*...and {len(player.queue) - 10} more songs in queue*"
            embed.add_field(name="⏳ Up Next", value=queue_str, inline=False)
        else:
            embed.add_field(name="⏳ Up Next", value="*No upcoming songs*", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Show details of the song currently playing")
    async def now_playing(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        if not player.current:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        track = player.current
        embed = discord.Embed(
            title="🎧 Now Playing",
            description=f"[{track.title}]({track.webpage_url})",
            color=0x22c55e
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embed.add_field(name="Channel / Artist", value=track.uploader, inline=True)
        embed.add_field(name="Duration", value=track.formatted_duration, inline=True)
        embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
        embed.add_field(name="Loop Mode", value=player.loop_mode.capitalize(), inline=True)
        embed.add_field(name="Requested By", value=track.requester.mention, inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Adjust playback volume (1 to 100%)")
    @app_commands.describe(level="Volume level percentage (1-100)")
    async def set_volume(self, interaction: discord.Interaction, level: int):
        if level < 1 or level > 100:
            await interaction.response.send_message("❌ Volume must be between 1 and 100.", ephemeral=True)
            return

        player = self.get_player(interaction.guild_id)
        player.volume = level / 100.0

        vc = interaction.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = player.volume

        await interaction.response.send_message(f"🔊 Volume set to **{level}%**.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Auto-disconnect if bot is left alone in voice channel"""
        vc: Optional[discord.VoiceClient] = member.guild.voice_client
        if vc and vc.channel and len(vc.channel.members) == 1 and vc.channel.members[0] == member.guild.me:
            player = self.get_player(member.guild.id)
            player.stop()
            await vc.disconnect()

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
