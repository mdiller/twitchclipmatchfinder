# set base image (host OS)
FROM python:3.8

# copy the content of the local src directory to the working directory
COPY . /code

# set the working directory in the container
WORKDIR /code

# install openCV prerequisites
RUN apt-get update
RUN apt-get install ffmpeg libsm6 libxext6  -y

# install dependencies
RUN pip --disable-pip-version-check install -r requirements.txt 2>&1 | grep --line-buffered -v "pip as the 'root' user"

# command to run on container start
CMD [ "python", "./redditbot.py" ] 