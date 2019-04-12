from dotabase import *
import json
from finder import *

session = dotabase_session()

with open("tests/testdata.json", "r") as f:
	text = f.read()
testdata = json.loads(text)

def check_names():
	names = []
	for hero in session.query(Hero):
		names.append(hero.name)

	for thing in testdata:
		for hero in thing["heroes"]:
			if not hero in names:
				print(hero)

def test_clip(clip_info):
	print("testing:", clip_info["slug"])
	heroes = []
	for hero in session.query(Hero):
		if hero.name in clip_info["heroes"]:
			heroes.append(hero.localized_name)

	for meth in matching_methods:
		print(meth)
		matches = find_heroes(f"cache/{clip_info['slug']}.png", eval(meth))
		missing = heroes.copy()
		extra = []

		for match in matches:
			print(match)
			if match.hero.localized_name in missing:
				missing.remove(match.hero.localized_name)
			else:
				extra.append(match.hero.localized_name)

		if missing or extra:
			print("missing:")
			for hero in missing:
				print(f"- {hero}")
			print("extra:")
			for hero in extra:
				print(f"- {hero}")
		else:
			print("found all!")

		print("\n", flush=True)


test_clip(testdata[3])


#    4
# 4     4
#    16