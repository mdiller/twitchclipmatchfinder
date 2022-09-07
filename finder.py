import typing
import cv2
import numpy as np
import requests
import os
import json
import shutil
from PIL import Image
import sys
import datetime
from dotabase import *
import pathlib
import re
import youtube_dl


debug = False
SUPERDEBUG = False
PRINT_HTTP_REQUESTS = False

superdebug_dir = "superdebug"


finder_y_tolerance = 4
finder_x_tolerance = 15

twitch_datetime_format = '%Y-%m-%dT%H:%M:%SZ'

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
twitch_token_data = None

def superdebug_file(filename):
	if not os.path.exists(superdebug_dir):
		os.mkdir(superdebug_dir)
	return os.path.join(superdebug_dir, filename)

def print_debug(text):
	global debug
	if debug:
		print(text)

# gets the twitch token for use with the api
# based on https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#oauth-client-credentials-flow
def get_twitch_token():
	global twitch_token_data

	token_is_expired = twitch_token_data is None or twitch_token_data["expiration_date"] > datetime.datetime.now()

	if token_is_expired:
		if PRINT_HTTP_REQUESTS:
			print(f"http_request: auth_token refresh")
		response = requests.post(f"https://id.twitch.tv/oauth2/token?client_id={config['twitch']['client_id']}&client_secret={config['twitch']['client_secret']}&grant_type=client_credentials")

		if response.status_code != 200:
			print(f"error {response.status_code} when getting twitch token")
			print(response.text)
			exit(1)
		
		twitch_token_data = response.json()
		expiration_date = datetime.datetime.now() + datetime.timedelta(seconds=twitch_token_data["expires_in"] - 30)
		twitch_token_data["expiration_date"] = expiration_date
	
	return twitch_token_data["access_token"]

# CLIP PROCESSING

def cache_filename(slug, ext):
	return os.path.join(cache_dir, f"{slug}.{ext}")

def retrieve_clip_info(slug):
	filename = cache_filename(slug, "json")
	if os.path.exists(filename):
		with open(filename, "r") as f:
			return json.loads(f.read())
	else:
		url = f"https://api.twitch.tv/helix/clips?id={slug}"
		if PRINT_HTTP_REQUESTS:
			print(f"http_request: {url}")
		data = requests.get(url,
			headers= {
			"Client-ID": config["twitch"]["client_id"],
			"Authorization": "Bearer " + get_twitch_token()
		}).json()

		data = data["data"][0]

		thumb_url = data["thumbnail_url"]
		slice_point = thumb_url.index("-preview-")
		mp4_url = thumb_url[:slice_point] + '.mp4'
		data["mp4_url"] = mp4_url

		if data.get("video_id"):
			vod_id = data["video_id"]
			url = f"https://api.twitch.tv/helix/videos?id={vod_id}"
			if PRINT_HTTP_REQUESTS:
				print(f"http_request: {url}")
			vod_data = requests.get(url,
				headers= {
				"Client-ID": config["twitch"]["client_id"],
				"Authorization": "Bearer " + get_twitch_token()
			}).json()
			data["vod_data"] = vod_data["data"][0]

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
			if PRINT_HTTP_REQUESTS:
				print(f"http_request: {mp4_url}")
			r = requests.get(mp4_url)
			with open(mp4_filename, "wb+") as f:
				f.write(r.content)

		vidcap = cv2.VideoCapture(mp4_filename)
		success, image = vidcap.read()
		cv2.imwrite(frame_filename, image)
		vidcap.release()
	return frame_filename


# HERO FINDING LOGIC

def save_content(filename, data):
	file_dir = os.path.dirname(filename)
	if not os.path.exists(file_dir):
		os.makedirs(file_dir)
	with open(filename, "wb+") as f:
		f.write(data)

