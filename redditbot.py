import json
import praw
import prawcore
import time
import os
import re
import requests
import finder
import time
from praw.models import Comment, Submission as Post


with open("config.json", "r") as f:
	config = json.loads(f.read())

DEBUG = config.get("debug", False)

if DEBUG:
	print("DEBUG: True")

MatchNotFound_hours_timeout = 6 # the number of hours to wait till giving up on finding the match (when getting MatchNotFoundException)

posts_to_revisit = set() # a set of posts for which we found the heroes, but got a MatchNotFoundException, and aren't too old (see MatchNotFound_hours_timeout)
checked_posts = set() # a set of post ids that we've already checked.

reddit: praw.Reddit
reddit = None

reddit_me = "^[/u\/EuphonicPotato](/user/EuphonicPotato)"
github_url = "https://github.com/mdiller/twitchclipmatchfinder"
github_explanation_url = "https://github.com/mdiller/twitchclipmatchfinder#how-it-works"
reddit_comment_footer = f"\n\n---\n*^I ^am ^a ^bot ^created ^by {reddit_me}*\n\n*^(How I figured this out:)* [*^(Explanation)*]({github_explanation_url})\n\n*^(Source:)* [*^(GitHub)*]({github_url})"

twitch_clip_url_pattern = r"^https?://clips\.twitch\.tv/([^\?]*)(\?.*)?$"

# subreddits we'll act on when summoned via a username mention - deliberately not
# account-wide, since inbox mentions can come from anywhere on reddit
allowed_mention_subreddits = {"dota2"}

handled_mentions_file = os.path.join("cache", "handled_mentions.json")
handled_mentions_ttl_days = 7 # matches the clean_data_cache retention used elsewhere

reply_unsupported_video = (
	"Sorry, I don't know how to parse this post - I can currently only handle Twitch "
	"clip links and native Reddit-hosted videos (v.redd.it)." + reddit_comment_footer
)
reply_no_heroes_found = (
	"I looked at this video but couldn't clearly make out all 10 heroes in the top bar, "
	"so I can't identify the match. This can happen if the hero bar is hidden or cropped "
	"out, or if the clip isn't actually Dota gameplay." + reddit_comment_footer
)
reply_match_not_found = (
	"I found the 10 heroes, but couldn't find a matching game in OpenDota's database. "
	"This can happen for very recent matches that haven't been indexed yet, or for "
	"private/unranked lobby games that aren't publicly recorded." + reddit_comment_footer
)
reply_match_too_early = (
	"This looks like it's from before OpenDota's match-finding data starts (~April 2019), "
	"so I can't look it up." + reddit_comment_footer
)
reply_generic_error = (
	"Something went wrong while I was trying to process this - could be a temporary issue "
	"reaching Twitch/Reddit/OpenDota. Feel free to mention me again later." + reddit_comment_footer
)
reply_already_answered = (
	"Looks like I've already found a match for this post - check my other comment on it!"
	+ reddit_comment_footer
)

# raised when a post doesn't link a video source we know how to parse
class UnsupportedPostException(Exception):
	pass

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
	response += f", which started {format_delta_minutes(minutes_diff)} before the clip was {event}."

	response += "\n\nMore match details here:\n"
	match_id = match_info['match_id']
	response += f"\n- [OpenDota](https://www.opendota.com/matches/{match_id})"
	response += f"\n- [Dotabuff](https://www.dotabuff.com/matches/{match_id})"
	response += f"\n- [Stratz](https://www.stratz.com/matches/{match_id})"
	if match_info.get("league_name"):
		response += f"\n- [datdota](https://www.datdota.com/matches/{match_id})"
	response += reddit_comment_footer
	return response

# checks if we've already left a comment on this post (used to avoid double-replying)
def post_already_commented(post):
	comment: Comment
	for comment in post.comments:
		if comment.author and comment.author.name == config["reddit"]["username"]:
			return True
	return False

# figures out how to parse the given submission's video and returns match_info, or
# raises UnsupportedPostException if we don't know how to handle this post's source,
# or one of finder's ClipFinderException subclasses if parsing was attempted but failed
def find_match_for_post(post):
	match = re.match(twitch_clip_url_pattern, post.url)
	if match:
		return finder.find_match(match.group(1), False)

	if getattr(post, "is_video", False):
		media = post.media or getattr(post, "secure_media", None)
		reddit_video = (media or {}).get("reddit_video") if media else None
		fallback_url = reddit_video.get("fallback_url") if reddit_video else None
		if fallback_url:
			return finder.find_match_from_reddit_video(post.id, fallback_url, post.created_utc)

	raise UnsupportedPostException()

def load_handled_mentions():
	if os.path.exists(handled_mentions_file):
		with open(handled_mentions_file, "r") as f:
			try:
				return json.loads(f.read())
			except json.decoder.JSONDecodeError:
				return {}
	return {}

