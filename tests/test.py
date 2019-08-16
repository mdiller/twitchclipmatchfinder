from dotabase import *
import json
import cv2
import praw
import re
import os
import sys
import inspect

current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir) 
from finder import *

session = dotabase_session()

test_dir = os.path.dirname(os.path.realpath(__file__))

with open(os.path.join(test_dir, "testdata.json"), "r") as f:
	testdata = json.loads(f.read())

testlog = ""

def logprint(text):
	global testlog
	testlog += str(text) + "\n"
	print(text, flush=True)

# helper function which will show the template images
def dump_templates(match):
	count = 0
	for img in match.images:
		postfix = ""
		if count:
			postfix = f"_{count}"
		count += 1
		cv2.imwrite(f"cache/templates/{match.hero.name}{postfix}.png", img)


def check_names():
	names = []
	for hero in session.query(Hero):
		names.append(hero.name)

	for thing in testdata:
		for hero in thing["heroes"]:
			if not hero in names:
				logprint(hero)

def test_clip(clip_info, method):
	slug = clip_info["slug"]
	logprint(f"testing:{slug}")
	heroes = []
	for hero in session.query(Hero):
		if hero.name in clip_info["heroes"]:
			heroes.append(hero.localized_name)

	clip_frame = get_first_clip_frame(slug)

	matches = find_heroes(clip_frame, method, 5, True)
	missing = heroes.copy()
	extra = []

	for i in range(len(matches)):
		match = matches[i]
		if i == 10:
			logprint("-----------------------------------------------------")
		logprint(match)
		# dump_templates(match)

	matches = matches[:10]

	for match in matches:
		if match.hero.localized_name in missing:
			missing.remove(match.hero.localized_name)
		else:
			extra.append(match.hero.localized_name)

	if missing or extra:
		logprint("missing:")
		for hero in missing:
			logprint(f"- {hero}")
		logprint("extra:")
		for hero in extra:
			logprint(f"- {hero}")
	else:
		logprint("found all!")

	expected_match = clip_info.get("match_id")
	if not expected_match is None:
		match_info = find_match(slug)
		if match_info["match_id"] == expected_match:
			print("found match!")
		else:
			print(f"couldn't find match. expected {expected_match}, actual {match_info['match_id']}")

	logprint("\n")

# outdated
def check_reddit_clips():
	reddit = praw.Reddit(client_id=config["reddit"]["client_id"],
		client_secret=config["reddit"]["client_secret"],
		user_agent=config["reddit"]["user_agent"],
		username=config["reddit"]["username"],
		password=config["reddit"]["password"])

	with open("reddit_cache.json", "r") as f:
		data = json.loads(f.read())
	for postid in data["replied_posts"]:
		post = reddit.submission(id=postid)
		match = re.match(r"^https?://clips\.twitch\.tv/([^\?]*)(\?.*)?$", post.url)
		slug = match.group(1)
		match_info = find_match(slug)
		print(f"old: {match_info['minutes_diff']} minutes")
		if match_info.get('other_minutes_diff'):
			print(f"new: {match_info['other_minutes_diff']} minutes")
		else:
			print("new: not found")

# test all clips saved in testdata
for clip in testdata:
 	test_clip(clip, cv2.TM_CCOEFF_NORMED)

# check_reddit_clips()
