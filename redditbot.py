import json
import praw
import prawcore
import time
import os
import re
import finder


with open("config.json", "r") as f:
	config = json.loads(f.read())

cache_file = "reddit_cache.json"
reddit = None

reddit_me = "^[/u\/EuphonicPotato](/user/EuphonicPotato)"
github_url = "https://github.com/mdiller/twitchclipmatchfinder"
reddit_comment_footer = f"\n\n---\n*^I ^am ^a ^bot ^created ^by {reddit_me}*\n\n*^(Source/Description:)* [*^(GitHub)*]({github_url})"


def read_cache():
	if os.path.exists(cache_file):
		with open(cache_file, "r") as f:
			return json.loads(f.read())
	else:
		return {
			"replied_posts": []
		}

def save_cache(cache):
	with open(cache_file, "w+") as f:
		f.write(json.dumps(cache, indent="\t"))

def create_reddit_response(match_info):
	response = f"Looks like this is match {match_info['match_id']}"
	if match_info.get("better_minutes_diff"):
		response += f", which started {match_info['better_minutes_diff']} minutes before the clip was recorded."
	else:
		response += f", which started {match_info['minutes_diff']} minutes before the clip was taken."

	response += "\n\nMore match details here:\n"
	match_id = match_info['match_id']
	response += f"\n- [OpenDota](https://www.opendota.com/matches/{match_id})"
	response += f"\n- [Dotabuff](https://www.dotabuff.com/matches/{match_id})"
	response += f"\n- [Stratz](https://www.stratz.com/matches/{match_id})"
	response += reddit_comment_footer
	return response

def bot_check_posts():
	cache = read_cache()
	for post in reddit.subreddit("dota2").new(limit=100):
		if post.id in cache["replied_posts"]:
			continue # already replied to this post
		match = re.match(r"^https?://clips\.twitch\.tv/([^\?]*)(\?.*)?$", post.url)
		if match:
			slug = match.group(1)
			match_info = None
			try: 
				match_info = finder.find_match(slug)
			except finder.ClipFinderException as e:
				print(f"encountered {type(e).__name__} for slug {slug} on post {post.id}")
				pass
			if match_info is not None:
				print(f"found match {match_info['match_id']} on post {post.id}, via slug {slug}")
				response = create_reddit_response(match_info)
				try:
					post.reply(response)
				except praw.exceptions.APIException as e:
					print("getting ratelimited, quitting")
					return
				cache["replied_posts"].append(post.id)
				save_cache(cache)

def run_bot():
	global reddit
	reddit = praw.Reddit(client_id=config["reddit"]["client_id"],
		client_secret=config["reddit"]["client_secret"],
		user_agent=config["reddit"]["user_agent"],
		username=config["reddit"]["username"],
		password=config["reddit"]["password"])
	while True:
		try:
			bot_check_posts()
		except prawcore.exceptions.ServerError:
			print("praw threw servererror, skipping")
		except prawcore.exceptions.ResponseException:
			print("praw threw responseexception, skipping")
		time.sleep(60)


if __name__ == '__main__':
	run_bot()

