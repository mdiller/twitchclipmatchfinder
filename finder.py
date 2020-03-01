import cv2
import numpy as np
import requests
import os
import json
from PIL import Image
import sys
import datetime
from dotabase import *


session = dotabase_session()

vpk_url = "http://dotabase.dillerm.io/dota-vpk"
vpk_cache = "cache/vpk"

arcana_images = {}
with open("data/arcana_links.json", "r") as f:
	arcana_images = json.loads(f.read())

config = {}

cache_dir = "cache"

if not os.path.exists(cache_dir):
	os.mkdir(cache_dir)

with open("config.json", "r") as f:
	config = json.loads(f.read())


# CLIP PROCESSING

def cache_filename(slug, ext):
	return os.path.join(cache_dir, f"{slug}.{ext}")

def retrieve_clip_info(slug):
	filename = cache_filename(slug, "json")
	if os.path.exists(filename):
		with open(filename, "r") as f:
			return json.loads(f.read())
	else:
		data = requests.get(f"https://api.twitch.tv/kraken/clips/{slug}",
			headers= {
			"Client-ID": config["twitch"]["client_id"],
			"Accept": "application/vnd.twitchtv.v5+json"
		}).json()

		thumb_url = data["thumbnails"]["medium"]
		slice_point = thumb_url.index("-preview-")
		mp4_url = thumb_url[:slice_point] + '.mp4'
		data["mp4_url"] = mp4_url

		if data["vod"]:
			vod_id = data["vod"]["id"]
			vod_data = requests.get(f"https://api.twitch.tv/kraken/videos/{vod_id}",
				headers= {
				"Client-ID": config["twitch"]["client_id"],
				"Accept": "application/vnd.twitchtv.v5+json"
			}).json()
			data["vod_data"] = vod_data

		with open(filename, "w+") as f:
			f.write(json.dumps(data, indent="\t"))

		return data

def get_first_clip_frame(slug):
	mp4_filename = cache_filename(slug, "mp4")
	frame_filename = cache_filename(slug, "png")
	if not os.path.exists(frame_filename):
		if not os.path.exists(mp4_filename):
			data = retrieve_clip_info(slug)
			mp4_url = data["mp4_url"]
			r = requests.get(mp4_url)
			with open(mp4_filename, "wb+") as f:
				f.write(r.content)

		vidcap = cv2.VideoCapture(mp4_filename)
		success, image = vidcap.read()
		cv2.imwrite(frame_filename, image)
	return frame_filename


# HERO FINDING LOGIC

def save_content(filename, data):
	file_dir = os.path.dirname(filename)
	if not os.path.exists(file_dir):
		os.makedirs(file_dir)
	with open(filename, "wb+") as f:
		f.write(data)

def get_template(vpk_png_path, width):
	local_file = vpk_cache + vpk_png_path
	if not os.path.exists(local_file):
		remote_url = vpk_url + vpk_png_path
		r = requests.get(remote_url)
		save_content(local_file, r.content)

	# this gets the right ratio for a hero image
	height = round(0.5625 * width)
	image = Image.open(local_file).convert("RGB")
	image.thumbnail((width, height), Image.ANTIALIAS)

	modifier = width / 128
	# crop to not include the edges or the bottom section where dota plus icons show up
	image = image.crop((
		round(8 * modifier),
		round(8 * modifier),
		image.size[0] - round(8 * modifier),
		image.size[1] - round(32 * modifier)
	))
	return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)

# x positions of heroes in the match image, based on an image with height of 2160
hero_positions = [ 30.44, 156.44, 282.44, 408.44, 534.44, 1078.77, 1205.11, 1331.11, 1456.44, 1582.77 ]