def save_handled_mentions(data):
	if not os.path.exists("cache"):
		os.mkdir("cache")
	with open(handled_mentions_file, "w+") as f:
		f.write(json.dumps(data, indent="\t"))

# drops entries older than handled_mentions_ttl_days so this doesn't grow forever
def prune_handled_mentions(data):
	cutoff = time.time() - (handled_mentions_ttl_days * 86400)
	return {post_id: entry for post_id, entry in data.items() if entry.get("handled_at", 0) > cutoff}

def print_mention_status(mention, post, status):
	reddit_url = f"https://redd.it/{post.id}"
	print(f"{reddit_url.rjust(24)} | {status.ljust(30)} | mention by u/{mention.author}")

# maps a submission to (reply_body, status_text_for_logging, status_to_cache)
def resolve_mention_response(post):
	try:
		match_info = find_match_for_post(post)
		return create_reddit_response(match_info), f"Match: {match_info['match_id']}", "matched"
	except UnsupportedPostException:
		return reply_unsupported_video, "Unsupported video", "unsupported"
	except finder.MatchTooEarlyException:
		return reply_match_too_early, "Too early", "too_early"
	except finder.HeroFindingException:
		return reply_no_heroes_found, "Could not find heroes", "no_heroes"
	except finder.MatchNotFoundException:
		return reply_match_not_found, "No match found", "no_match"
	except finder.ClipFinderException as e:
		return reply_generic_error, f"ERROR: {type(e).__name__}", "error"

def bot_check_mentions():
	print_debug("entering: bot_check_mentions")
	handled = prune_handled_mentions(load_handled_mentions())
	changed = False

	mention: Comment
	for mention in reddit.inbox.mentions(limit=25):
		try:
			if not isinstance(mention, Comment) or not mention.new:
				continue

			if str(mention.subreddit).lower() not in allowed_mention_subreddits:
				mention.mark_read()
				continue

			post = mention.submission
			post_key = post.id

			if post_key in handled:
				mention.mark_read()
				continue

			if post_already_commented(post):
				response, status, cache_status = reply_already_answered, "Already commented", "matched"
			else:
				response, status, cache_status = resolve_mention_response(post)

			handled[post_key] = {"handled_at": time.time(), "status": cache_status}
			print_mention_status(mention, post, status)
			changed = True

			if not DEBUG:
				try:
					mention.reply(body=response)
				except praw.exceptions.APIException as e:
					print("getting ratelimited on mention replies, stopping this pass")
					mention.mark_read()
					break

			mention.mark_read()
		except Exception as e:
			print(f"error handling mention {getattr(mention, 'id', '?')}: {type(e).__name__}: {e}")
			continue

	if changed:
		save_handled_mentions(handled)

def bot_check_posts():
	print_debug("entering: bot_check_posts")
	MatchNotFound_time_cutoff = time.time() - (60 * 60 * MatchNotFound_hours_timeout)
	time_filter = "week" if DEBUG else "day"
	post: Post
	# this emulates https://old.reddit.com/search?q=site%3Atwitch.tv+subreddit%3Adota2&sort=new&t=all
	for post in reddit.subreddit("dota2").search("site:twitch.tv", sort="new", time_filter=time_filter):
		if post.id in checked_posts:
			continue
		checked_posts.add(post.id)
		match = re.match(twitch_clip_url_pattern, post.url)
		if match:
			slug = match.group(1)
			match_info = None
			try: 
				match_info = finder.find_match(slug, False)
			except finder.ClipFinderException as e:
				should_print_status = True
				if isinstance(e, finder.HeroFindingException):
					status = "Not A Match"
				elif isinstance(e, finder.MatchNotFoundException) and (post.created_utc > MatchNotFound_time_cutoff):
					status = "Heroes found. No match yet..."
					if post.id in posts_to_revisit:
						should_print_status = False
					else:
						posts_to_revisit.add(post.id)
					checked_posts.remove(post.id) # revisit this later
				else:
					status = f"ERROR: {type(e).__name__}"
				if should_print_status:
					print_post_status(post, slug, status)
			if match_info is not None:
				response = create_reddit_response(match_info)
				status = f"Match: {match_info['match_id']}"

				already_commented = post_already_commented(post)
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
			# bot_check_mentions() # disabled for now - decided against letting anyone @ the bot to trigger it
		except prawcore.exceptions.ServerError:
			print("praw threw servererror, skipping")
		except prawcore.exceptions.ResponseException:
			print("praw threw responseexception, skipping")
		if "healthchecks_url" in config:
			requests.post(config["healthchecks_url"])
		# Check every x minutes
		minutes_to_sleep = 10
		print_debug(f"sleeping for {minutes_to_sleep} mins")
		time.sleep(60 * minutes_to_sleep)


if __name__ == '__main__':
	run_bot()

