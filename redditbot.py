import json
import praw
import prawcore
import time
import os
import re
import requests
import finder
from praw.models import Comment, Submission as Post


with open("config.json", "r") as f:
	config = json.loads(f.read())

DEBUG = config.get("debug", False)

if DEBUG:
	print("DEBUG: True")

checked_posts = set()

reddit: praw.Reddit
reddit = None

reddit_me = "^[/u\/EuphonicPotato](/user/EuphonicPotato)"
github_url = "https://github.com/mdiller/twitchclipmatchfinder"
github_explanation_url = "https://github.com/mdiller/twitchclipmatchfinder#how-it-works"
reddit_comment_footer = f"\n\n---\n*^I ^am ^a ^bot ^created ^by {reddit_me}*\n\n*^(How I figured this out:)* [*^(Explanation)*]({github_explanation_url})\n\n*^(Source:)* [*^(GitHub)*]({github_url})"

# prints that only go off during debug mode
def print_debug(text):
	if DEBUG:
		print(text)

# prints the status of this post to console out
def print_post_status(post: Post, slug: str, status: str):
	reddit_url = f"https://redd.it/{post.id}"
	twitch_url = f"https://clips.twitch.tv/{slug}"
	if DEBUG and not ("Match: " in status):
		title = post.title
		max_title_len = 75
		if len(title) > max_title_len:
			title = title[:max_title_len - 3] + "..."
		twitch_url = f"{twitch_url.ljust(78)} | {title}"
	print(f"{reddit_url.rjust(24)} | {status.ljust(30)} | {twitch_url}")

# clears the data cache of all files older than cache_age_limit days
def clean_data_cache(data_cache_dir, cache_age_limit):
	now = time.time()
	for f in os.listdir(data_cache_dir):
		filename = os.path.join(data_cache_dir, f)
		if os.path.isfile(filename) and os.stat(filename).st_mtime < now - (cache_age_limit * 86400):
			os.remove(filename)


_TIME_LIMITS = [("day", 24 * 60), ("hour", 60), ("minute", 1)]

def format_delta_minutes(delta_minutes: int) -> str:
	"""Formats `delta_minutes` into a human-readable string."""
	# Nasty edge case. This ends up spelling "which started right before ..."
	if delta_minutes == 0:
		return "right"
	formatted = []
	for name, limit in _TIME_LIMITS:
		if delta_minutes >= limit:
			qot, delta_minutes = divmod(delta_minutes, limit)
			actual_name = f"{name}s" if qot > 1 else name
			formatted.append(f"{qot} {actual_name}")
	return ", ".join(formatted)

def create_reddit_response(match_info):
	response = f"Looks like this is match {match_info['match_id']}"
	if match_info.get("team_rad") and match_info.get("team_dire") and match_info.get("league_name"):
		response += f", {match_info['team_rad']} vs {match_info['team_dire']} at {match_info['league_name']}"	

	if "better_minutes_diff" in match_info:
		minutes_diff = match_info["better_minutes_diff"]
		event = "recorded"
	else:
		minutes_diff = match_info["minutes_diff"]
		event = "taken"
	response += f", which started {format_timedelta(minutes_diff)} before the clip was {event}."

	response += "\n\nMore match details here:\n"
	match_id = match_info['match_id']
	response += f"\n- [OpenDota](https://www.opendota.com/matches/{match_id})"
	response += f"\n- [Dotabuff](https://www.dotabuff.com/matches/{match_id})"
	response += f"\n- [Stratz](https://www.stratz.com/matches/{match_id})"
	if match_info.get("league_name"):
		response += f"\n- [datdota](https://www.datdota.com/matches/{match_id})"
	response += reddit_comment_footer
	return response

def bot_check_posts():
	print_debug("entering: bot_check_posts")
	time_filter = "week" if DEBUG else "day"
	post: Post
	# this emulates https://old.reddit.com/search?q=site%3Atwitch.tv+subreddit%3Adota2&sort=new&t=all
	for post in reddit.subreddit("dota2").search("site:twitch.tv", sort="new", time_filter=time_filter):
		if post.id in checked_posts:
			continue
		checked_posts.add(post.id)
		match = re.match(r"^https?://clips\.twitch\.tv/([^\?]*)(\?.*)?$", post.url)
		if match:
			slug = match.group(1)
			match_info = None
			try: 
				match_info = finder.find_match(slug, False)
			except finder.ClipFinderException as e:
				if isinstance(e, finder.HeroFindingException):
					status = "Not A Match"
				else:
					status = f"ERROR: {type(e).__name__}"
				print_post_status(post, slug, status)
				pass
			if match_info is not None:
				response = create_reddit_response(match_info)
				status = f"Match: {match_info['match_id']}"

				already_commented = False
				comment: Comment
				for comment in post.comments:
					if comment.author.name == config["reddit"]["username"]:
						already_commented = True
				if already_commented:
					status += " (commented)"
				print_post_status(post, slug, status)

				if not (DEBUG or already_commented):
					try:
						post.reply(body=response)
					except praw.exceptions.APIException as e:
						print("getting ratelimited, quitting")
						checked_posts.remove(post.id)
						return

def run_bot():
	global reddit
	print("starting bot...")
	reddit = praw.Reddit(client_id=config["reddit"]["client_id"],
		client_secret=config["reddit"]["client_secret"],
		user_agent=config["reddit"]["user_agent"],
		username=config["reddit"]["username"],
		password=config["reddit"]["password"])
	while True:
		try:
			clean_data_cache("cache", 7) # directory, days of data to keep
			bot_check_posts()
		except prawcore.exceptions.ServerError:
			print("praw threw servererror, skipping")
		except prawcore.exceptions.ResponseException:
			print("praw threw responseexception, skipping")
		if "healthchecks_url" in config:
			requests.post(config["healthchecks_url"])
		# Check every 5 minutes
		print_debug("sleeping for 5 mins")
		time.sleep(60 * 5)


if __name__ == '__main__':
	run_bot()

