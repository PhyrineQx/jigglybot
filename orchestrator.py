
import asyncio

import discord
import yt_dlp as youtube_dl
import os
import all_strings
import random
import re
import csv
from io import StringIO
from unidecode import unidecode
from collections import Counter

from discord.ext import commands

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

CATEGORY_NUMBER_FOR_VOTE = 6
DEFAULT_DURATION = 90

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

def custom_exception_handler(loop, context):
    # first, handle with default handler
    loop.default_exception_handler(context)
    print(context)
    loop.stop()

def normalize_team_name(str):
    return re.sub(r'[^-a-z0-9]', '', unidecode(str).lower().replace(" ", "-"))

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class Downloader():
    def __init__(self, table):
        self.table = table

    @staticmethod
    async def pre_download_table(table):
        for track in table:
            print(f"Downloading {track['url']}")
            track['player'] = await YTDLSource.from_url(track['url'])
            print(f"Download OK")

        return table

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.teams = []
        self.table = None
        self.current_track = None
        self.current_answers = {}
        self.vote_privilege = None
        self.game_in_session = False
        self.pause = False

    @commands.command()
    @commands.has_role("quizmaster")
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command()
    @commands.has_role("quizmaster")
    async def loadlocal(self, ctx):
        """Loads the blindtest"""
        
        if self.game_in_session is True:
            await ctx.send("You can't use !load while a blindtest is already running.")
            return

        self.table = [{'url': 'https://www.youtube.com/watch?v=B7gGacb8cO4', 'answer': 'Pizza Tower', 'category': 'Catégorie unique', 'acceptable_answers': '', 'duration_seconds': ''},
                      {'url': 'https://www.youtube.com/watch?v=bSyL0N_JE7M', 'answer': 'Rogue Legacy 2', 'category': 'Catégorie unique', 'acceptable_answers': 'Rogue Legacy|Rogue Legacy 3', 'duration_seconds': 20},
                      {'url': 'https://www.youtube.com/watch?v=lTNgHKUX3eM', 'answer': 'Paradise Killer', 'category': 'Catégorie unique', 'acceptable_answers': '', 'duration_seconds': ''}]

        # Mutates table to include a player for each song
        await Downloader.pre_download_table(self.table)
        await ctx.send(all_strings.LOAD_SUCCESS)

    @commands.command()
    @commands.dm_only()
    async def loadcsv(self, ctx):
        if self.game_in_session is True:
            await ctx.send("You can't use !loadcsv while a blindtest is already running.")
            return
        
        bytes_file = await ctx.message.attachments[0].read()
        csv_file = StringIO(bytes_file.decode("utf-8-sig")) # UTF-8 with BOM (works without just as well)
        reader = csv.DictReader(csv_file)
        
        problems = []
        table = []
        for idx, row in enumerate(reader):
            table.append(row)
            if 'url' not in row.keys():
                problems.append(f'Line {idx + 2}: Missing url column')
            elif not row['url']:
                problems.append(f'Line {idx + 2}: url field containing an empty string')
            
            if 'answer' not in row.keys():
                problems.append(f'Line {idx + 2}: Missing answer column')
            elif not row['answer']:
                problems.append(f'Line {idx + 2}: answer field containing an empty string')
            
            if 'category' not in row.keys():
                problems.append(f'Line {idx + 2}: Missing category column')
            elif not row['category']:
                problems.append(f'Line {idx + 2}: category field containing an empty string')
            
            if 'acceptable_answers' not in row.keys():
                problems.append(f'Line {idx + 2}: Missing acceptable_answers column')
            
            if 'duration_seconds' not in row.keys():
                problems.append(f'Line {idx + 2}: Missing duration_seconds column')
            elif row['duration_seconds'] and not row['duration_seconds'].isdigit():
                problems.append(f'Line {idx + 2}: duration_seconds has to be an integer')
        
        if problems:
            await ctx.send("Problems found:\n- " + '\n- '.join(problems))
            return
        
        self.table = table
        await Downloader.pre_download_table(self.table)
        await ctx.send(all_strings.LOAD_SUCCESS)

    @commands.command()
    async def team(self, ctx, *args):
        """Create a team and/or joins the team"""
        
        team_name = normalize_team_name(' '.join(args))

        if len(team_name) == 0:
            return
        
        if len(team_name) > 99:
            return
        
        category_channel = discord.utils.get(ctx.guild.channels, name="team channels")
        if not category_channel:
            category_channel = await ctx.guild.create_category("team channels")

        # Remove the contestant from other teams
        for team in self.teams:
            if ctx.author in team['members']:
                team['members'].remove(ctx.author)

        # Create the team
        if not team_name in map(lambda team: team['name'], self.teams):
            self.teams.append({'name': team_name,
                               'members': set()})
        
        # Add the member to the team
        for team in self.teams:
            if team_name == team['name']:
                team['members'].add(ctx.author)

        # Remove empty teams
        for team in self.teams:
            if len(team['members']) == 0:
                self.teams.remove(team)

        await self.update_team_channels(ctx)

    async def update_team_channels(self, ctx):
        """Update team channels to reflect the game state"""

        category_channel = discord.utils.get(ctx.guild.channels, name="team channels")
        if not category_channel:
            category_channel = await ctx.guild.create_category("team channels")

        # Delete empty team channels
        for channel in category_channel.text_channels:
            if channel.name not in map(lambda team: team['name'], self.teams):
                await channel.delete()

        # Create team channels if they don't exist and reset permissions for existing ones
        for team in self.teams:
            team_channel = discord.utils.get(ctx.guild.channels, name=team['name'])
            permission_overwrites={ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False)}
            for team_member in team['members']:
                permission_overwrites[team_member] = discord.PermissionOverwrite(read_messages=True)
            if not team_channel:
                team_channel = await ctx.guild.create_text_channel(team['name'], category=category_channel, overwrites=permission_overwrites)
            else:
                await team_channel.edit(overwrites=permission_overwrites)
            

    async def skippable_wait(self, duration):
        counter = 0
        while not self.skip and counter < duration:
            await asyncio.sleep(1)
            counter += 1
        
    @commands.command()
    @commands.has_role("quizmaster")
    async def skip(self, ctx):
        if not self.game_in_session:
            await ctx.send("There is no game running.")
            return

        if not self.current_track:
            await ctx.send("There is no track playing.")
            return
        
        self.skip = True


    @commands.command()
    @commands.has_role("quizmaster")
    async def begin(self, ctx):
        # Check if there are any teams
        if len(self.teams) == 0:
            await ctx.send(f'Please create at least one team before launching the game.')
            return
        
        # Check if there is a blindtest loaded
        if self.table is None:
            await ctx.send(f'Please load a blindtest file before launching the game.')
            return
        
        # Welcome
        self.game_in_session = True
        await ctx.send(f'Beginning the game, check your team channels and good luck!')
        await self.send_all_teams(ctx, all_strings.TEAM_WELCOME)
        await asyncio.sleep(10)

        # The game loop runs until there are no songs left
        while len(self.table) > 0:

            # Time to select a category by vote
            await self.maybe_pause()
            category = await self.vote_for_category(ctx)
            
            # Select track
            track = self.get_random_track_from_category(category)

            # Get ready
            await self.maybe_pause()
            self.current_track = track
            self.skip = False
            await self.send_all_teams(ctx, all_strings.build_start_song_message(category))
            get_ready_sound = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio('assets/question.wav'))
            ctx.voice_client.play(get_ready_sound, after=lambda e: print(f'Player error: {e}') if e else 
                                  ctx.voice_client.play(track['player'], after=lambda e: print(f'Player error: {e}') if e else None))
            duration = DEFAULT_DURATION if not track['duration_seconds'] else int(track['duration_seconds'])

            async def after_seconds_left(self, ctx, after, content, only_still_playing = False, skippable = False):
                await self.skippable_wait(after)
                if not (skippable and self.skip):
                    if only_still_playing is True:
                        await self.send_still_playing_teams(ctx, content)
                    else:
                        await self.send_all_teams(ctx, content)
            
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.send_all_teams(ctx, all_strings.build_times_left_message(duration)))
                if duration >= 30:
                    tg.create_task(after_seconds_left(self, ctx, duration - 30, all_strings.THIRTY_SECONDS_LEFT, only_still_playing=True, skippable=True))
                if duration >= 10:
                    tg.create_task(after_seconds_left(self, ctx, duration - 10, all_strings.TEN_SECONDS_LEFT, only_still_playing=True, skippable=True))
                tg.create_task(after_seconds_left(self, ctx, duration, all_strings.build_times_up_message(track['answer'], track['url'])))
        
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            if len(self.current_answers.items()) > 0:
                await self.send_all_teams(ctx, all_strings.build_everyone_guesses_message(self.current_answers))
            self.current_track = None
            self.skip = False
            times_up_sound = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio('assets/time.wav'))
            ctx.voice_client.play(times_up_sound, after=lambda e: print(f'Player error: {e}') if e else None)

            await asyncio.sleep(10)

            self.table.remove(track)
            self.current_answers = {}

        await self.send_all_teams(ctx, all_strings.GAME_FINISHED)
        self.game_in_session = False

    async def maybe_pause(self):
        while self.pause is True:
            await asyncio.sleep(1)

    def get_random_track_from_category(self, category):
        category_tracks = list(filter(lambda song: song['category'] == category, self.table))
        return random.choice(category_tracks)

    async def vote_for_category(self, ctx):
        categories = self.select_categories(CATEGORY_NUMBER_FOR_VOTE)

        async def add_reactions(message, categories):
            for i in range(1, len(categories) + 1):
                await message.add_reaction(all_strings.VOTE_EMOJIS[i-1])

        # Send messages to winning team or every team
        vote_messages = await self.send_all_teams(ctx, all_strings.build_vote_message(categories)) if self.vote_privilege is None else [await self.send_team(ctx, self.vote_privilege, all_strings.build_vote_message(categories))]
        async with asyncio.TaskGroup() as tg:
            for message in vote_messages:
                tg.create_task(add_reactions(message, categories))
        await asyncio.sleep(10)

        # Gather all reactions
        reactions_count = Counter()
        for i in range(1, len(categories) + 1):
            reactions_count.update({all_strings.VOTE_EMOJIS[i-1]: 0})
        for message in vote_messages:
            refreshed_message = await message.channel.fetch_message(message.id)
            for reaction in refreshed_message.reactions:
                reactions_count.update({reaction.emoji: reaction.count})

        # Winning team consumed their voting rights, time to earn them again
        self.vote_privilege = None

        # Who's the winner
        winner_emoji = reactions_count.most_common(1)[0][0]
        winner_position = all_strings.VOTE_EMOJIS.index(winner_emoji)
        return categories[winner_position]

    def select_categories(self, k):
        remaining_categories = set(map(lambda track: track['category'], self.table))
        n = k if len(remaining_categories) > k else len(remaining_categories)
        return random.sample(list(remaining_categories), n)

    async def send_all_teams(self, ctx, content):
        async def send_team(self, ctx, team, content):
            team_channel = discord.utils.get(ctx.guild.channels, name=team['name'])
            message = await team_channel.send(content)
            all_messages.append(message)
        
        all_results = []
        async with asyncio.TaskGroup() as tg:
            for team in self.teams:
                result = tg.create_task(send_team(self, ctx, team, content))
                all_results.append(result)
        all_messages = map(lambda r: r.result(), all_results)
        return all_messages
    
    async def send_still_playing_teams(self, ctx, content):
        all_messages = []
        for team in self.teams:
            if team['name'] not in self.current_answers.keys():
                team_channel = discord.utils.get(ctx.guild.channels, name=team['name'])
                message = await team_channel.send(content)
                all_messages.append(message)
        return all_messages

    async def send_team(self, ctx, team_name, content):
        for team in self.teams:
            if team['name'] == team_name:
                team_channel = discord.utils.get(ctx.guild.channels, name=team['name'])
                return await team_channel.send(content)
        
    @commands.command()
    async def guess(self, ctx, *args):
        answer = ' '.join(args)
        
        # If no track is currently playing there's no point
        if self.current_track is None:
            await ctx.send(f'There is no question in progress.')
            return
        
        # Who is answering
        answering_team = None
        for team in self.teams:
            if ctx.author in team['members']:
                answering_team = team['name']
        
        # If team already answered, tell them so
        if answering_team in self.current_answers.keys():
            await ctx.send(f'Your team already answered. One guess only!')
            return
        
        def sanitize_answer(str):
            return re.sub(r'[^a-z0-9]', '', unidecode(str).lower())

        # Strip accents and everything that isn't lowercase alphanumeric
        correct_answers_sanitized = [sanitize_answer(self.current_track['answer'])]
        if self.current_track['acceptable_answers']:
            for alternate_answer in self.current_track['acceptable_answers'].split('|'):
                correct_answers_sanitized.append(sanitize_answer(alternate_answer))
        team_answer_sanitized = sanitize_answer(answer)

        # Store the full fledged answer for question end recap
        self.current_answers[answering_team] = answer

        # If it's correct, team gains the voting privilege if no one got it yet
        if team_answer_sanitized in correct_answers_sanitized:
            if self.vote_privilege is None:
                self.vote_privilege = answering_team
            await self.send_all_teams(ctx, all_strings.build_guessed_right_message(answering_team))
        else:
            await self.send_all_teams(ctx, all_strings.build_guessed_wrong_message(answering_team))

    @commands.command()
    @commands.has_role("quizmaster")
    async def vote(self, ctx, team):
        if team not in map(lambda t: t['name'], self.teams):
            await ctx.send(all_strings.TEAM_DOES_NOT_EXIST)
            return

        self.vote_privilege = team
        await self.send_all_teams(ctx, all_strings.build_next_voting_team_message(team))

    @commands.command()
    @commands.has_role("quizmaster")
    async def pause(self, ctx):
        if self.game_in_session is False:
            return

        self.pause = True
        await self.send_all_teams(ctx, all_strings.GAME_PAUSED)

    @commands.command()
    @commands.has_role("quizmaster")
    async def unpause(self, ctx):
        if self.game_in_session is False:
            return
        
        self.pause = False
        await self.send_all_teams(ctx, all_strings.GAME_RESUMED)

    @commands.command()
    @commands.has_role("quizmaster")
    async def disband(self, ctx, team):
        """Deletes a team"""

        if team in self.teams:
            self.teams.remove(team)

        team_channel = discord.utils.get(ctx.guild.channels, name=team)
        if team_channel:
            await team_channel.delete()

    @commands.command()
    async def play(self, ctx, *, query):
        """Plays a file from the local filesystem"""

        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
        ctx.voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)

        await ctx.send(f'Now playing: {query}')

    @commands.command()
    async def yt(self, ctx, *args):
        """Plays from a url (almost anything youtube_dl supports)"""

        async with ctx.typing():
            player = await YTDLSource.from_url(args[0], loop=self.bot.loop)
            ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)

        await ctx.send(f'Now playing: {player.title}')

    @commands.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        if ctx.voice_client.source:
            ctx.voice_client.source.volume = volume / 100

        await ctx.send(f"Changed volume to {volume}%")

    @commands.command()
    @commands.has_role("quizmaster")
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect()

    @play.before_invoke
    @yt.before_invoke
    @begin.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()




intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    description='Relatively simple music bot example',
    intents=intents,
)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')


async def main():
    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(os.getenv('DISCORD_TOKEN_LEVEL99'))


asyncio.run(main())