class HeroMatch():
	def __init__(self, hero, size_ratio):
		self.hero = hero
		self.size_ratio = size_ratio
		self.hero_width = round(128 * size_ratio)
		self.images = []
		self.point = None
		self.score = None
		self.add_image(hero.image)
		if str(hero.id) in arcana_images:
			for img in arcana_images[str(hero.id)]:
				self.add_image(img)

	def add_image(self, vpk_img_path):
		self.images.append(get_template(vpk_img_path, self.hero_width))

	@classmethod
	def get_all(cls, width):
		result = []
		for hero in session.query(Hero):
			result.append(HeroMatch(hero, width))
		return result

	def is_point_valid(self, y_tolerance, x_tolerance):
		y = round(self.hero_width / 8)
		return abs(self.point[1] - y) < y_tolerance and self.slot_diff < x_tolerance

	def get_index_diff(self):
		normedx = self.point[0] / self.size_ratio
		bestdiff = 1000
		besti = 0
		for i in range(len(hero_positions)):
			diff = hero_positions[i] - normedx
			if abs(diff) < abs(bestdiff):
				bestdiff = diff
				besti = i
		return besti, bestdiff

	@property
	def slot_diff(self):
		slot, diff = self.get_index_diff()
		return abs(diff)

	@property
	def slot(self):
		slot, diff = self.get_index_diff()
		return slot

	def __str__(self):
		return f"{self.hero.localized_name.rjust(20)}: {str(self.point).rjust(10)} {{{self.slot} {f'{self.slot_diff:.2f}'.rjust(6)}}} [{self.score}]"



# removed the ones that are bad
matching_methods = ["cv2.TM_CCOEFF", "cv2.TM_CCOEFF_NORMED", "cv2.TM_CCORR",
	"cv2.TM_CCORR_NORMED", "cv2.TM_SQDIFF", "cv2.TM_SQDIFF_NORMED"]

def find_heroes(match_image_path, method=cv2.TM_CCOEFF_NORMED, extra_count=0, sort_by_score=False):
	game_image = Image.open(match_image_path).convert("RGB")
	# ratio between full hero size and the one in this image
	image_ratio = game_image.size[1] / 2160

	# yes, calculating this relative to the height
	herobar_width = 0.8 * game_image.size[1]
	herobar_margin = (game_image.size[0] - herobar_width) // 2

	game_image = game_image.crop((herobar_margin, 0, game_image.size[0] - herobar_margin, int(84 * image_ratio)))
	img = cv2.cvtColor(np.asarray(game_image), cv2.COLOR_RGB2GRAY)
	img2 = img.copy()

	matches = HeroMatch.get_all(image_ratio)
	for match in matches:
		for template in match.images:
			w, h = template.shape[::-1]

			img = img2.copy()

			# Apply template Matching
			result = cv2.matchTemplate(img, template, method)
			min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

			# If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
			if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
				top_left = min_loc
				score = 0 - min_val
			else:
				top_left = max_loc
				score = max_val

			if match.score is None or match.score < score:
				match.score = score
				match.point = top_left

	matches = list(filter(lambda m: m.is_point_valid(4, 10), matches))
	matches = sorted(matches, key=lambda m: m.score, reverse=True)

	final_matches = []
	for slot in range(10):
		besti = None
		for i in range(len(matches)):
			match = matches[i]
			if slot == match.slot:
				besti = i
				break
		if besti is not None:
			final_matches.append(matches.pop(besti))

	if sort_by_score:
		final_matches = sorted(final_matches, key=lambda m: m.score, reverse=True)

	if extra_count:
		final_matches.extend(matches[:extra_count])

	return final_matches

# indicates something went wrong when finding this match
class ClipFinderException(Exception):
	def __init__(self, message=None, heroes=None):
		super().__init__(message)
		self.heroes = heroes or []

# there was an error loading the clip
class ClipLoadingException(ClipFinderException):
	pass

# couldn't find all the heroes in this clip, or we weren't confident enough in our findings
class HeroFindingException(ClipFinderException):
	pass

# couldn't find the match in the findMatches results
class MatchNotFoundException(ClipFinderException):
	pass

# the match occured before all of the findMatches functionality was available
class MatchTooEarlyException(ClipFinderException):
	pass

# an error occured when requesting data from the opendota api
class OpendotaApiException(ClipFinderException):
	pass

