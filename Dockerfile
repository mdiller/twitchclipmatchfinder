# set base image (host OS)
FROM python:3.8

# copy the content of the local src directory to the working directory
COPY . /code

# set the working directory in the container
WORKDIR /code

# install dependencies
RUN pip install -r requirements.txt

# command to run on container start
CMD [ "python", "./redditbot.py" ] 