from dotabase import *
import json
from finder import *
from clipprocessing import *
import cv2
import praw
import re

session = dotabase_session()

with open("tests/testdata.json", "r") as f:
	text = f.read()
testdata = json.loads(text)

testlog = ""

def logprint(text):
	global testlog
	testlog += str(text) + "\n"
	print(text, flush=True)

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

def create_positions():
	positions = []
	for clip_info in testdata:
		clip_frame = get_first_clip_frame(clip_info["slug"])
		image = Image.open(clip_frame).convert("RGB")
		image_ratio = image.size[1] / 2160
		matches = find_heroes(clip_frame, cv2.TM_CCOEFF_NORMED)
		temp = []
		for match in matches:
			temp.append(match.point[0] / image_ratio)
		positions.append(temp)
	for i in range(10):
		total = 0
		for clip_pos in positions:
			total += clip_pos[i]
		total = total / len(positions)
		print(total)


def test_clip(clip_info, method):
	logprint(f"testing:{clip_info['slug']}")
	heroes = []
	for hero in session.query(Hero):
		if hero.name in clip_info["heroes"]:
			heroes.append(hero.localized_name)

	clip_frame = get_first_clip_frame(clip_info["slug"])

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

	logprint("\n")

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

# for clip in testdata:
# 	test_clip(clip, cv2.TM_CCOEFF_NORMED)
# with open("temp/testlog.txt", "w+") as f:
# 	f.write(testlog)

check_reddit_clips()
# check_names()


# create_positions()