def find_match(slug):
	print(f"finding for {slug}")
	try:
		clip_info = retrieve_clip_info(slug)
		clip_frame = get_first_clip_frame(slug)
	except Exception as e:
		raise ClipLoadingException() from e

	heroes = find_heroes(clip_frame)

	if len(heroes) != 10:
		raise HeroFindingException(heroes=heroes)
	unsure_count = 0
	for hero_match in heroes:
		if hero_match.score < 0.75:
			unsure_count += 1
	if unsure_count > 5:
		raise HeroFindingException(heroes=heroes)

	teama = []
	teamb = []
	for i in range(5):
		teama.append(heroes[i].hero.id)
	for i in range(5, 10):
		teamb.append(heroes[i].hero.id)

	teama = "&".join(map(lambda p: f"teamA={p}", teama))
	teamb = "&".join(map(lambda p: f"teamB={p}", teamb))
	url = f"https://api.opendota.com/api/findMatches?{teama}&{teamb}"

	timestamp = datetime.datetime.strptime(clip_info["created_at"], '%Y-%m-%dT%H:%M:%SZ')
	timestamp = int(timestamp.replace(tzinfo=datetime.timezone.utc).timestamp())

	if timestamp < 1555200000:
		raise MatchTooEarlyException(heroes=heroes)

	try:
		response = requests.get(url)
		if response.status_code != 200:
			raise OpendotaApiException(heroes=heroes)
		found_matches = response.json()
	except json.decoder.JSONDecodeError as e:
		raise OpendotaApiException from e

	best_match = None
	for match in found_matches:
		if match["start_time"] < timestamp:
			if best_match is None or match["start_time"] > best_match["start_time"]:
				best_match = match
	if best_match is None:
		raise MatchNotFoundException(heroes=heroes)

	minutes_diff = (timestamp - best_match["start_time"]) // 60

	result = {
		"match_id": best_match["match_id"],
		"minutes_diff": minutes_diff,
		"heroes": heroes
	}

	if clip_info.get("vod_data"):
		timestamp = datetime.datetime.strptime(clip_info["vod_data"]["created_at"], '%Y-%m-%dT%H:%M:%SZ')
		timestamp = int(timestamp.replace(tzinfo=datetime.timezone.utc).timestamp())
		timestamp += clip_info["vod"]["offset"]
		new_diff = (timestamp - best_match["start_time"]) // 60
		if new_diff > 0:
			result["better_minutes_diff"] = new_diff

	# Get league info
	match_file = cache_filename(result["match_id"], "json")
	match_details = None
	try:
		if os.path.exists(match_file):
			with open(match_file, "r") as f:
				match_details = json.loads(f.read())
		else:
			match_details_url = f"https://api.opendota.com/api/matches/{best_match['match_id']}"
			response = requests.get(match_details_url)
			if response.status_code == 200:
				match_details = response.json()

			with open(match_file, "w+") as f:
				f.write(json.dumps(match_details, indent="\t"))

		if match_details is not None:
			if 'tier' in match_details['league']:
				if match_details['league']['tier'] == 'premium':
					result['league_name'] = match_details['league']['name']
					result['team_rad'] = match_details['radiant_team']['name']
					result['team_dire'] = match_details['dire_team']['name']

	except (json.decoder.JSONDecodeError, KeyError) as e:
		pass

	return result


if __name__ == '__main__':
	if len(sys.argv) > 1:
		slug = sys.argv[1]
		match = find_match(slug)
		print("matched for the following heroes:")
		for hero_match in match["heroes"]:
			print(hero_match)
		print(f"found match {match['match_id']}")
		print(f"started {match['minutes_diff']} minutes before the clip was taken.")
		if match.get("better_minutes_diff"):
			print(f"started {match['better_minutes_diff']} minutes before the clip was recorded.")
		print(f"found match {match['match_id']}")		
		if match.get('league_name'):
			print(f"{match['team_rad']} vs {match['team_dire']} at {match['league_name']}")
		print(f"https://www.opendota.com/matches/{match['match_id']}")
