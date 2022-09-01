from dotabase import *
import json
import cv2
import shutil
import praw
import re
import os
import sys
import inspect
import sys

current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir) 
from finder import *

session = dotabase_session()

result_char_success = "✔️"
result_char_fail = "❌"

VERBOSE = False

test_cache_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "images")
test_dir = os.path.dirname(os.path.realpath(__file__))
test_data_file = os.path.join(test_dir, "testdata.json")

with open(test_data_file, "r") as f:
	testdata = json.loads(f.read())

# helper function which will show the template images
def dump_templates(match):
	count = 0
	for img in match.images:
		postfix = ""
		if count:
			postfix = f"_{count}"
		count += 1
		cv2.imwrite(f"cache/templates/{match.hero.name}{postfix}.png", img)

def test_clip(clip_info, method):
	slug = clip_info["slug"]
	expected_heroes = clip_info["heroes"]

	clip_frame = os.path.join(test_cache_dir, f"{slug}.png")

	success = True
	matches = find_heroes(clip_frame, method)
	for i in range(len(matches)):
		if matches[i].hero.name != clip_info["heroes"][i]:
			success = False

	if success:
		print(f"{result_char_success} {slug}", flush=True)
		pass
	else:
		print(f"{result_char_fail} {slug}", flush=True)
		print("Found heroes:")
		for i in range(len(matches)):
			if matches[i].hero.name != expected_heroes[i]:
				print(f" + {matches[i].hero.localized_name} (expected: {expected_heroes[i]})")
			else:
				print(f" - {matches[i].hero.localized_name}")

		print("More info:")
		matches = find_heroes(clip_frame, method, 5, True)
	
		for i in range(len(matches)):
			match = matches[i]
			if i == 10:
				print("-----------------------------------------------------")
			print(match)
			# dump_templates(match)

	expected_match = clip_info.get("match_id")
	if not expected_match is None:
		match_info = find_match(slug)
		if match_info["match_id"] == expected_match:
			print("found match!")
		else:
			print(f"couldn't find match. expected {expected_match}, actual {match_info['match_id']}")

# generates an example test entry from the given slug, copying the frame file to the cache
def generate_test_entry(slug):
	for clip_info in testdata:
		if clip_info.get("slug") == slug:
			print("That slug is already in the testdata")
			return
	print(f"creating new entry: https://clips.twitch.tv/{slug}")
	clip_frame = get_first_clip_frame(slug)
	
	new_frame_file = os.path.join(test_cache_dir, f"{slug}.png")
	shutil.copyfile(clip_frame, new_frame_file)

	matches = find_heroes(new_frame_file, cv2.TM_CCOEFF_NORMED)
	
	heronames = []
	for match in matches:
		print(" - " + match.hero.localized_name)
		heronames.append(match.hero.name)
	
	clip_info = {
		"slug": slug,
		"heroes": heronames
	}
	testdata.append(clip_info)
	with open(test_data_file, "w+") as f:
		f.write(json.dumps(testdata, indent="\t"))


if __name__ == '__main__':
	if len(sys.argv) > 1:
		if sys.argv[1] == "add" and len(sys.argv) == 3:
			generate_test_entry(sys.argv[2])
		else:
			print("Not sure what you wanna do. Do 'add <slugname>' to add a new testcase")
	else:
		for clip_info in testdata:
			test_clip(clip_info, cv2.TM_CCOEFF_NORMED)
