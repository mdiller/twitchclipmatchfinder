from dotabase import *
import json

session = dotabase_session()

names = []
for hero in session.query(Hero):
	names.append(hero.name)


with open("testdata.json", "r") as f:
	text = f.read()

data = json.loads(text)

for thing in data:
	for hero in thing["heroes"]:
		if not hero in names:
			print(hero)
