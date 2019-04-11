import cv2
import numpy as np
import requests
from PIL import Image
from dotabase import *


session = dotabase_session()


def get_template(vpk_png_path):
	image = Image.open("vpk" + vpk_png_path).convert("RGB")
	image.thumbnail((64, 36))
	return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)

game_image = Image.open("cache/CuteSucculentScorpionAMPEnergy.png").convert("RGB")
game_image = game_image.crop((0, 0, game_image.size[0], 42))
img = cv2.cvtColor(np.asarray(game_image), cv2.COLOR_RGB2GRAY)
# img = cv2.imread("game.jpg", 0)
img2 = img.copy()

# All the 6 methods for comparison in a list
methods = ['cv2.TM_CCOEFF', 'cv2.TM_CCOEFF_NORMED', 'cv2.TM_CCORR',
			'cv2.TM_CCORR_NORMED', 'cv2.TM_SQDIFF', 'cv2.TM_SQDIFF_NORMED']
for meth in methods:
	print(meth)
	method = eval(meth)
	matches = []
	for hero in session.query(Hero):
		template = get_template(hero.image)
		w, h = template.shape[::-1]

		img = img2.copy()

		# Apply template Matching
		res = cv2.matchTemplate(img,template,method)
		min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

		# If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
		if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
			top_left = min_loc
			the_val = min_val
		else:
			top_left = max_loc
			the_val = max_val
		bottom_right = (top_left[0] + w, top_left[1] + h)

		# cv2.rectangle(img, top_left, bottom_right, 255, 2)
		if (top_left[1] < 5):
			matches.append({
				"hero": hero,
				"point": top_left,
				"value": the_val
			})

		# print(f"{hero.localized_name}: {top_left}, {bottom_right} ({the_val})")

	take_count = 15

	reverse = meth in ["cv2.TM_COEFF", "cv2.TM_CCOEFF_NORMED", "cv2.TM_CCORR_NORMED"]

	matches = sorted(matches, key=lambda m: m["value"], reverse=reverse)
	matches = matches[:take_count]
	# matches = sorted(matches, key=lambda m: m["point"][0], reverse=True)

	for match in matches:
		print(f"{match['hero'].localized_name}: {match['point']}    [{match['value']}]")
	print("\n")