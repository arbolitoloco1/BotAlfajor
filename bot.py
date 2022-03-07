import tweepy
from tweepy import TweepyException

twitter_oauth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
twitter_oauth.set_access_token(TOKEN, SECRET)
api = tweepy.API(twitter_oauth, wait_on_rate_limit=True)

tweets = tweepy.Cursor(api.search_tweets, q="(alfajor OR alfajores) -filter:replies", result_type='recent').items(100)

for tweet in tweets:
    try:
        api.retweet(id=tweet.id)
        print("Retwiteado!")
    except tweepy.TweepyException as e:
        print(e)
        continue
