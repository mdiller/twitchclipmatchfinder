# TwitchClipMatchFinder (name pending)

This tool takes a twitch clip of someone playing dota and finds the match (match id) of dota that they were playing so you can get a dotabuff/opendota link or retrieve stats for it

## Steps

- get some info about the clip [via the twitch api](https://dev.twitch.tv/docs/v5/reference/clips/#get-clip)
- download the mp4 of the clip
- extract the first frame of the mp4
- find the heroes in the top bar of the image
    - first, crop the image to only look at the top row where the heroes should be
    - then load all the hero images (plus arcana images)
    - check if the hero is in the given image and if so, where
    - sort the results to get the 10 heroes that are most likely in this image in the right order
    - do a bunch of other things to make sure we got the right heroes in the right places, because computers are bad at pattern detection
- use [this opendota api endpoint](https://docs.opendota.com/#tag/findMatches) to search for matches containing exactly this hero matchup
- pick the correct match out of the results based on which one has a start time closest to the time that the clip was taken