import tweepy
from tweepy import TooManyRequests
import json
import requests
import base64
from datetime import datetime, timezone, timedelta
import pytz
import os
from unidecode import unidecode


class Retweet(object):
    def __init__(self):
        self.client_id = os.environ.get("CLIENT_ID")
        self.client_secret = os.environ.get("CLIENT_SECRET")
        self.banned_words = json.loads(os.environ.get("BANNED_WORDS"))
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
        self.do_retweets()
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

    @staticmethod
    def should_we_refresh_token(token):
        expires_at = datetime.fromtimestamp(token["expires_at"])
        if expires_at - datetime.now() <= timedelta(minutes=5):
            return True
        return False

    def refresh_token(self):
        authorization_bytes = f"{self.client_id}:{self.client_secret}".encode("utf8")
        authorization_b64_bytes = base64.b64encode(authorization_bytes)
        authorization_b64 = authorization_b64_bytes.decode("utf8")

        data = {
            "refresh_token": self.config["token"]["refresh_token"],
            "grant_type": "refresh_token",
            "client_id": self.client_id,
        }

        headers = {
            "Authorization": f"Basic {authorization_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        response = requests.post(
            "https://api.twitter.com/2/oauth2/token", data=data, headers=headers
        )
        response = response.json()

        self.config["token"]["access_token"] = response["access_token"]
        self.config["token"]["expires_at"] = (
            datetime.now().timestamp() + response["expires_in"]
        )
        self.config["token"]["refresh_token"] = response["refresh_token"]

        self.stats["refreshed_tokens"] += 1

        with open(file="config.json", mode="w+", encoding="utf8") as f:
            json.dump(self.config, f, ensure_ascii=False)

    def get_api_v2_client(self):
        if not self.config["token"]["access_token"]:
            oauth2_user_handler = tweepy.OAuth2UserHandler(
                client_id=self.client_id,
                redirect_uri="https://127.0.0.1",
                scope=["tweet.read", "tweet.write", "offline.access", "users.read"],
                client_secret=self.client_secret,
            )

            print(oauth2_user_handler.get_authorization_url())

            auth_response = input()

            access_token = oauth2_user_handler.fetch_token(auth_response)

            self.config["token"]["access_token"] = access_token["access_token"]
            self.config["token"]["expires_at"] = access_token["expires_at"]
            self.config["token"]["refresh_token"] = access_token["refresh_token"]

            with open(file="config.json", mode="w+", encoding="utf8") as f:
                json.dump(self.config, f, ensure_ascii=False)

        if self.should_we_refresh_token(self.config["token"]):
            self.refresh_token()

        self.v2_api = tweepy.Client(self.config["token"]["access_token"])

        self.stats["times_logged"] += 1

    def get_tweets(self):
        self.tweets = self.v2_api.search_recent_tweets(
            query="(alfajor OR alfajores) -is:retweet",
            max_results=100,
            sort_order="recency",
            expansions="entities.mentions.username",
        )
        self.logs.append(f"{self.datetime_now} Read {len(self.tweets.data)} tweets!")
        self.stats["retrieved_tweets"] += len(self.tweets.data)

    @staticmethod
    def check_tweet_mentions(tweet):
        if not tweet.entities:
            return
        if "mentions" not in tweet.entities:
            return
        modified_tweet_text = tweet.text
        mentions_alfajor = False
        for mention in tweet.entities["mentions"]:
            modified_tweet_text = modified_tweet_text.replace(
                f"@{mention['username']}", ""
            )
            if "alfajor" in unidecode(
                mention["username"].lower()
            ) or "alfajores" in unidecode(mention["username"].lower()):
                mentions_alfajor = True
        if not mentions_alfajor:
            return
        if (
            "alfajor" in modified_tweet_text.lower()
            or "alfajores" in modified_tweet_text.lower()
        ):
            return
        return True

    def do_retweets(self):
        n_retweets = 0
        n_already_retweeted = 0
        n_skipped = 0
        for tweet in self.tweets.data:
            try:
                if any(substring in tweet.text for substring in self.banned_words):
                    n_skipped += 1
                    self.logs.append(f"Skipping this tweet '{tweet.text}'")
                    continue
                if (
                    "alfajor" not in tweet.text.lower()
                    and "alfajores" not in tweet.text.lower()
                ):
                    n_skipped += 1
                    self.logs.append(f"Skipping this tweet '{tweet.text}'")
                    continue
                if tweet.id in self.config["retweets"]:
                    n_already_retweeted += 1
                    continue
                skip_tweet = self.check_tweet_mentions(tweet)
                if skip_tweet:
                    n_skipped += 1
                    self.logs.append(f"Skipping this tweet '{tweet.text}'")
                    continue
                self.v2_api.retweet(tweet_id=tweet.id, user_auth=False)
                self.config["retweets"].append(tweet.id)
                n_retweets += 1
                with open(file="config.json", mode="w+", encoding="utf8") as f:
                    json.dump(self.config, f, ensure_ascii=False)
            except TooManyRequests:
                self.logs.append(f"{self.datetime_now} RATELIMITED!")
                self.stats["ratelimits"] += 1
                break
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


if __name__ == "__main__":
    Retweet().run()
