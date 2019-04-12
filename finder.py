import cv2
import numpy as np
import requests
import os
import json
from PIL import Image
from dotabase import *


session = dotabase_session()

vpk_url = "http://dotabase.dillerm.io/dota-vpk"
vpk_cache = "cache/vpk"

arcana_images = {}
with open("arcana_links.json", "r") as f:
	arcana_images = json.loads(f.read())

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
