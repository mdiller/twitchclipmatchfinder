import requests
import json
import cv2
import os

config = {}

cache_dir = "cache"

if not os.path.exists(cache_dir):
	os.mkdir(cache_dir)

with open("config.json", "r") as f:
	config = json.loads(f.read())

def cache_filename(slug, ext):
	return os.path.join(cache_dir, f"{slug}.{ext}")

def retrieve_mp4_data(slug):
	filename = cache_filename(slug, "json")
	if os.path.exists(filename):
		with open(filename, "r") as f:
			return json.loads(f.read())
	else:
		clip_info = requests.get(f"https://api.twitch.tv/helix/clips?id={slug}", 
			headers= {"Client-ID": config["twitch"]["client_id"]}).json()
		data = clip_info["data"][0]

		thumb_url = data['thumbnail_url']
		slice_point = thumb_url.index("-preview-")
		mp4_url = thumb_url[:slice_point] + '.mp4'
		data["mp4_url"] = mp4_url

		with open(filename, "w+") as f:
			f.write(json.dumps(data, indent="\t"))

		return data

def get_first_clip_frame(slug):
	mp4_filename = cache_filename(slug, "mp4")
	frame_filename = cache_filename(slug, "png")
	if not os.path.exists(frame_filename):
		if not os.path.exists(mp4_filename):
			data = retrieve_mp4_data(slug)
			mp4_url = data["mp4_url"]
			r = requests.get(mp4_url)
			with open(mp4_filename, "wb+") as f:
				f.write(r.content)

		vidcap = cv2.VideoCapture(mp4_filename)
		success, image = vidcap.read()
		cv2.imwrite(frame_filename, image)
	return frame_filename

get_first_clip_frame("CuteSucculentScorpionAMPEnergy")