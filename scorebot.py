from datetime import datetime, time
from pathlib import Path
from typing import List, Optional
import warnings
import sys
import logging
from zoneinfo import ZoneInfo

from pytz import timezone
from telegram import Bot, Update
from telegram.ext import Updater, JobQueue, CallbackContext, CommandHandler

from Footy import MatchStatus
from Footy.Footy import Footy
from Footy.Table import Table
from Footy.Match import Match
from Footy.TeamData import reverseTeamLookup
from Footy.MatchStates import (
    Drawing,
    TeamLeadByOne, 
    TeamExtendingLead,
    TeamLosingLead,
    TeamDeficitOfOne,
    TeamExtendingDeficit,
    TeamLosingDeficit
)

# Set the chat ID
CHAT_ID = -701653934

class ScoreBot:
    def __init__(self) -> None:
        # Enable logging
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            level=logging.INFO)

        self.logger = logging.getLogger(__name__)

        try:
            # Get the token from the bot_token.txt file, this is exclued from git, so may not exist
            with open(Path('bot_token.txt'), 'r', encoding='utf8') as secretFile:
                token = secretFile.read()
        except:
            # If bot_token.txt is not available, print some help and exit
            print('No bot_token.txt file found, you need to put your token from BotFather in here')
            sys.exit()

        # List of chat IDs to respond to
        self.chatIdList: list[int] = []

        # Create a Footy object using the list of all teams
        self.footy = Footy()

        # Create the Updater and pass it your bot's token.
        # Make sure to set use_context=True to use the new context based callbacks
        # Post version 12 this will no longer be necessary
        self.updater = Updater(token, use_context=True)

        # Get the dispatcher to register handlers
        self.dp = self.updater.dispatcher

        # On receipt of a /start command call the start() function and /stop command to call the stop() function
        self.dp.add_handler(CommandHandler('start', self.start))
        self.dp.add_handler(CommandHandler('stop', self.stop))

        # Add chat IDs and list the chat IDs from another chat
        self.dp.add_handler(CommandHandler('add', self.add))
        self.dp.add_handler(CommandHandler('list', self.listChats))

        # Add a handler to get the table
        self.dp.add_handler(CommandHandler('table', self.GetTable))

        # Add a handler to answer questions
        self.dp.add_handler(CommandHandler('can', self.can))

        # Get the job queue
        self.jq: JobQueue = self.updater.job_queue

        # Add a job which gets todays matches once a day at 1am
        matchUpdateTime = time(1, 0, tzinfo=timezone('UTC'))
        nowTime = datetime.now(tz=ZoneInfo('UTC')).timetz()
        self.jq.run_daily(self.MatchUpdateHandler, matchUpdateTime)

        # Call Get Matches if this is started after the update time
        if nowTime > matchUpdateTime:
            self.GetMatches()

        # Add the error handler to log errors
        self.dp.add_error_handler(self.error)

        # Start the bot polling
        self.updater.start_polling()

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        self.updater.idle()

    def start(self, update: Update, context: CallbackContext) -> None:
        # Add the chat ID to the list if it isn't already in there
        if update.message.chat_id not in self.chatIdList:
            self.chatIdList.append(update.message.chat_id)
            print(f'Chat ID {update.message.chat_id} added')

    def stop(self, update: Update, context: CallbackContext) -> None:
        # If the user is me
        if update.message.from_user.first_name == 'Stephen' and update.message.from_user.last_name == 'Schleising':
            # If the chat ID is in the list remove it
            if update.message.chat_id in self.chatIdList:
                self.chatIdList.remove(update.message.chat_id)
                print(f'Chat ID {update.message.chat_id} removed')
        else:
            # Otherwise respond rejecting the request to stop me
            update.message.reply_text('Only my master can stop me !!', quote=False)

    def add(self, update: Update, context: CallbackContext) -> None:
        # If the user is me
        if update.message.from_user.first_name == 'Stephen' and update.message.from_user.last_name == 'Schleising':
            # Get the requested date
            commands: list[str] = update.message.text.split(' ')

            # Get the requested date if it exists in the command (only accessible by me)
            if len(commands) > 1:
                try:
                    chatId = int(commands[1])
                except:
                    print('Need to enter a single integer only')
                    update.message.reply_text('Need to enter a single integer only')
                else:
                    if chatId not in self.chatIdList:
                        self.chatIdList.append(chatId)
                        print(f'Chat ID {chatId} added')
                        update.message.reply_text(f'Chat ID {chatId} added')

    def listChats(self, update: Update, context: CallbackContext) -> None:
        # If the user is me send back the list of chats the bot is going to send to
        if update.message.from_user.first_name == 'Stephen' and update.message.from_user.last_name == 'Schleising':
            chatIds = '\n'.join(str(chatId) for chatId in self.chatIdList)
            print(f'Chat IDs:\n{chatIds}')
            update.message.reply_text(f'Chat IDs:\n{chatIds}', quote=False)

    def GetTable(self, update: Update, context: CallbackContext) -> None:
        table = Table()
        print(table.condensedTable)
        update.message.reply_markdown_v2(table.condensedTable, quote=False)

    def can(self, update: Update, context: CallbackContext) -> None:
        # Log the request
        print(f'{update.message.from_user.first_name} {update.message.from_user.last_name} in chat {update.message.chat.title} asked {update.message.text}')

        # Get the request
        request = update.message.text.lower().replace('?', '').split()[1:]

        # Get a table object
        table = Table()

        # Test for the first team name being in two parts
        test = ''.join(request[0:2])

        # If the first team name is in two parts join them together and insert that at the start of the
        # list replacing the original two entries
        if test in reverseTeamLookup:
            request.insert(0, ''.join((request.pop(0), request.pop(0))))

        # Match the request
        match request:
            # Can team A still beat team B
            case [teamA, 'beat', *teamB] | [teamA, 'still', 'beat', *teamB]:
                # If team B is in two parts join them togther
                teamB = ''.join(teamB)
                # Ensure both teams are in the lookup table
                if teamA in reverseTeamLookup and teamB in reverseTeamLookup:
                    # Check whether team A can beat team B
                    if table.CanTeamABeatTeamB(reverseTeamLookup[teamA], reverseTeamLookup[teamB]):
                        response = 'Yes'
                    else:
                        response = 'No'
                else:
                    # Standard response
                    response = "Don't ask stupid questions"
            # Can team still win the league
            case [team, 'win', 'the', 'league'] | [team, 'still', 'win', 'the', 'league']:
                # Check the team is in the lookup table
                if team in reverseTeamLookup:
                    # Check whether the team can win the league
                    if table.CanTeamWinTheLeague(reverseTeamLookup[team]):
                        response = 'Yes'
                    else:
                        response = 'No'
                else:
                    # Standard response
                    response = "Don't ask stupid questions"
            case _:
                # Standard response
                response = "Don't ask stupid questions"

        # Log and send the response
        print(response)
        update.message.reply_text(response)

    def MatchUpdateHandler(self, context: CallbackContext) -> None:
        # Call get matches, this allows the function to be called directly
        self.GetMatches()

    def GetMatches(self) -> None:
        # Log that we are updating today's matches
        print('Updating matches')

        # Get today's matches for the teams in the list
        todaysMatches = self.footy.GetMatches()

        # If the download was successful, print the matches
        if todaysMatches is not None:
            # Create a set for the start times
            startTimes = set()

            # Iterate over the matches
            for match in todaysMatches:
                # Print the match details
                print(match)

                # If the match is not finished add the start time to a set
                if match.status in MatchStatus.matchToBePlayedList:
                    if match.matchDate > datetime.now(ZoneInfo('UTC')):
                        # If the match start is in the future, schedule the request for updates
                        startTimes.add(match.matchDate)
                    else:
                        # If the match has already started, request an update immediately
                        startTimes.add(0)

            # Set the context to the list of matches
            matchContext = todaysMatches

            # Iterate through the start times
            for startTime in startTimes:
                # Add a job to check the scores once the game starts
                self.jq.run_once(self.SendScoreUpdates, startTime, context=matchContext)
        else:
            print('Download Failed')

    def SendMessage(self, bot: Bot, message: Optional[str]):
        if message is not None:
            for chatId in self.chatIdList:
                bot.send_message(chat_id=chatId, text=message)
            print(message)
        else:
            print('No Status Change')

    def SendScoreUpdates(self, context: CallbackContext) -> None:
        if context.job is not None and isinstance(context.job.context, list):
            oldMatchList: list[Match] = context.job.context
            newMatchList: Optional[list[Match]] = self.footy.GetMatches(oldMatchList=oldMatchList)

            # If all matches are finished this will remain false and the loop will end
            requestUpdates = False

            if newMatchList:
                # Loop through the matche updates
                for newMatchData in newMatchList:
                    message = None

                    # Check if this is the start of the match
                    if newMatchData.matchChanges.fullTime:
                        # Send final score
                        message = f'Full Time\n{str(newMatchData)}'
                    else:
                        if newMatchData.matchChanges.firstHalfStarted:
                            # Send match started
                            message = f'Kick Off\n{str(newMatchData)}'
                        elif newMatchData.matchChanges.goalScored:
                            # Send score update
                            message = str(newMatchData)

                    # Send the message
                    self.SendMessage(context.bot, message)

                    if newMatchData.status in MatchStatus.matchToBePlayedList:
                        # If any matches are still in progress or yet to be started then keep requesting updates
                        requestUpdates = True

                if requestUpdates:
                    # Add a job to check the scores again in 10 seconds
                    self.jq.run_once(self.SendScoreUpdates, 10, context=newMatchList)
            else:
                # This update failed, try again in 20 seconds using the old match data as the context
                self.jq.run_once(self.SendScoreUpdates, 20, context=oldMatchList)
        else:
            return

    # Log errors
    def error(self, update, context: CallbackContext) -> None:
        self.logger.warning('Update "%s" caused error "%s"', update, context.error)

# Main function
def main() -> None:
    # Filter out a warning from dateparser
    warnings.filterwarnings('ignore', message='The localize method is no longer necessary')

    # Start the score bot
    ScoreBot()

if __name__ == '__main__':
    # Call the main function
    main()
