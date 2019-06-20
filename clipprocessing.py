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
