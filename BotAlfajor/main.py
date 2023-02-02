import tweepy
from tweepy import TooManyRequests, BadRequest, HTTPException, TwitterServerError
import json
from datetime import datetime, timezone
import pytz
import os
from unidecode import unidecode
import backoff
import re


class Retweet(object):
    MAX_RESULT_SIZE = 500

    def __init__(self):
        self.consumer_key = os.environ.get("TWITTER_CONSUMER_KEY")
        self.consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET")
        self.banned_words = os.environ.get("BANNED_WORDS").split(",,,")
        self.config = {}
        self.v2_api = None
        self.tweets = None
        self.logs = []
        self.datetime_now = datetime.now(timezone.utc).astimezone(
            tz=pytz.timezone("America/Argentina/Buenos_Aires")
        )
        self.stats = {}

    def run(self):
        self.get_config_and_stats()
        self.get_api_v2_client()
        self.get_tweets()
        self.process_tweets()
        self.save_logs()
        self.save_stats()

    def get_config_and_stats(self):
        if not os.path.isfile("config.json"):
            with open(file="config.json", mode="w+", encoding="utf8") as f:
                json.dump(
                    {"retweets": [], "token": {"access_token": ""}},
                    f,
                    ensure_ascii=False,
                )
        with open(file="config.json", mode="r+", encoding="utf8") as f:
            self.config = json.load(f)
        if not os.path.isfile("stats.json"):
            with open(file="stats.json", mode="w+", encoding="utf8") as f:
                json.dump({}, f, ensure_ascii=False)
        with open(file="stats.json", mode="r+", encoding="utf8") as f:
            self.stats = json.load(f)
        if not self.stats:
            self.stats = {
                "last_time_ran": "",
                "times_ran": 0,
                "refreshed_tokens": 0,
                "times_logged": 0,
                "retrieved_tweets": 0,
                "times_retweeted": 0,
                "repeated_tweets": 0,
                "skipped_tweets": 0,
                "ratelimits": 0,
            }
        self.stats["last_time_ran"] = str(self.datetime_now)
        self.stats["times_ran"] += 1

    def get_api_v2_client(self):
        if "tokens" not in self.config or not self.config["tokens"]["access_token"]:
            oauth1_user_handler = tweepy.OAuth1UserHandler(
                self.consumer_key,
                self.consumer_secret,
                callback="oob",
            )

            print(oauth1_user_handler.get_authorization_url())

            verifier = input("PIN: ")

            access_token, access_token_secret = oauth1_user_handler.get_access_token(
                verifier
            )

            self.config["tokens"] = {
                "access_token": access_token,
                "access_token_secret": access_token_secret,
            }

            self.save_config()

        self.v2_api = tweepy.Client(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            access_token=self.config["tokens"]["access_token"],
            access_token_secret=self.config["tokens"]["access_token_secret"],
        )

        self.stats["times_logged"] += 1

    def get_tweets(self):
        next_token = None
        tweets = []
        while True:
            response = self.v2_api.search_recent_tweets(
                query="(alfajor OR alfajores) -is:retweet",
                max_results=100,
                sort_order="recency",
                expansions="entities.mentions.username",
                since_id=self.config.get("most_recent_tweet"),
                next_token=next_token,
                user_auth=True,
            )
            if response.data is None:
                break
            tweets.extend(response.data)
            if len(tweets) >= self.MAX_RESULT_SIZE:
                break
            if "next_token" not in response.meta:
                break
            next_token = response.meta["next_token"]
            if not self.config.get("most_recent_tweet"):
                break

        self.tweets = list(reversed(tweets))

        self.logs.append(f"{self.datetime_now} Read {len(self.tweets)} tweets!")
        self.stats["retrieved_tweets"] += len(self.tweets)

    @staticmethod
    def is_word_in_string(string):
        if re.search(r"\b(alfajor)\b", unidecode(string.lower())) or re.search(
            r"\b(alfajores)\b", unidecode(string.lower())
        ):
            return True
        return False

    def word_in_mentions(self, tweet):
        if not tweet.entities:
            return False
        if "mentions" not in tweet.entities:
            return False
        modified_tweet_text = tweet.text
        for mention in tweet.entities["mentions"]:
            modified_tweet_text = modified_tweet_text.replace(
                f"@{mention['username']}", ""
            )
        if self.is_word_in_string(modified_tweet_text):
            return False
        return True

    @backoff.on_exception(
        backoff.expo, (TwitterServerError, HTTPException), max_time=60
    )
    @backoff.on_exception(backoff.expo, TooManyRequests, max_tries=2)
    def do_retweet(self, tweet):
        try:
            self.v2_api.retweet(tweet_id=tweet.id, user_auth=True)
        except BadRequest:
            self.logs.append(f"Tweet was not found {tweet.id}")

    def process_tweets(self):
        n_retweets = 0
        n_already_retweeted = 0
        n_skipped = 0
        for tweet in self.tweets:
            former_most_recent_tweet = self.config.get("most_recent_tweet")
            self.config["most_recent_tweet"] = tweet.id
            self.save_config()
            if any(substring in tweet.text for substring in self.banned_words):
                n_skipped += 1
                self.logs.append(f"Skipping this tweet '{tweet.text}'")
                continue
            if not self.is_word_in_string(tweet.text):
                n_skipped += 1
                self.logs.append(f"Skipping this tweet '{tweet.text}'")
                continue
            if tweet.id in self.config["retweets"]:
                n_already_retweeted += 1
                continue
            if self.word_in_mentions(tweet):
                n_skipped += 1
                self.logs.append(f"Skipping this tweet '{tweet.text}'")
                continue
            try:
                self.do_retweet(tweet)
            except TooManyRequests:
                self.logs.append(f"{self.datetime_now} RATELIMITED!")
                self.stats["ratelimits"] += 1
                self.config["most_recent_tweet"] = former_most_recent_tweet
                self.save_config()
                break
            self.config["retweets"].append(tweet.id)
            n_retweets += 1
            self.save_config()
        self.logs.append(f"{self.datetime_now} Retweeted {n_retweets} tweets!")
        self.logs.append(
            f"{self.datetime_now} Skipped {n_already_retweeted} repeated tweets."
        )
        self.logs.append(f"{self.datetime_now} Skipped {n_skipped} tweets.")
        self.stats["times_retweeted"] += n_retweets
        self.stats["repeated_tweets"] += n_already_retweeted
        self.stats["skipped_tweets"] += n_skipped

    def save_logs(self):
        if not os.path.isfile("botalfajor.log"):
            with open(file="botalfajor.log", mode="w+", encoding="utf8") as f:
                f.write("")
        with open(file="botalfajor.log", mode="a+", encoding="utf8") as f:
            f.write("\n".join(self.logs) + "\n")

    def save_stats(self):
        with open(file="stats.json", mode="w+", encoding="utf8") as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=4)

    def save_config(self):
        with open(file="config.json", mode="w+", encoding="utf8") as f:
            json.dump(self.config, f, ensure_ascii=False)


if __name__ == "__main__":
    Retweet().run()
