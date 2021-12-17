import json
import os
from dotabase import *



# This is a script for auto-generating the arcana_links.json file
# note that to run this script you'll have to have a local version of the vpk and a parsed version of the items_game file. mine is produced as a sideproduct of dotabase_builder



thisdir = os.path.dirname(os.path.realpath(__file__))
outfile = os.path.join(thisdir, "data/arcana_links.json")
configfile = os.path.join(thisdir, "config.json")
with open(configfile) as f:
	config = json.loads(f.read())

with open(config["arcanascript"]["items_game_path"]) as f:
	data = json.loads(f.read())

hero_image_cosmetics = []

# go through the cosmetics and look for all arcanas/personas where they change the image
for itemid in data["items_game"]["items"]:
	item = data["items_game"]["items"][itemid]
	for attr in item.get("visuals", {}):
		if not ("asset_modifier" in attr):
			continue
		attr_data = item["visuals"][attr]
		if attr_data.get("type") == "icon_replacement_hero":
			image = attr_data.get("modifier")
			heroname = list(item["used_by_heroes"].keys())[0]
			hero_image_cosmetics.append({
				"hero": heroname,
				"image": image
			})
		elif attr_data.get("type") == "icon_replacement_hero_minimap" and "persona" in attr_data.get("modifier"):
			image = attr_data.get("modifier")
			heroname = list(item["used_by_heroes"].keys())[0]
			hero_image_cosmetics.append({
				"hero": heroname,
				"image": image
			})

vpk_path = config["arcanascript"]["vpk_path"]

session = dotabase_session()

output_json = {}

for image_cosmetic in hero_image_cosmetics:
	hero_id = str(session.query(Hero).filter_by(full_name=image_cosmetic["hero"]).first().id)
	if hero_id not in output_json:
		output_json[hero_id] = []
	filepath = f"/panorama/images/heroes/{image_cosmetic['image']}_png.png"

	if not os.path.exists(vpk_path + filepath):
		print(f"Error! Can't find file {filepath} (skipping)")
	else:
		output_json[hero_id].append(filepath)

with open(outfile, "w+") as f:
	f.write(json.dumps(output_json, indent="\t"))

print("Done!")