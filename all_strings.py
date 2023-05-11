LOAD_SUCCESS = """:white_check_mark: **All songs have been successfully downloaded!** 
As the **quizmaster**, you can use the `!begin` command (on the server) to start the game!"""

GENERAL_WELCOME = """:musical_note: Welcome to the blindtest quiz!
First, **create or join a team** with the `!team team_name` command.
Then wait for the game to begin.

The quizmaster can send me the CSV list as an attachment in a DM message with the command `!loadcsv`."""

TEAM_WELCOME = """The quiz is about to begin!

:clipboard: **Rules**
- For each song, your team can submit one guess using the !guess something command.
- Guessing right first will give you the voting privileges for the next song!
- Guessing wrong will strip you of your voting privileges!
- If every team guesses wrong or waits for the time to be up, every team gets to vote

:fire: **Tips**
- You can adjust the music volume by right clicking on the bot in the voice channel UI."""

VOTE_EMOJIS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '0️⃣']

def build_vote_message(categories):
    message = """:ballot_box: **Choose a category**
React to this message to cast your vote for the next question's category!
"""

    for i in range(1, len(categories) + 1):
        message += f"\n**{VOTE_EMOJIS[i-1]} {categories[i-1]}**"

    return message

def build_start_song_message(category):
    return f':headphones: Here is a song from the **{category}** category!'

THIRTY_SECONDS_LEFT = ':clock3: Only 30 seconds left!'
TEN_SECONDS_LEFT = ':clock3: Only 10 seconds left!'
def build_times_left_message(time_left):
    return f':clock3: You have {time_left} seconds!'

def build_times_up_message(answer, url, everyone_answered):
    return f"""{":alarm_clock: Time's up! " if not everyone_answered else ""}The answer was **{answer}**:
{url}"""

def build_guessed_right_message(team):
    return f':white_check_mark: **Team {team}** guessed correctly!'

def build_guessed_wrong_message(team):
    return f':x: **Team {team}** guessed incorrectly. Womp womp :postal_horn:'

def build_everyone_guesses_message(team_and_answers):
    message = 'This is what everyone guessed:'
    for team, answer in team_and_answers.items():
        message += f'\n- **Team {team}**: {answer}'
    return message

GAME_FINISHED = ':trophy: Game finished! **Congratulations to everyone!**'

GAME_PAUSED = ':pause_button: The game has been paused.'
GAME_RESUMED = ':arrow_forward: The game has been resumed.'

TEAM_DOES_NOT_EXIST = 'Team does not exist.'

def build_next_voting_team_message(team):
    return f':ballot_box: Next voting team will be **team {team}**.'