def get_template(vpk_png_path, width) -> cv2.Mat:
	local_file = vpk_cache + vpk_png_path
	if not os.path.exists(local_file):
		remote_url = vpk_url + vpk_png_path
		if PRINT_HTTP_REQUESTS:
			print(f"http_request: {remote_url}")
		r = requests.get(remote_url)
		save_content(local_file, r.content)

	# this gets the right ratio for a hero image
	height = round(0.5625 * width)
	image = Image.open(local_file).convert("RGB")
	image.thumbnail((width, height), Image.Resampling.LANCZOS)

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
	hero: Hero
	size_ratio: float
	hero_width: int
	images: typing.List[cv2.Mat]
	point: typing.Tuple[int, int]
	score: float
	def __init__(self, hero: Hero, size_ratio):
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

def find_heroes(match_image_path, method=cv2.TM_CCOEFF_NORMED, extra_count=0, sort_by_score=False) -> typing.List[HeroMatch]:
	game_image = Image.open(match_image_path).convert("RGB")
	# ratio between full hero size and the one in this image
	image_ratio = game_image.size[1] / 2160

	# yes, calculating this relative to the height
	herobar_width = 0.8 * game_image.size[1]
	herobar_margin = (game_image.size[0] - herobar_width) // 2

	# added this logic because sometimes theres a black border at the top of the image
	top_margin = -1
	margin_samples = 20
	brightness_threshold = 30
	done_finding_margin = False
	while not done_finding_margin:
		top_margin += 1
		for i in range(margin_samples):
			pixel = game_image.getpixel((int(i * (game_image.width / margin_samples)), top_margin))
			brightness = pixel[0] + pixel[1] + pixel[2]
			if brightness > brightness_threshold:
				done_finding_margin = True
				break

	game_image = game_image.crop((herobar_margin, top_margin, game_image.size[0] - herobar_margin, top_margin + int(84 * image_ratio)))
	img = cv2.cvtColor(np.asarray(game_image), cv2.COLOR_RGB2GRAY)
	img2 = img.copy()

	if SUPERDEBUG:
		game_image.save(superdebug_file("herobar.png"))
	
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

	matches = list(filter(lambda m: m.is_point_valid(finder_y_tolerance, finder_x_tolerance), matches))
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

def find_match(slug, print_finding=True):
	if print_finding:
		print(f"finding for {slug}")
	try:
		clip_info = retrieve_clip_info(slug)
		clip_frame = get_first_clip_frame(slug)
		if SUPERDEBUG:
			shutil.copyfile(clip_frame, superdebug_file("first_frame.png"))
	except Exception as e:
		raise ClipLoadingException() from e

	return find_match_with_info(clip_info, clip_frame)

youtube_url_patterns = [
	r"https?://(?:www\.)?youtube\.com/watch\?v=([^/&]*)(?:&t=(\d+))?",
	r"https?://(?:www\.)?youtu\.be/([^/?]*)(?:\?t=(\d+))?",
]


def find_match_from_youtube(url):
	youtube_id = None
	seconds_offset = None
	for pattern in youtube_url_patterns:
		match = re.match(pattern, url)
		if match:
			youtube_id = match.group(1)
			if match.group(2):
				seconds_offset = int(match.group(2))
			break
	if youtube_id is None:
		raise ClipFinderException(message="Doesn't look like a youtube url")

	ytdl_options = {
		"format": "bestvideo[ext=mp4]",
		"geturl": True,
		"timestamp": True
	}
	with youtube_dl.YoutubeDL(ytdl_options) as ytdl:
		print("contacting youtube for mp4 url...")
		video_info = ytdl.extract_info(youtube_id, download=False)
	
	video_url = video_info["url"]

	# get date created
	date_created = datetime.datetime.strptime(video_info["upload_date"], "%Y%m%d")
	date_created += datetime.timedelta(days=1) # add a day because we dont have time info so assume worst
	date_created = date_created.strftime(twitch_datetime_format)

	# calculate seconds in if dont already have
	if seconds_offset is None:
		seconds_offset = video_info["duration"] // 5

	video_frame_file = cache_filename(f"youtube_{youtube_id}_{seconds_offset}", "png")

	if not os.path.exists(video_frame_file):
		print("extracting frame...")
		vidcap = cv2.VideoCapture(video_url)
		frame_rate = vidcap.get(5) #frame rate
		desired_frame = seconds_offset * frame_rate

		vidcap.set(1, desired_frame)
		success, frame = vidcap.read()
		if not success:
			raise ClipFinderException(message="Error when extracting frame")
		cv2.imwrite(video_frame_file, frame)
		vidcap.release()

	return find_match_with_info({
		"created_at": date_created
	}, video_frame_file)

