# BotAlfajor
This is a simple script which uses the Twitter API to search and retweet tweets containing the word 'alfajor' or 'alfajores'.
Can be adapted for any other word the user may prefer.

## Usage
### Environmental variables
The script reads three different variables from the environment: `CLIENT_ID`, `CLIENT_SECRET`, and `BANNED_WORDS`
- `CLIENT_ID`: OAuth 2.0 Client ID, found in Twitter Developer Portal
- `CLIENT_SECRET`: OAuth 2.0 Client Secret, found in Twitter Developer Portal
- `BANNED_WORDS`: A `,,,` separated list of words that when present in a Tweet will make the script skip it

[This link](https://developer.twitter.com/en/docs/platform-overview) contains more info about the Twitter API and how to request an application.

I personally prefer to export/set these variables at the start of my cron file, but you can also set them in .bashrc for example.

This script requires Twitter API v2, so you will need elevated access.

### OAuth 2.0
This script needs access to your bot's Twitter Account. The first time it is run, an authorization URL will be printed out on your screen,
which you will have to open in your browser while logged in to your bot's account. If everything is working correctly, the page
should display an authorization box, by clicking "Authorize app", you are allowing your application to control the account.
After you clicked that button, you will be redirected, copy the new URL and paste it on the console running the script.
Now the access tokens will be stored in a json file, and you won't need to authorize the application again.