import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
from typing import Optional
from faster_whisper import WhisperModel
import discord.ext.voice_recv as voice_recv

class VoiceNotesCog(commands.Cog, name="Voice Transcriber"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_recordings = {} # guild_id -> {"file": filename, "sink": sink, "channel_id": id}
        self.whisper_model = None

    def get_whisper(self):
        if self.whisper_model is None:
            # Using 'tiny' or 'base' for fast real-time transcription on CPU
            print("Loading Whisper Model...")
            self.whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
            print("Whisper Model loaded!")
        return self.whisper_model

    radio_group = app_commands.Group(name="radio", description="Radio & Meeting Voice Note Transcriber")

    @radio_group.command(name="join", description="Join a voice radio or discussion channel.")
    @app_commands.describe(channel="Voice channel to join (defaults to your current voice channel)")
    async def join_voice(self, interaction: discord.Interaction, channel: Optional[discord.VoiceChannel] = None):
        await interaction.response.defer()

        target_ch = channel or getattr(interaction.user.voice, "channel", None)
        if not target_ch:
            await interaction.followup.send("❌ You must be in a voice channel, or select one!")
            return

        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()

        try:
            await target_ch.connect(cls=voice_recv.VoiceRecvClient)
            await interaction.followup.send(f"🎙️ Joined **{target_ch.name}**! Use `/radio record` when ready to record notes.")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to join voice channel: `{e}`")

    @radio_group.command(name="record", description="Start recording meeting audio for transcription.")
    async def start_record(self, interaction: discord.Interaction):
        await interaction.response.defer()
        vc: voice_recv.VoiceRecvClient = interaction.guild.voice_client

        if not vc or not vc.is_connected():
            await interaction.followup.send("❌ Bot is not in a voice channel. Run `/radio join` first.")
            return

        if vc.is_listening():
            await interaction.followup.send("⚠️ Already recording audio in this channel!")
            return

        filename = os.path.join(os.path.dirname(__file__), f"rec_{interaction.guild.id}.wav")
        # Remove any previous temp file
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                pass

        sink = voice_recv.WaveSink(filename)
        vc.listen(sink)

        self.active_recordings[interaction.guild.id] = {
            "file": filename,
            "sink": sink,
            "channel_id": vc.channel.id
        }

        embed = discord.Embed(
            title="🔴 Radio Recording Started",
            color=discord.Color.red(),
            description=f"Now listening to **{vc.channel.name}**.\nWhen finished, run `/radio stop` to transcribe and generate meeting notes."
        )
        embed.set_footer(text="Thenga Voice AI Transcriber")
        await interaction.followup.send(embed=embed)

    @radio_group.command(name="stop", description="Stop recording, transcribe audio, and post meeting notes.")
    @app_commands.describe(notes_channel="Text channel to post transcription notes (e.g. #thenga-journal)")
    async def stop_record(self, interaction: discord.Interaction, notes_channel: Optional[discord.TextChannel] = None):
        await interaction.response.defer()
        vc: voice_recv.VoiceRecvClient = interaction.guild.voice_client

        if not vc or not vc.is_listening():
            await interaction.followup.send("❌ No active recording in progress.")
            return

        vc.stop_listening()
        rec_data = self.active_recordings.pop(interaction.guild.id, None)
        target_text_ch = notes_channel or interaction.channel

        await interaction.followup.send("⏳ Recording stopped! Processing audio with Whisper AI...")

        filename = rec_data["file"] if rec_data else None
        if not filename or not os.path.exists(filename):
            await target_text_ch.send("⚠️ No audio data captured.")
            return

        # Run Whisper transcription in thread pool to avoid blocking bot loop
        loop = asyncio.get_running_loop()

        def transcribe_task():
            model = self.get_whisper()
            segments, info = model.transcribe(filename, beam_size=5)
            full_text = " ".join([seg.text.strip() for seg in segments if seg.text])
            return full_text, info.language

        try:
            text, lang = await loop.run_in_executor(None, transcribe_task)
        except Exception as e:
            await target_text_ch.send(f"❌ Transcription error: `{e}`")
            return
        finally:
            # Clean up temp wav file
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception:
                    pass

        if not text.strip():
            await target_text_ch.send("📝 Recording finished, but no speech was detected.")
            return

        # Format and send transcript
        embed = discord.Embed(
            title="🎙️ Radio Meeting Notes / Transcription",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Detected Language", value=lang.upper(), inline=True)
        embed.add_field(name="Recorded By", value=interaction.user.mention, inline=True)

        # Split into chunks if long
        if len(text) <= 1000:
            embed.description = f"```text\n{text}\n```"
            embed.set_footer(text="Thenga Voice Transcriber")
            await target_text_ch.send(embed=embed)
        else:
            embed.description = f"```text\n{text[:1000]}...\n```"
            await target_text_ch.send(embed=embed)
            # Send remainder as text
            remaining = text[1000:]
            for i in range(0, len(remaining), 1900):
                await target_text_ch.send(f"```text\n{remaining[i:i+1900]}\n```")

    @radio_group.command(name="leave", description="Disconnect bot from voice channel.")
    async def leave_voice(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.followup.send("👋 Disconnected from voice channel.")
        else:
            await interaction.followup.send("Bot is not in any voice channel.")

    @app_commands.command(name="transcribe", description="Transcribe an uploaded audio/video clip using Whisper AI.")
    @app_commands.describe(file="Audio or video file (WAV, MP3, M4A, OGG, MP4)")
    async def transcribe_file(self, interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer()

        # Check file extension
        valid_exts = [".wav", ".mp3", ".m4a", ".ogg", ".mp4", ".aac", ".flac"]
        if not any(file.filename.lower().endswith(ext) for ext in valid_exts):
            await interaction.followup.send("❌ Supported formats: WAV, MP3, M4A, OGG, MP4.")
            return

        # Download file
        temp_path = os.path.join(os.path.dirname(__file__), f"temp_{file.id}_{file.filename}")
        await file.save(temp_path)

        await interaction.followup.send("⏳ Transcribing audio file with Whisper AI...")

        loop = asyncio.get_running_loop()

        def transcribe_task():
            model = self.get_whisper()
            segments, info = model.transcribe(temp_path, beam_size=5)
            full_text = " ".join([seg.text.strip() for seg in segments if seg.text])
            return full_text, info.language

        try:
            text, lang = await loop.run_in_executor(None, transcribe_task)
        except Exception as e:
            await interaction.followup.send(f"❌ Error during transcription: `{e}`")
            return
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

        if not text.strip():
            await interaction.followup.send("📝 No speech detected in the uploaded file.")
            return

        embed = discord.Embed(
            title=f"🎙️ Audio Clip Transcript: `{file.filename}`",
            color=discord.Color.green(),
            description=f"```text\n{text[:1800]}\n```"
        )
        embed.set_footer(text=f"Detected Language: {lang.upper()} • Thenga Voice AI")
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceNotesCog(bot))