def find_match_from_file(image_path):
	print(f"finding from {image_path}")

	date_created = datetime.datetime.fromtimestamp(pathlib.Path(image_path).stat().st_ctime)
	date_created = date_created.strftime(twitch_datetime_format)

	return find_match_with_info({
		"created_at": date_created
	}, image_path)

def find_match_with_info(clip_info, clip_image):
	heroes = find_heroes(clip_image)

	if len(heroes) != 10:
		print_debug("not enough heroes found")
		raise HeroFindingException(heroes=heroes)
	unsure_count = 0
	for hero_match in heroes:
		if hero_match.score < 0.75:
			unsure_count += 1
	if unsure_count > 5:
		print_debug("not high enough confidence for some heroes")
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
	print_debug(url)

	timestamp = datetime.datetime.strptime(clip_info["created_at"], twitch_datetime_format)
	timestamp = int(timestamp.replace(tzinfo=datetime.timezone.utc).timestamp())

	if timestamp < 1555200000:
		raise MatchTooEarlyException(heroes=heroes)

	try:
		if PRINT_HTTP_REQUESTS:
			print(f"http_request: {url}")
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

	# NOTE: unfortunatley the 'offset' field was removed in the new 'helix' api that we're being forced to use, so we can't get the below information unless they add that feature back
	# if clip_info.get("vod_data"):
	# 	timestamp = datetime.datetime.strptime(clip_info["vod_data"]["created_at"], twitch_datetime_format)
	# 	timestamp = int(timestamp.replace(tzinfo=datetime.timezone.utc).timestamp())
	# 	timestamp += clip_info["vod"]["offset"]
	# 	new_diff = (timestamp - best_match["start_time"]) // 60
	# 	if new_diff > 0:
	# 		result["better_minutes_diff"] = new_diff

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
				if match_details['league']['tier'] in ['premium', 'professional']:
					result['league_name'] = match_details['league']['name']
					result['team_rad'] = match_details['radiant_team']['name']
					result['team_dire'] = match_details['dire_team']['name']

	except (json.decoder.JSONDecodeError, KeyError) as e:
		pass

	return result


def run_main():
	global debug
	global SUPERDEBUG
	debug = True
	if len(sys.argv) > 1:
		slug = sys.argv[1]
		if len(sys.argv) > 2:
			if sys.argv[2] == "-superdebug":
				SUPERDEBUG = True
		try:
			if re.match(r"https?://(?:www\.)?youtu", slug):
				# this is a youtube url
				match = find_match_from_youtube(slug)
			elif os.path.isfile(slug):
				# this is a passed in file to an image we can parse
				match = find_match_from_file(slug)
			else:
				match = find_match(slug)
		except HeroFindingException as e:
			print("HeroFindingException encountered!!!")
			print(f"found {len(e.heroes)} heroes:")
			for hero in e.heroes:
				print(hero)
			exit(1)
		except MatchNotFoundException as e:
			print("MatchNotFoundException encountered!!!")
			print(f"found {len(e.heroes)} heroes:")
			for hero in e.heroes:
				print(hero)
			exit(1)
		print("matched for the following heroes:")
		for hero_match in match["heroes"]:
			print(hero_match)
		print(f"found match {match['match_id']}")
		print(f"started {match['minutes_diff']} minutes before the clip was taken.")
		if match.get("better_minutes_diff"):
			print(f"started {match['better_minutes_diff']} minutes before the clip was recorded.")	
		if match.get('league_name'):
			print(f"{match['team_rad']} vs {match['team_dire']} at {match['league_name']}")
		print(f"https://www.opendota.com/matches/{match['match_id']}")


if __name__ == '__main__':
	run_main()
