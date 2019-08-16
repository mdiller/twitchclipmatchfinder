# TwitchClipMatchFinder

This tool takes a twitch clip of someone playing dota and finds the match (match id) of dota that they were playing so you can get a dotabuff/opendota link or retrieve stats for it. I've created a reddit bot that automatically finds clips posted and gets matches for them: [/u/DotaClipMatchFinder](https://www.reddit.com/user/DotaClipMatchFinder) (The name is slightly different because TwitchClipMatchFinder was too many characters)

## How it works

- Get some info about the clip [via the twitch api](https://dev.twitch.tv/docs/v5/reference/clips/#get-clip)
- Download the mp4 of the clip
- Extract the first frame of the mp4 (using [OpenCV](https://opencv.org/))
- Find the heroes in the top bar of the image
    - First, crop the image to only look at the top row where the heroes should be
    - Load all the hero images (plus arcana images)
    - Check if the hero is in the given image and if so, where (using [OpenCV](https://opencv.org/))
    - Filter out heroes that are in the wrong place in the image
    - Sort the results to get the 10 heroes that are most likely in this image in the right order
    - Do a bunch of other things to make sure we got the right heroes in the right places, because computers are bad at pattern detection
- Use [this opendota api endpoint](https://docs.opendota.com/#tag/findMatches) to search for matches containing exactly this hero matchup
- Pick the correct match out of the results based on which one has a start time closest to the time that the clip was taken


## Libraries used

- [Twitch API](https://dev.twitch.tv/docs/v5/reference/clips/#get-clip)
- [Opendota API](https://docs.opendota.com/#tag/findMatches)
- [Python PIL / Pillow](https://pillow.readthedocs.io/en/stable/)
- [OpenCV](https://opencv.org/)

## Usage

This library was built with the idea of using it as a reddit bot, which is its main use, but it can also be used separately to find specific clips. The `find_match` function in `finder.py` can be called to find the match for a given clip slug (the 'slug' is the bit at the end of the twitch clip url that is a bunch of words together.) The finder.py file can also be started directly if you give the clip slug as the argument. Here is an example for https://clips.twitch.tv/CoyCleverOilLitFam:

```
> python finder.py CoyCleverOilLitFam
finding for CoyCleverOilLitFam
matched for the following heroes:
          Grimstroke:    (16, 8) {0   1.56} [0.9345031380653381]
    Templar Assassin:    (79, 8) {1   1.56} [0.9476589560508728]
         Beastmaster:   (142, 8) {2   1.56} [0.9453526139259338]
         Wraith King:   (205, 8) {3   1.56} [0.9641481637954712]
       Shadow Shaman:   (268, 8) {4   1.56} [0.9190652370452881]
                Ursa:   (539, 8) {5   0.77} [0.9223578572273254]
           Alchemist:   (602, 8) {6   1.11} [0.911087691783905]
            Silencer:   (665, 8) {7   1.11} [0.945387601852417]
                Doom:   (728, 8) {8   0.44} [0.9171727299690247]
        Earth Spirit:   (791, 8) {9   0.77} [0.9245378375053406]
found match 4757318890, started 37 minutes before the clip was taken.
https://www.opendota.com/matches/4757318890
```